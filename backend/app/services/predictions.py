"""Stored, immutable predictions (spec 4.3). GET endpoints never run Monte Carlo:
they read the rows written here.

Recomputed on: milestone, disruption start/end, telemetry outage start/end,
intervention applied, assumptions change, clock advance.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from .. import models as m
from ..engine.eta import simulate_arrival
from ..engine.risk import risk_category, risk_index
from ..engine.stock import stockout_hours
from ..seeds import seed_pred
from . import alerts as alert_svc
from .core import ACTIVE_STATES, get_assumptions, hours, iso, latest_prediction, leaf_shipments, plus_hours, sim_state
from .mapping import active_disruptions, build_inputs, data_confidence, stock_params

latest = latest_prediction

CHIP_LABELS = {
    "handling_deviation": "Loading / handling vs reference",
    "gate_queue": "Plant gate queue",
    "dispatch_delay": "Late dispatch / second-vehicle lead",
    "slowdown": "Route slowdown",
    "closure_wait": "Road closure wait",
    "repair_wait": "Vehicle repair wait",
    "variability": "Travel variability / interactions",
}


def recompute(db: Session, trigger: str, trigger_event_id: Optional[str] = None, trigger_label: Optional[str] = None,
              order_ids: Optional[list[str]] = None, raise_alerts: bool = True) -> int:
    """Run the engine once per active lot and insert new prediction rows. Does not commit."""
    st = sim_state(db)
    now = st.sim_now
    a, av = get_assumptions(db)
    disruptions = active_disruptions(db)
    q = (db.query(m.Shipment.order_id).filter(m.Shipment.disposition == "ACTIVE", m.Shipment.is_historical.is_(False),
                                              m.Shipment.state.in_(ACTIVE_STATES)).distinct())
    ids = sorted({r[0] for r in q})
    if order_ids is not None:
        ids = [i for i in ids if i in set(order_ids)]
    count = 0
    for oid in ids:
        order = db.get(m.Order, oid)
        stock = stock_params(db, order, now)
        results = {}
        lots = []
        for sh in leaf_shipments(db, oid):
            if sh.state in ACTIVE_STATES:
                root = sh.parent_shipment_id or sh.id
                seed = seed_pred(st.global_seed, root)
                res = simulate_arrival(build_inputs(db, sh, order, now, a, disruptions), a.n_samples, seed)
                results[sh.id] = (sh, res, seed)
                lots.append((res.samples, sh.quantity_tonnes))
            elif sh.arrived_at is not None:                 # already at the gate: a known arrival
                lots.append((np.full(a.n_samples, hours(sh.arrived_at - now)), sh.quantity_tonnes))
        p_stock = exp_stock = None
        if stock is not None and lots:
            so = stockout_hours(lots, stock)
            p_stock, exp_stock = float((so > 0).mean()), float(so.mean())
        for sh, res, seed in results.values():
            prev = latest_prediction(db, sh.id)
            conf, scale, age = data_confidence(sh, now, a)
            idx = risk_index(res.p_late, p_stock, a.w_late, a.w_stock)
            cat = risk_category(idx, res.p_late, p_stock, a.band_medium_from, a.band_high_from)
            p50_at = plus_hours(now, res.p50)
            chips = [{"key": k, "label": CHIP_LABELS[k], "hours": round(v, 4)} for k, v in res.components.items()]
            transporter = db.get(m.Transporter, sh.transporter_id)
            notes = [f"Data confidence: {conf}" + (f" (telemetry is {age:.0f} min old; uncertainty widened x{scale:.2f})"
                                                   if conf == "STALE" else "")]
            if abs(transporter.sigma_factor - 1.0) > 1e-9:
                notes.append(f"Transporter variability factor x{transporter.sigma_factor:.2f} (widens the range, not the mean)")
            change = None
            if prev is not None:
                # Same seed => same variate matrix, so the P50 difference is attributable to the trigger.
                change = {"hours": round(hours(p50_at - prev.p50_at), 3), "since": iso(prev.created_sim_at),
                          "trigger": trigger_label or trigger, "trigger_event_id": trigger_event_id}
            reasons = {
                "explains": "mean contribution (hours) versus the deterministic baseline; P50/P90 are shown separately",
                "baseline_at": iso(plus_hours(now, res.baseline_h)), "mean_at": iso(plus_hours(now, res.mean)),
                "chips": chips, "notes": notes, "p50_change": change,
                "expected_late_hours": round(res.expected_late_hours, 4),
                "expected_stockout_hours": None if exp_stock is None else round(exp_stock, 4),
                "stock_available": stock is not None,
                "stock_depletion_at": iso(plus_hours(now, stock.depletion_rel_h)) if stock else None,
                "telemetry_age_min": None if age is None else round(age, 1),
                "method": f"Monte Carlo, N={res.n}. Probabilities carry a sampling error of up to about 2.2 "
                          f"percentage points. Assumed distributions; not a trained ML model.",
            }
            pred = m.Prediction(
                shipment_id=sh.id, created_sim_at=now, seed=seed, n=res.n,
                p10_at=plus_hours(now, res.p10), p50_at=p50_at, p90_at=plus_hours(now, res.p90),
                p_late=res.p_late, p_stockout=p_stock, risk_index=idx, risk_category=cat,
                previous_p50_at=prev.p50_at if prev else None, trigger=trigger_label or trigger,
                trigger_event_id=trigger_event_id, reasons_json=reasons, data_confidence=conf,
                state_version=sh.state_version, assumptions_version=av)
            db.add(pred)
            db.flush()
            count += 1
            if raise_alerts:
                alert_svc.evaluate(db, sh, order, prev, pred, res.components, now, a)
    return count
