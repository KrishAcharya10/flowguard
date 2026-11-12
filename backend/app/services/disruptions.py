"""Disruption taxonomy (spec 4.5). Presets are parameterised events with validated bounds."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import PRESETS
from .core import ACTIVE_STATES, add_event, audit, next_id, plus_hours, sim_state
from .paths import get_path

SHIPMENT_PRESETS = {
    "BREAKDOWN": {"label": "Vehicle breakdown", "cause": "BREAKDOWN", "kind": "VEHICLE_STOPPAGE",
                  "duration": (1.0, 2.0, 4.0), "requires_state": ("IN_TRANSIT",)},
    "LATE_DISPATCH": {"label": "Late dispatch", "cause": "LATE_DISPATCH", "kind": "DEPARTURE_OFFSET",
                      "duration": (1.5, 1.5, 1.5), "requires_state": ("PLANNED",)},
    "TELEMETRY_OUTAGE": {"label": "Telemetry outage (data-quality event, not a delay cause)", "cause": None,
                         "kind": "TELEMETRY_OUTAGE", "duration": (1.0, 2.0, 3.0), "requires_state": ("IN_TRANSIT",)},
}
ALL_PRESETS = {**PRESETS, **SHIPMENT_PRESETS}


def affected_shipments(db: Session, d: m.Disruption) -> list[m.Shipment]:
    """Active shipments whose remaining plan this disruption can touch."""
    q = db.query(m.Shipment).filter(m.Shipment.disposition == "ACTIVE", m.Shipment.is_historical.is_(False),
                                    m.Shipment.state.in_(ACTIVE_STATES)).order_by(m.Shipment.id)
    out = []
    for sh in q:
        if d.kind in ("VEHICLE_STOPPAGE", "DEPARTURE_OFFSET", "TELEMETRY_OUTAGE"):
            hit = d.shipment_id == sh.id
        elif d.kind in ("GATE_QUEUE_SHIFT", "HANDLING_SHIFT"):
            hit = sh.state in ("PLANNED", "LOADING", "AT_PLANT_GATE")
        else:
            _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
            key = f"{d.route_id}:{d.segment_waypoint_id}"
            hit = any(s.key == key and (sh.last_progress_km or 0.0) < s.km_end - 1e-6 for s in segs)
            # the primary route is also "affected" for a vehicle that could still be rerouted around it
        if hit:
            out.append(sh)
    return out


def create(db: Session, user: m.User, preset: str, shipment_id: Optional[str], start_offset_h: float,
           duration: Optional[tuple[float, float, float]], multiplier: Optional[float]) -> m.Disruption:
    if preset not in ALL_PRESETS:
        raise HTTPException(422, f"Unknown preset {preset}")
    p = ALL_PRESETS[preset]
    now = sim_state(db).sim_now
    dur = duration or p["duration"]
    if not (0 <= dur[0] <= dur[1] <= dur[2] <= 72):
        raise HTTPException(422, "Duration must satisfy 0 <= min <= mode <= max <= 72 hours")
    mult = multiplier if multiplier is not None else p.get("multiplier", 1.0)
    if not (1.0 <= mult <= 5.0):
        raise HTTPException(422, "Multiplier must be between 1 and 5")
    if "requires_state" in p:
        sh = db.get(m.Shipment, shipment_id) if shipment_id else None
        if sh is None or sh.disposition != "ACTIVE" or sh.is_historical:
            raise HTTPException(422, f"{preset} needs an active shipment_id")
        if sh.state not in p["requires_state"]:
            raise HTTPException(409, f"{preset} requires the shipment to be {' or '.join(p['requires_state'])}")
        dup = db.query(m.Disruption).filter(m.Disruption.kind == p["kind"], m.Disruption.shipment_id == sh.id,
                                            m.Disruption.status == "ACTIVE").first()
        if dup:
            raise HTTPException(409, "The same disruption is already active for this shipment")
    else:
        shipment_id = None
        dup = db.query(m.Disruption).filter(m.Disruption.preset == preset, m.Disruption.status == "ACTIVE").first()
        if dup:
            raise HTTPException(409, "This disruption is already active (overlaps are not double-counted; end it first)")
    d = m.Disruption(id=next_id(db, "DSR"), preset=preset, label=p["label"], cause=p["cause"], kind=p["kind"],
                     route_id=p.get("route_id"), segment_waypoint_id=p.get("segment_waypoint_id"),
                     shipment_id=shipment_id, start_at=plus_hours(now, start_offset_h),
                     dur_min_h=dur[0], dur_mode_h=dur[1], dur_max_h=dur[2], multiplier=mult, status="ACTIVE")
    return activate(db, user, d, "DRIVER" if user.role == "TRANSPORTER" else "COORDINATOR")


def activate(db: Session, user: m.User, d: m.Disruption, source: str) -> m.Disruption:
    """Persist a new disruption and record it on every shipment it can touch (one code path for the
    coordinator's injector and for driver reports)."""
    now = sim_state(db).sim_now
    db.add(d)
    db.flush()
    for sh in affected_shipments(db, d):
        sh.state_version += 1                               # material event
        add_event(db, sh.id, "DISRUPTION_START", now, f"{d.label} ({d.id})", state=sh.state, user=user,
                  source=source)
    audit(db, user, "DISRUPTION_CREATED", "disruption", d.id,
          after={"preset": d.preset, "kind": d.kind, "duration_h": [d.dur_min_h, d.dur_mode_h, d.dur_max_h],
                 "multiplier": d.multiplier, "shipment_id": d.shipment_id, "source": source})
    return d


def end(db: Session, d: m.Disruption, at: datetime, user: Optional[m.User], source: str) -> None:
    if d.status == "ENDED":
        return
    hit = affected_shipments(db, d)
    d.status, d.ended_at = "ENDED", at
    for sh in hit:
        sh.state_version += 1
        add_event(db, sh.id, "DISRUPTION_END", at, f"{d.label} ended ({d.id})", state=sh.state, user=user, source=source)
    audit(db, user, "DISRUPTION_ENDED", "disruption", d.id, after={"ended_at": at.isoformat(), "source": source})
