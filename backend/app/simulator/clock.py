"""The simulation clock (spec 4.12). Time only moves through advance().

advance() runs ticks of at most 5 simulated minutes; each tick processes
disruption ends, milestones and telemetry in order; predictions are recomputed
once at the end. Default state is paused with explicit advance.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..engine.geo import position_at_km
from ..services import disruptions as dis_svc
from ..services import gate as gate_svc
from ..services import predictions as pred_svc
from ..services.core import ACTIVE_STATES, add_event, audit, get_assumptions, hours, plus_hours, sim_state
from ..services.paths import get_path, total_km
from ..services.shipments import advance_state
from . import truth

TICK_MINUTES = 5


def _tick(db: Session, now: datetime, a, global_seed: int) -> None:
    all_d = db.query(m.Disruption).order_by(m.Disruption.id).all()
    # 1) disruptions whose true end has passed
    for d in all_d:
        if d.status == "ACTIVE" and d.kind != "DEPARTURE_OFFSET":
            end = truth.disruption_true_end(global_seed, d)
            if end <= now:
                dis_svc.end(db, d, end, None, "SIMULATED")
    # 2) milestones (simulated geofence events), 3) telemetry
    shipments = (db.query(m.Shipment).filter(m.Shipment.disposition == "ACTIVE", m.Shipment.is_historical.is_(False),
                                             m.Shipment.state.in_(ACTIVE_STATES)).order_by(m.Shipment.id).all())
    for sh in shipments:
        for _ in range(4):                                  # a lot can pass several milestones in one tick
            if sh.state == "PLANNED":
                offset = sum(d.dur_mode_h for d in all_d if d.kind == "DEPARTURE_OFFSET"
                             and d.shipment_id == sh.id and d.status == "ACTIVE")
                due = plus_hours(sh.planned_loading_at, offset)
            elif sh.state == "LOADING":
                due = plus_hours(sh.state_entered_at, truth.loading_true_h(global_seed, sh, a, all_d))
            elif sh.state == "AT_PLANT_GATE":
                due = plus_hours(sh.state_entered_at, truth.gate_true_h(global_seed, sh, a, all_d))
            else:
                break
            if due > now:
                break
            advance_state(db, sh, {"PLANNED": "LOADING", "LOADING": "AT_PLANT_GATE",
                                   "AT_PLANT_GATE": "IN_TRANSIT"}[sh.state], max(due, sh.state_entered_at), "SIMULATED")
        if sh.state != "IN_TRANSIT":
            continue
        points = truth.transit_timeline(db, global_seed, sh, a, all_d)
        t_rel = hours(now - sh.departed_at)
        if t_rel >= points[-1][0]:
            advance_state(db, sh, "ARRIVED_AT_CUSTOMER_GATE", plus_hours(sh.departed_at, points[-1][0]), "SIMULATED")
            continue
        outage = any(d.kind == "TELEMETRY_OUTAGE" and d.shipment_id == sh.id and d.status == "ACTIVE" for d in all_d)
        if not outage:                                      # report an OBSERVED position; hidden truth is never stored
            pts, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
            km = min(truth.position_km(points, t_rel), total_km(segs))
            sh.last_progress_km = km
            sh.last_lat, sh.last_lon = position_at_km(pts, segs, km)
            sh.last_telemetry_at = now


POSITION_EVERY_H = 0.5      # one "position updated" event per vehicle per 30 simulated minutes (keeps the feed readable)


def _position_events(db: Session, now: datetime) -> None:
    """Record the latest REPORTED position of each moving vehicle as an event (throttled)."""
    moving = (db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False), m.Shipment.disposition == "ACTIVE",
                                          m.Shipment.state == "IN_TRANSIT", m.Shipment.last_telemetry_at == now).all())
    for sh in moving:
        last = (db.query(m.ShipmentEvent.occurred_at).filter(m.ShipmentEvent.shipment_id == sh.id,
                                                             m.ShipmentEvent.type == "POSITION")
                .order_by(m.ShipmentEvent.id.desc()).first())
        if last is not None and hours(now - last[0]) < POSITION_EVERY_H:
            continue
        _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
        pct = round(100 * (sh.last_progress_km or 0.0) / max(total_km(segs), 1e-9))
        add_event(db, sh.id, "POSITION", now, f"Latest position reported: {pct}% of the route completed",
                  state=sh.state, source="SIMULATED")


def advance(db: Session, minutes: float, user=None, record_audit: bool = True) -> dict:
    st = sim_state(db)
    a, _ = get_assumptions(db)
    start = st.sim_now
    target = start + timedelta(minutes=minutes)
    while st.sim_now < target:
        st.sim_now = min(target, st.sim_now + timedelta(minutes=TICK_MINUTES))
        _tick(db, st.sim_now, a, st.global_seed)
        db.flush()
    _position_events(db, st.sim_now)
    gate_svc.mark_missed(db, st.sim_now)
    gate_svc.ensure_slots(db, commit=False)
    st.clock_version += 1
    n = pred_svc.recompute(db, trigger="CLOCK_ADVANCE", trigger_label=f"clock advanced {minutes:g} min")
    if record_audit:        # the auto-run records its Start/Pause instead of one row per tick
        audit(db, user, "CLOCK_ADVANCED", "simulation_state", 1, before={"sim_now": start.isoformat()},
              after={"sim_now": st.sim_now.isoformat(), "clock_version": st.clock_version})
    return {"predictions_recomputed": n}
