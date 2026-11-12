"""ORM -> engine inputs. The predictor sees only observed events, reported
telemetry and declared distributions.

This module must never import the simulator (a test enforces it).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from ..engine.contracts import (ClosureInput, EngineInputs, HandlingStage, RepairInput, SegmentInput,
                                SlowdownInput, StockParams, Tri)
from ..engine.geo import PathSegment
from .core import hours
from .paths import get_path

USE_CURRENT = "__current__"


def active_disruptions(db: Session) -> list[m.Disruption]:
    return db.query(m.Disruption).filter(m.Disruption.status == "ACTIVE").order_by(m.Disruption.id).all()


def data_confidence(sh: m.Shipment, now: datetime, a: Assumptions) -> tuple[str, float, Optional[float]]:
    """Fresh / Aging / Stale from the age of the last REPORTED telemetry.
    Stale widens uncertainty: sigma x (1 + min(age / stale_threshold, 2))."""
    if sh.state != "IN_TRANSIT" or sh.last_telemetry_at is None:
        return "FRESH", 1.0, None
    age_min = hours(now - sh.last_telemetry_at) * 60.0
    if age_min <= a.fresh_minutes:
        return "FRESH", 1.0, age_min
    if age_min < a.stale_minutes:
        return "AGING", 1.0, age_min
    return "STALE", 1.0 + min(age_min / a.stale_minutes, 2.0), age_min


def remaining_segments(segs: list[PathSegment], progress_km: float) -> tuple[SegmentInput, ...]:
    out = []
    for s in segs:
        if progress_km >= s.km_end - 1e-6:
            continue
        inside = progress_km > s.km_start + 1e-6
        out.append(SegmentInput(s.key, s.km_end - max(progress_km, s.km_start), s.speed_kmh, inside))
    return tuple(out)


def _tri(d: m.Disruption) -> Tri:
    return Tri(d.dur_min_h, d.dur_mode_h, d.dur_max_h)


def lot_key_for(lot_type: str) -> str:
    return "" if lot_type == "SINGLE" else f"lot:{lot_type}|"


def build_inputs(db: Session, sh: m.Shipment, order: m.Order, now: datetime, a: Assumptions,
                 disruptions: list[m.Disruption], *, alt_route_id: Optional[str] = USE_CURRENT,
                 as_new_lot: Optional[str] = None, lead_h: float = 0.0) -> EngineInputs:
    """as_new_lot: model a not-yet-existing split child that starts loading after lead_h."""
    alt = sh.active_alternative_route_id if alt_route_id == USE_CURRENT else alt_route_id
    _, segs = get_path(db, sh.route_id, alt)
    transporter = db.get(m.Transporter, sh.transporter_id)
    state = "PLANNED" if as_new_lot else sh.state

    load_mult = max([d.multiplier for d in disruptions if d.kind == "HANDLING_SHIFT"] or [1.0])
    gate_mult = max([d.multiplier for d in disruptions if d.kind == "GATE_QUEUE_SHIFT"] or [1.0])
    loading = Tri(a.loading_min_h, a.loading_mode_h, a.loading_max_h).scaled(load_mult)
    gate = Tri(a.gate_min_h, a.gate_mode_h, a.gate_max_h).scaled(gate_mult)

    stages: tuple = ()
    gate_queue = None
    planned_wait = 0.0
    dispatch_delay = 0.0
    progress = 0.0
    repair = None
    if state == "PLANNED":
        stages = (HandlingStage("loading", a.loading_ref_h, loading),)
        gate_queue = gate
        if as_new_lot:
            dispatch_delay = lead_h                       # second-vehicle lead time
        else:
            planned_wait = max(0.0, hours(sh.planned_loading_at - now))
            # LATE_DISPATCH: fixed offset only while departure is still pending
            dispatch_delay = sum(d.dur_mode_h for d in disruptions
                                 if d.kind == "DEPARTURE_OFFSET" and d.shipment_id == sh.id)
    elif state == "LOADING":
        stages = (HandlingStage("loading", a.loading_ref_h, loading, max(0.0, hours(now - sh.state_entered_at))),)
        gate_queue = gate
    elif state == "AT_PLANT_GATE":
        gate_queue = gate
    elif state == "IN_TRANSIT":
        progress = sh.last_progress_km or 0.0             # last REPORTED position, never the hidden one
        for d in disruptions:
            if d.kind == "VEHICLE_STOPPAGE" and d.shipment_id == sh.id:
                repair = RepairInput(d.id, max(0.0, hours(now - d.start_at)), _tri(d))

    seg_inputs = remaining_segments(segs, progress)
    keys = {s.key for s in seg_inputs}
    closures, slowdowns = [], []
    for d in disruptions:
        if d.kind not in ("CLOSURE", "SLOWDOWN") or not d.segment_waypoint_id:
            continue
        key = f"{d.route_id}:{d.segment_waypoint_id}"
        if key not in keys:
            continue
        start_rel = hours(d.start_at - now)
        if d.kind == "CLOSURE":
            closures.append(ClosureInput(d.id, key, start_rel, _tri(d)))
        else:
            slowdowns.append(SlowdownInput(d.id, key, start_rel, _tri(d), d.multiplier))

    _, stale_scale, _ = data_confidence(sh, now, a) if not as_new_lot else ("FRESH", 1.0, None)
    lot_type = as_new_lot or sh.lot_type
    return EngineInputs(
        segments=seg_inputs,
        promised_rel_h=hours(order.promised_at - now) + a.grace_hours,
        handling_stages=stages, gate_queue=gate_queue,
        planned_wait_h=planned_wait, dispatch_delay_h=dispatch_delay,
        closures=tuple(closures), slowdowns=tuple(slowdowns), repair=repair,
        sigma_route=a.sigma_route, sigma_segment=a.sigma_segment,
        sigma_scale=transporter.sigma_factor * stale_scale,
        lot_key=lot_key_for(lot_type), residual_floor_h=a.residual_floor_h,
    )


def inventory_for(db: Session, order: m.Order) -> Optional[m.CustomerInventory]:
    return (db.query(m.CustomerInventory)
            .filter(m.CustomerInventory.customer_id == order.customer_id,
                    m.CustomerInventory.product_code == order.product_code).first())


def stock_params(db: Session, order: m.Order, now: datetime) -> Optional[StockParams]:
    """Depletion S = t0 + I0 / r. None when the customer shares no stock data."""
    inv = inventory_for(db, order)
    if inv is None:
        return None
    depletion_rel = hours(inv.measured_at - now) + inv.inventory_tonnes / inv.consumption_tph
    return StockParams(depletion_rel_h=depletion_rel, rate_tph=inv.consumption_tph, unload_h=inv.unloading_hours)
