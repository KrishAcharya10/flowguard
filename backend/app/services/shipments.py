"""Milestones (forward-only) and delay attribution."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from .core import add_event, hours, leaf_shipments
from .paths import get_path, total_km

NEXT = {s: m.STATES[i + 1] for i, s in enumerate(m.STATES[:-1])}
LABEL = {
    "PLANNED": "Planned", "LOADING": "Loading at Plant X", "AT_PLANT_GATE": "Loaded, waiting at plant gate",
    "IN_TRANSIT": "In transit", "ARRIVED_AT_CUSTOMER_GATE": "Arrived at customer gate", "DELIVERED": "Delivered (POD)",
}
ATTRIBUTION_TOLERANCE_H = 1e-3     # documented rounding tolerance for delay-event sums


def advance_state(db: Session, sh: m.Shipment, to_state: str, at: datetime, source: str,
                  user: Optional[m.User] = None, note: str = "") -> None:
    """Move to the NEXT state only. Creates an event and bumps state_version."""
    if NEXT.get(sh.state) != to_state:
        raise HTTPException(409, f"Invalid transition {sh.state} -> {to_state}. Next allowed: {NEXT.get(sh.state)}")
    sh.state, sh.state_entered_at = to_state, at
    sh.state_version += 1
    pts, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    if to_state == "IN_TRANSIT":
        from . import gate as gate_svc
        gate_svc.complete_on_departure(db, sh, at)
        sh.departed_at = at
        sh.last_progress_km, sh.last_lat, sh.last_lon, sh.last_telemetry_at = 0.0, pts[0].lat, pts[0].lon, at
        for d in db.query(m.Disruption).filter(m.Disruption.kind == "DEPARTURE_OFFSET",
                                               m.Disruption.shipment_id == sh.id, m.Disruption.status == "ACTIVE"):
            d.status, d.ended_at = "ENDED", at
    elif to_state == "LOADING":
        for d in db.query(m.Disruption).filter(m.Disruption.kind == "DEPARTURE_OFFSET",
                                               m.Disruption.shipment_id == sh.id, m.Disruption.status == "ACTIVE"):
            d.status, d.ended_at = "ENDED", at
    elif to_state == "ARRIVED_AT_CUSTOMER_GATE":
        sh.arrived_at = at
        sh.last_progress_km, sh.last_lat, sh.last_lon, sh.last_telemetry_at = total_km(segs), pts[-1].lat, pts[-1].lon, at
        attribute_delay(db, sh)
        from .warroom import complete_if_arrived
        db.flush()
        complete_if_arrived(db, sh.order_id)
    elif to_state == "DELIVERED":
        sh.delivered_at = at
    add_event(db, sh.id, "MILESTONE", at, note or LABEL[to_state], state=to_state, user=user, source=source)


def attribute_delay(db: Session, sh: m.Shipment) -> None:
    """Realised delay = max(0, arrived_at - planned_arrival_at), split across observed
    disruption causes by how long each overlapped the trip. Rows do not overlap in time
    and their hours sum to the realised delay. Anything unexplained is classed as
    ROUTE_CONGESTION (declared assumption). Early arrivals create no rows."""
    realised = max(0.0, hours(sh.arrived_at - sh.planned_arrival_at))
    if realised <= ATTRIBUTION_TOLERANCE_H:
        return
    _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    keys = {s.key for s in segs}
    trip_start = sh.departed_at or sh.planned_loading_at
    weights: dict[str, float] = {}
    for d in db.query(m.Disruption).filter(m.Disruption.cause.isnot(None)).order_by(m.Disruption.id):
        end = d.ended_at or sh.arrived_at
        if d.kind in ("CLOSURE", "SLOWDOWN"):
            if f"{d.route_id}:{d.segment_waypoint_id}" not in keys:
                continue
            lo, hi = max(d.start_at, trip_start), min(end, sh.arrived_at)
        elif d.kind in ("VEHICLE_STOPPAGE", "DEPARTURE_OFFSET"):
            if d.shipment_id != sh.id:
                continue
            lo, hi = d.start_at, min(end, sh.arrived_at)
            if d.kind == "DEPARTURE_OFFSET":
                hi = d.start_at + timedelta(hours=d.dur_mode_h)
        else:                                               # plant-wide gate / loading shifts: before departure
            lo, hi = max(d.start_at, sh.planned_loading_at), min(end, sh.departed_at or sh.arrived_at)
        w = hours(hi - lo)
        if w > 0:
            weights[d.cause] = weights.get(d.cause, 0.0) + w
    total_w = sum(weights.values())
    parts: list[tuple[str, float]] = []
    if total_w >= realised:
        parts = [(c, realised * w / total_w) for c, w in weights.items()]
    else:
        parts = list(weights.items())
        parts.append(("ROUTE_CONGESTION", realised - total_w))
    merged: dict[str, float] = {}
    for c, h in parts:
        merged[c] = merged.get(c, 0.0) + h
    cursor = sh.arrived_at - timedelta(hours=realised)
    items = sorted(merged.items())
    for i, (cause, h) in enumerate(items):
        end = sh.arrived_at if i == len(items) - 1 else cursor + timedelta(hours=h)
        db.add(m.DelayEvent(shipment_id=sh.id, cause=cause, start_at=cursor, end_at=end, hours=hours(end - cursor)))
        cursor = end


def order_arrival_complete(db: Session, order_id: str) -> bool:
    leaves = leaf_shipments(db, order_id)
    return bool(leaves) and all(s.arrived_at is not None for s in leaves)
