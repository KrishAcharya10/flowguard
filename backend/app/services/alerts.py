"""Alerts (spec 4.7, O4). An alert is not an executed intervention.

Coordinators get the specific suggested action and its operational reason.
Customers get a safe plain-language message with no internal cost data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from ..engine.risk import ORDER
from .core import iso

CUSTOMER_REASON = {
    "closure_wait": "A road closure on the planned route may delay your delivery.",
    "slowdown": "Heavy congestion on the planned route may delay your delivery.",
    "repair_wait": "A vehicle issue may delay your delivery.",
    "gate_queue": "Longer than usual waiting at the plant may delay your delivery.",
    "handling_deviation": "Longer than usual loading at the plant may delay your delivery.",
    "dispatch_delay": "A later than planned dispatch may delay your delivery.",
    "variability": "Updated travel conditions may delay your delivery.",
}
COORD_REASON = {
    "closure_wait": "road closure wait", "slowdown": "route slowdown", "repair_wait": "vehicle repair wait",
    "gate_queue": "plant gate queue", "handling_deviation": "slow loading", "dispatch_delay": "late dispatch",
    "variability": "travel variability",
}


def create(db: Session, *, audience_role: str, shipment: Optional[m.Shipment], order: Optional[m.Order], kind: str,
           severity: str, title: str, message: str, suggested_action: str, dedupe_key: str, now: datetime,
           customer_id: Optional[str] = None, data: Optional[dict] = None) -> Optional[m.Alert]:
    if db.query(m.Alert.id).filter(m.Alert.dedupe_key == dedupe_key).first():
        return None                                         # deduplicated
    al = m.Alert(audience_role=audience_role, customer_id=customer_id,
                 shipment_id=shipment.id if shipment else None, order_id=order.id if order else None,
                 kind=kind, severity=severity, title=title, message=message, suggested_action=suggested_action,
                 data_json=data or {}, dedupe_key=dedupe_key, created_sim_at=now)
    db.add(al)
    db.flush()
    return al


def _suggest(db: Session, sh: m.Shipment, order: m.Order, now: datetime, a: Assumptions) -> tuple[str, str, str]:
    """Quick actionable suggestion (no stability run). Returns (code, coordinator text, customer text)."""
    from . import warroom as wr
    try:
        case, plans = wr.run_case(db, sh, order, now, a, with_stability=False)
    except Exception:  # a suggestion must never block the alert itself
        return "REVIEW", "Open the War Room to compare options.", \
            "Our logistics team is reviewing the shipment; no action is required from you."
    rec = case["recommendation"]
    opts = {o["code"]: o for o in case["options"]}
    cont = opts["CONTINUE"]
    if rec["code"] == "REROUTE":
        o = opts["REROUTE"]
        return ("REROUTE",
                f"Suggested action: REROUTE via {plans['REROUTE']['alt_route_name']}. Modelled P(late) falls from "
                f"{cont['p_late']:.0%} to {o['p_late']:.0%} for Rs {o['freight']:,.0f} extra freight. "
                f"Open the War Room to compare Continue, Reroute and Split before approving.",
                "Our logistics team is evaluating an alternate route; no action is required from you.")
    if rec["code"] == "SPLIT":
        o = opts["SPLIT"]
        return ("SPLIT",
                f"Suggested action: SPLIT SHIPMENT ({plans['SPLIT']['urgent_qty_t']:g} t urgent on a second vehicle). "
                f"Modelled P(stock-out) falls from {cont['p_stockout'] or 0:.0%} to {o['p_stockout'] or 0:.0%}. "
                f"Open the War Room to compare options before approving.",
                "Our logistics team is evaluating sending an urgent part of your order first; no action is required from you.")
    if rec["code"] == "NO_FEASIBLE_OPTION":
        return ("ESCALATE", "No option meets the hard constraints. Open the War Room and escalate.",
                "Our logistics team is reviewing options for your delivery; no action is required from you.")
    return ("CONTINUE", "Suggested action: CONTINUE the current plan. No option beats it by a meaningful modelled "
            "margin (late is not the same as costly). Open the War Room to see the comparison.",
            "Our logistics team is monitoring the shipment closely; no action is required from you.")


def evaluate(db: Session, sh: m.Shipment, order: m.Order, prev: Optional[m.Prediction], pred: m.Prediction,
             components: dict, now: datetime, a: Assumptions) -> None:
    prev_cat = prev.risk_category if prev else "LOW"
    prev_late = prev.p_late if prev else 0.0
    prev_stock = (prev.p_stockout or 0.0) if prev else 0.0
    kinds = []
    if ORDER[pred.risk_category] > ORDER[prev_cat]:
        kinds.append("RISK_UP")
    if prev_late < 0.50 <= pred.p_late:
        kinds.append("P_LATE_50")
    if pred.p_stockout is not None and prev_stock < 0.20 <= pred.p_stockout:
        kinds.append("P_STOCKOUT_20")
    wait = components.get("closure_wait", 0) + components.get("repair_wait", 0) + components.get("slowdown", 0)
    prev_wait = 0.0
    if prev:
        prev_wait = sum(c["hours"] for c in prev.reasons_json.get("chips", [])
                        if c["key"] in ("closure_wait", "repair_wait", "slowdown"))
    if wait >= a.alert_expected_wait_h > prev_wait:
        kinds.append("DISRUPTION_WAIT")
    # fire only on a category change or an index move of at least 10
    if prev and pred.risk_category == prev.risk_category and abs(pred.risk_index - prev.risk_index) < 10:
        kinds = []
    stale = (order.priority == "HIGH" and pred.data_confidence == "STALE"
             and (prev is None or prev.data_confidence != "STALE"))

    if stale:
        create(db, audience_role="COORDINATOR", shipment=sh, order=order, kind="STALE_HIGH_PRIORITY", severity="MEDIUM",
               title=f"Stale position data: {sh.id} (high priority)",
               message="No telemetry has been reported recently. The map shows the last REPORTED position; "
                       "the ETA range has been widened.",
               suggested_action="Contact the transporter to confirm the vehicle position.",
               data={"risk_category": pred.risk_category, "data_confidence": "STALE"},
               dedupe_key=f"{sh.id}|STALE|sv{sh.state_version}|COORDINATOR", now=now)
    if not kinds or pred.risk_category == "LOW":
        return

    top = max((k for k in components if k != "variability"), key=lambda k: components[k], default="variability")
    if components.get(top, 0) < 0.25:
        top = "variability"
    code, coord_action, customer_action = _suggest(db, sh, order, now, a)
    sev = "HIGH" if pred.risk_category == "HIGH" else "MEDIUM"
    ps = "n/a" if pred.p_stockout is None else f"{pred.p_stockout:.0%}"
    key = f"{sh.id}|{'+'.join(kinds)}|{pred.risk_category}|sv{sh.state_version}"
    create(db, audience_role="COORDINATOR", shipment=sh, order=order, kind="+".join(kinds), severity=sev,
           title=f"Delay risk {pred.risk_category}: {sh.id}",
           message=f"P(late) {pred.p_late:.0%}, P(stock-out) {ps}, risk index {pred.risk_index}. "
                   f"Main driver (mean contribution): {COORD_REASON[top]} +{components.get(top, 0):.1f} h.",
           suggested_action=coord_action,
           data={"risk_category": pred.risk_category, "p_late": pred.p_late, "p_stockout": pred.p_stockout,
                 "risk_index": pred.risk_index, "eta_p50": iso(pred.p50_at), "eta_p10": iso(pred.p10_at),
                 "eta_p90": iso(pred.p90_at), "promised_at": iso(order.promised_at), "suggestion_code": code},
           dedupe_key=key + "|COORDINATOR", now=now)
    # customer-safe: no costs, penalties, stock rates or transporter details
    create(db, audience_role="CUSTOMER", customer_id=order.customer_id, shipment=sh, order=order, kind="DELAY_RISK",
           severity=sev, title=f"Delivery update for order {order.id}",
           message=CUSTOMER_REASON[top], suggested_action=customer_action,
           data={"risk_level": pred.risk_category.capitalize(), "eta_from": iso(pred.p10_at), "eta_to": iso(pred.p90_at),
                 "promised_at": iso(order.promised_at), "updated_expected_delivery": iso(pred.p50_at)},
           dedupe_key=key + "|CUSTOMER", now=now)
