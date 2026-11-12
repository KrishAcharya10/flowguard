"""Driver-reported problems: a breakdown or a road hazard on the vehicle's own route.

Both become ordinary disruptions through the same code as the coordinator's injector, so predictions,
alerts and the activity feed react exactly as they do to any other disruption. A report is data from a
human, not a measurement: the simulator still decides, from its hidden seed, when it really ends.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from . import disruptions as dis_svc
from . import predictions as pred_svc
from .core import add_event, audit, next_id, sim_now
from .paths import get_path

HAZARD_PRESET = "DRIVER_HAZARD"
HAZARD_DURATION = (1.0, 2.0, 3.5)       # hours (min / most likely / max), assumption
HAZARD_MULTIPLIER = 1.8                 # slowdown factor while the hazard lasts, assumption


def active_report(db: Session, sh: m.Shipment) -> Optional[m.Disruption]:
    return (db.query(m.Disruption).filter(
        m.Disruption.shipment_id == sh.id, m.Disruption.status == "ACTIVE",
        (m.Disruption.kind == "VEHICLE_STOPPAGE") | (m.Disruption.preset == HAZARD_PRESET)).first())


def report(db: Session, user: m.User, sh: m.Shipment, kind: str, note: Optional[str]) -> m.Disruption:
    if sh.disposition != "ACTIVE" or sh.state != "IN_TRANSIT":
        raise HTTPException(409, "You can report a breakdown or hazard only while the vehicle is in transit")
    if active_report(db, sh) is not None:
        raise HTTPException(409, "A report for this vehicle is already active. The control tower has been told.")
    now = sim_now(db)
    if kind == "BREAKDOWN":
        d = dis_svc.create(db, user, "BREAKDOWN", sh.id, 0.0, None, None)
        label = "breakdown"
    else:
        pts, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
        progress = sh.last_progress_km or 0.0
        seg = next((s for s in segs if progress < s.km_end - 1e-6), None)
        if seg is None:
            raise HTTPException(409, "The vehicle has no road ahead to report on")
        d = m.Disruption(id=next_id(db, "DSR"), preset=HAZARD_PRESET, label="Road hazard reported by a driver",
                         cause="ROUTE_CONGESTION", kind="SLOWDOWN", route_id=seg.route_id,
                         segment_waypoint_id=pts[seg.from_idx].waypoint_id, shipment_id=sh.id, start_at=now,
                         dur_min_h=HAZARD_DURATION[0], dur_mode_h=HAZARD_DURATION[1], dur_max_h=HAZARD_DURATION[2],
                         multiplier=HAZARD_MULTIPLIER, status="ACTIVE")
        dis_svc.activate(db, user, d, "DRIVER")
        label = "road hazard"
    text = (note or "").strip()
    add_event(db, sh.id, "DRIVER_REPORT", now, f"Driver reported a {label}" + (f": {text}" if text else ""),
              state=sh.state, user=user, source="DRIVER")
    audit(db, user, "DRIVER_REPORT", "shipment", sh.id, after={"kind": kind, "disruption": d.id, "note": text})
    db.flush()
    pred_svc.recompute(db, trigger="DISRUPTION_START", trigger_event_id=d.id,
                       trigger_label=f"{label} reported by the driver ({d.id})")
    return d
