"""KPIs and analytics (spec 4.10 / 4.11). Everything is computed from database records.

On-time is decided at CUSTOMER-GATE ARRIVAL, per ORDER (every leaf lot by promised_at + grace).
Historical arrivals and predictions are never mixed in one denominator.
Transporter analytics are by COMPANY, never by individual driver.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from .core import ACTIVE_STATES, hours, latest_prediction

IMPACT_LABEL = "MODELLED - ILLUSTRATIVE SCENARIO, NOT VERIFIED PLANT X OR LYB PERFORMANCE"
WINDOW_DAYS = 56


def active_buckets(db: Session, now: datetime, a: Assumptions) -> dict:
    """LATE / AT_RISK / ON_TRACK are mutually exclusive and sum to lots not yet at the customer gate."""
    rows = (db.query(m.Shipment, m.Order).join(m.Order, m.Order.id == m.Shipment.order_id)
            .filter(m.Shipment.is_historical.is_(False), m.Shipment.disposition == "ACTIVE").all())
    out = {"LATE": 0, "AT_RISK": 0, "ON_TRACK": 0, "ARRIVED_PENDING_POD": 0, "DELIVERED": 0}
    by_id = {}
    for sh, order in rows:
        if sh.state == "DELIVERED":
            b = "DELIVERED"
        elif sh.state == "ARRIVED_AT_CUSTOMER_GATE":
            b = "ARRIVED_PENDING_POD"
        elif now > order.promised_at + timedelta(hours=a.grace_hours):
            b = "LATE"
        else:
            p = latest_prediction(db, sh.id)
            b = "AT_RISK" if p and p.risk_category in ("MEDIUM", "HIGH") else "ON_TRACK"
        out[b] += 1
        by_id[sh.id] = b
    out["active_total"] = out["LATE"] + out["AT_RISK"] + out["ON_TRACK"]
    return {"counts": out, "by_shipment": by_id}


def completed_orders(db: Session, now: datetime, a: Assumptions, days: int = WINDOW_DAYS) -> list[dict]:
    """Orders whose every non-parent leaf lot has reached the customer gate inside the window."""
    since = now - timedelta(days=days)
    rows = (db.query(m.Shipment, m.Order).join(m.Order, m.Order.id == m.Shipment.order_id)
            .filter(m.Shipment.disposition == "ACTIVE").all())      # SPLIT_PARENT rows excluded
    lots = defaultdict(list)
    orders = {}
    for sh, order in rows:
        lots[order.id].append(sh)
        orders[order.id] = order
    out = []
    for oid, shs in lots.items():
        if any(s.arrived_at is None for s in shs):
            continue                                                # still in transit: excluded
        last = max(s.arrived_at for s in shs)
        if not (since <= last <= now):
            continue
        order = orders[oid]
        deadline = order.promised_at + timedelta(hours=a.grace_hours)
        out.append({"order_id": oid, "route_id": shs[0].route_id, "transporter_id": shs[0].transporter_id,
                    "customer_id": order.customer_id, "arrived_at": last, "on_time": last <= deadline,
                    "late_hours": max(0.0, hours(last - order.promised_at)), "shipment_ids": [s.id for s in shs]})
    return out


def _kpi(orders: list[dict]) -> dict:
    n = len(orders)
    late = [o for o in orders if not o["on_time"]]
    return {"orders_completed": n, "orders_on_time": n - len(late),
            "on_time_pct": None if n == 0 else round(100.0 * (n - len(late)) / n, 1),
            "average_delay_hours_late_orders": None if not late else round(sum(o["late_hours"] for o in late) / len(late), 2)}


def overview(db: Session, now: datetime, a: Assumptions) -> dict:
    done = completed_orders(db, now, a)
    buckets = active_buckets(db, now, a)["counts"]
    # predicted on-time: shown separately, never mixed with arrivals
    active = (db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False), m.Shipment.disposition == "ACTIVE",
                                          m.Shipment.state.in_(ACTIVE_STATES)).all())
    preds = [p for p in (latest_prediction(db, s.id) for s in active) if p]
    predicted = None if not preds else round(100.0 * sum(1 - p.p_late for p in preds) / len(preds), 1)
    # warning lead time: promised_at minus first HIGH alert, only for lots predicted late or breached
    leads = []
    for sh in active:
        order = db.get(m.Order, sh.order_id)
        p = latest_prediction(db, sh.id)
        if not ((p and p.p_late >= 0.5) or now > order.promised_at):
            continue
        first = (db.query(m.Alert).filter(m.Alert.shipment_id == sh.id, m.Alert.severity == "HIGH",
                                          m.Alert.audience_role == "COORDINATOR").order_by(m.Alert.id).first())
        if first:
            leads.append(hours(order.promised_at - first.created_sim_at))
    # operational headline numbers for the Control Tower (active = not yet at the customer gate)
    delayed = high_risk = 0
    gaps = []
    for sh in active:
        order = db.get(m.Order, sh.order_id)
        p = latest_prediction(db, sh.id)
        due = order.promised_at + timedelta(hours=a.grace_hours)
        if now > due or (p and p.p50_at > due):
            delayed += 1
        if p and p.risk_category == "HIGH":
            high_risk += 1
        if p:
            gaps.append(max(0.0, hours(p.p50_at - order.promised_at)))
    return {
        "active_orders": len({s.order_id for s in active}), "active_shipments": len(active),
        "delayed_shipments": delayed, "high_risk_shipments": high_risk,
        "avg_predicted_delay_hours": None if not gaps else round(sum(gaps) / len(gaps), 2),
        "window_days": WINDOW_DAYS, **_kpi(done), "buckets": buckets,
        "predicted_on_time_pct_active": predicted,
        "warning_lead_time_hours": None if not leads else round(sum(leads) / len(leads), 2),
        "warning_lead_time_note": "promised_at minus first HIGH alert, for lots predicted late or breached. "
                                  "Baseline assumption: without the tool, customers learn at the breach (lead time 0).",
        "definition": "On-time = every lot of the order reached the customer gate by promised_at + grace. "
                      "Orders still in transit are excluded.",
    }


def by_dimension(db: Session, now: datetime, a: Assumptions, dim: str) -> list[dict]:
    done = completed_orders(db, now, a)
    names = {r.id: r.name for r in db.query(m.Route)} if dim == "route_id" else {t.id: t.name for t in db.query(m.Transporter)}
    groups = defaultdict(list)
    for o in done:
        groups[o[dim]].append(o)
    ship_dim = {}
    for o in done:
        for sid in o["shipment_ids"]:
            ship_dim[sid] = o[dim]
    delay_h = defaultdict(float)
    for de in db.query(m.DelayEvent):
        if de.shipment_id in ship_dim:
            delay_h[ship_dim[de.shipment_id]] += de.hours
    return [{"id": k, "name": names.get(k, k), **_kpi(v), "attributed_delay_hours": round(delay_h[k], 2)}
            for k, v in sorted(groups.items())]


def delay_causes(db: Session, now: datetime, a: Assumptions) -> dict:
    """Per cause: shipments affected and attributed hours, by route and by transporter company."""
    done = completed_orders(db, now, a)
    ship = {}
    for o in done:
        for sid in o["shipment_ids"]:
            ship[sid] = o
    routes = {r.id: r.name for r in db.query(m.Route)}
    trans = {t.id: t.name for t in db.query(m.Transporter)}
    agg = {"route": defaultdict(lambda: [set(), 0.0]), "transporter": defaultdict(lambda: [set(), 0.0]),
           "total": defaultdict(lambda: [set(), 0.0])}
    for de in db.query(m.DelayEvent):
        o = ship.get(de.shipment_id)
        if o is None:
            continue
        for kind, key in (("route", (o["route_id"], de.cause)), ("transporter", (o["transporter_id"], de.cause)),
                          ("total", ("ALL", de.cause))):
            agg[kind][key][0].add(de.shipment_id)
            agg[kind][key][1] += de.hours

    def rows(kind, names):
        return [{"id": k[0], "name": names.get(k[0], k[0]), "cause": k[1], "shipments_affected": len(v[0]),
                 "attributed_hours": round(v[1], 2)} for k, v in sorted(agg[kind].items())]
    return {"by_route": rows("route", routes), "by_transporter": rows("transporter", trans),
            "totals": rows("total", {"ALL": "All"}),
            "note": "Attributed hours sum to realised delay = max(0, arrived_at - planned_arrival_at) per lot."}


def panel_b(a: Assumptions) -> dict:
    affected = a.annual_shipments * a.delay_rate
    mitigated = affected * a.mitigable_share
    interventions = mitigated / a.success_rate
    gross = mitigated * a.avoidable_hours * a.cost_per_late_hour_rs
    cost = interventions * a.avg_intervention_cost_rs
    return {
        "inputs": {k: getattr(a, k) for k in ("annual_shipments", "delay_rate", "mitigable_share", "success_rate",
                                              "avoidable_hours", "cost_per_late_hour_rs", "avg_intervention_cost_rs")},
        "affected_shipments": affected, "mitigated_shipments": mitigated, "interventions": interventions,
        "gross_modelled_benefit_rs": gross, "intervention_cost_rs": cost, "net_modelled_benefit_rs": gross - cost,
        "break_even_cost_per_late_hour_rs": (a.avg_intervention_cost_rs / a.success_rate) / a.avoidable_hours,
        "formulas": [
            "affected = annual_shipments x delay_rate",
            "mitigated = affected x mitigable_share",
            "interventions = mitigated / success_rate",
            "gross = mitigated x avoidable_hours x cost_per_late_hour",
            "intervention_cost = interventions x avg_intervention_cost",
            "net = gross - intervention_cost (may be negative)",
            "break_even_cost_per_late_hour = (avg_intervention_cost / success_rate) / avoidable_hours",
        ],
    }


def business_impact(db: Session, a: Assumptions) -> dict:
    rows = []
    for iv in (db.query(m.Intervention).filter(m.Intervention.status.in_(("APPLIED", "COMPLETED")))
               .order_by(m.Intervention.id)):
        imp = iv.impact_json or {}
        rows.append({"intervention_id": iv.id, "shipment_id": iv.shipment_id, "option": imp.get("option"),
                     "status": iv.status, "is_override": iv.is_override,
                     "modelled_late_hours_avoided": imp.get("modelled_late_hours_avoided", 0.0),
                     "modelled_cost_difference_rs": imp.get("modelled_cost_difference_rs", 0.0),
                     "incremental_freight_rs": imp.get("incremental_freight_rs", 0.0)})
    return {
        "label": IMPACT_LABEL,
        "panel_a": {
            "title": "This dataset: model expectations at approval time (not realised savings)",
            "interventions": rows,
            "total_modelled_late_hours_avoided": sum(r["modelled_late_hours_avoided"] for r in rows),
            "total_modelled_cost_difference_rs": sum(r["modelled_cost_difference_rs"] for r in rows),
            "total_incremental_freight_rs": sum(r["incremental_freight_rs"] for r in rows),
            "formulas": ["hours avoided = E[late hours | Continue] - E[late hours | chosen]",
                         "modelled cost difference = Total_Continue - Total_chosen (freight shown separately)"],
        },
        "panel_b": panel_b(a),
    }
