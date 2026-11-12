"""Read models: ORM rows -> API schemas. No Monte Carlo runs here (GETs only read)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..assumptions import Assumptions
from . import reports as report_svc
from . import runtime
from . import warroom as wr
from .alerts import CUSTOMER_REASON
from .core import hours, latest_prediction
from .mapping import data_confidence, inventory_for
from .paths import get_path, total_km
from .shipments import LABEL, NEXT

STOCK_NOTE = ("Customer stock data is fictional; a real deployment needs customer consent to share "
              "coarse stock-cover data.")
MAP_CAPTION = "Illustrative routes. Positions are simulated."


def prediction_out(p: Optional[m.Prediction]) -> Optional[s.PredictionOut]:
    if p is None:
        return None
    return s.PredictionOut(
        id=p.id, shipment_id=p.shipment_id, created_sim_at=p.created_sim_at, n=p.n, p10_at=p.p10_at, p50_at=p.p50_at,
        p90_at=p.p90_at, p_late=p.p_late, p_stockout=p.p_stockout, risk_index=p.risk_index,
        risk_category=p.risk_category, previous_p50_at=p.previous_p50_at, trigger=p.trigger,
        trigger_event_id=p.trigger_event_id, reasons=s.Reasons(**p.reasons_json), data_confidence=p.data_confidence,
        state_version=p.state_version, assumptions_version=p.assumptions_version)


def milestones(db: Session, sh: m.Shipment) -> list[s.MilestoneOut]:
    times: dict[str, datetime] = {}
    for ev in (db.query(m.ShipmentEvent).filter(m.ShipmentEvent.shipment_id == sh.id,
                                                m.ShipmentEvent.type.in_(("MILESTONE", "POD")))
               .order_by(m.ShipmentEvent.id)):
        if ev.state:
            times[ev.state] = ev.occurred_at
    cur = m.STATES.index(sh.state)
    return [s.MilestoneOut(state=st, label=LABEL[st], occurred_at=times.get(st), done=i <= cur, current=i == cur)
            for i, st in enumerate(m.STATES)]


def bucket_of(sh: m.Shipment, order: m.Order, pred: Optional[m.Prediction], now: datetime, a: Assumptions) -> str:
    if sh.disposition == "SPLIT_PARENT":
        return "SPLIT_PARENT"
    if sh.state == "DELIVERED":
        return "DELIVERED"
    if sh.state == "ARRIVED_AT_CUSTOMER_GATE":
        return "ARRIVED_PENDING_POD"
    if hours(now - order.promised_at) > a.grace_hours:
        return "LATE"
    return "AT_RISK" if pred and pred.risk_category in ("MEDIUM", "HIGH") else "ON_TRACK"


def shipment_fields(db: Session, sh: m.Shipment, now: datetime, a: Assumptions) -> dict:
    order = db.get(m.Order, sh.order_id)
    route = db.get(m.Route, sh.route_id)
    alt = db.get(m.Route, sh.active_alternative_route_id) if sh.active_alternative_route_id else None
    driver = db.get(m.User, sh.driver_user_id) if sh.driver_user_id else None
    pred = latest_prediction(db, sh.id) if sh.disposition == "ACTIVE" and sh.arrived_at is None else None
    _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    open_cases = db.info.get("open_cases")
    if open_cases is None:
        open_cases = {sid: iid for iid, sid in db.query(m.Intervention.id, m.Intervention.shipment_id)
                      .filter(m.Intervention.status == "AWAITING_APPROVAL")}
        db.info["open_cases"] = open_cases
    case = (open_cases[sh.id],) if sh.id in open_cases else None
    return dict(
        id=sh.id, order_id=sh.order_id, customer_id=order.customer_id,
        customer_name=db.get(m.Customer, order.customer_id).name, product_code=order.product_code,
        priority=order.priority, transporter_id=sh.transporter_id,
        transporter_name=db.get(m.Transporter, sh.transporter_id).name,
        driver_name=driver.display_name if driver else None, vehicle_label=sh.vehicle_label, route_id=sh.route_id,
        route_name=route.name, destination_name=route.destination_name,
        active_alternative_route_id=sh.active_alternative_route_id, alternative_route_name=alt.name if alt else None,
        parent_shipment_id=sh.parent_shipment_id, lot_type=sh.lot_type, quantity_tonnes=sh.quantity_tonnes,
        state=sh.state, state_label=LABEL[sh.state], disposition=sh.disposition, state_version=sh.state_version,
        bucket=bucket_of(sh, order, pred, now, a), planned_loading_at=sh.planned_loading_at,
        planned_arrival_at=sh.planned_arrival_at, promised_at=order.promised_at, departed_at=sh.departed_at,
        arrived_at=sh.arrived_at, delivered_at=sh.delivered_at, last_telemetry_at=sh.last_telemetry_at,
        last_lat=sh.last_lat, last_lon=sh.last_lon, last_progress_km=sh.last_progress_km or 0.0,
        total_km=total_km(segs), sla_penalty_per_late_hour=order.sla_penalty_per_late_hour,
        prediction=prediction_out(pred), open_case_id=case[0] if case else None)


def shipment_out(db, sh, now, a) -> s.ShipmentOut:
    return s.ShipmentOut(**shipment_fields(db, sh, now, a))


def stock_out(db: Session, order: m.Order) -> s.StockOut:
    inv = inventory_for(db, order)
    if inv is None:
        return s.StockOut(available=False, note="Stock data unavailable. Risk uses P(late) only.")
    from .core import plus_hours
    return s.StockOut(available=True, note=STOCK_NOTE, inventory_tonnes=inv.inventory_tonnes,
                      measured_at=inv.measured_at, consumption_tph=inv.consumption_tph,
                      unloading_hours=inv.unloading_hours,
                      depletion_at=plus_hours(inv.measured_at, inv.inventory_tonnes / inv.consumption_tph))


def shipment_detail(db: Session, sh: m.Shipment, now: datetime, a: Assumptions) -> s.ShipmentDetailOut:
    from .disruptions import affected_shipments
    order = db.get(m.Order, sh.order_id)
    dis = [d for d in db.query(m.Disruption).filter(m.Disruption.status == "ACTIVE").order_by(m.Disruption.id)
           if any(x.id == sh.id for x in affected_shipments(db, d))]
    children = [c.id for c in db.query(m.Shipment).filter(m.Shipment.parent_shipment_id == sh.id).order_by(m.Shipment.id)]
    return s.ShipmentDetailOut(**shipment_fields(db, sh, now, a), milestones=milestones(db, sh),
                               stock=stock_out(db, order),
                               disruptions=[s.DisruptionOut.model_validate(d) for d in dis],
                               child_shipment_ids=children)


# ---------- customer-safe ----------
def customer_shipment(db: Session, sh: m.Shipment, now: datetime, a: Assumptions) -> s.CustomerShipmentOut:
    order = db.get(m.Order, sh.order_id)
    route = db.get(m.Route, sh.route_id)
    pts, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    pred = latest_prediction(db, sh.id) if sh.arrived_at is None else None
    pos = None
    if sh.last_lat is not None and sh.last_telemetry_at is not None and sh.state in ("IN_TRANSIT", "ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
        pos = s.CustomerPosition(lat=sh.last_lat, lon=sh.last_lon, reported_at=sh.last_telemetry_at)
    ids = [x.id for x in db.query(m.Shipment).filter(m.Shipment.order_id == order.id)]
    applied = (db.query(m.Intervention).filter(m.Intervention.shipment_id.in_(ids),
                                               m.Intervention.status.in_(("APPLIED", "COMPLETED")))
               .order_by(m.Intervention.id.desc()).first())
    note = None
    if applied and applied.impact_json:
        note = {"REROUTE": "Your delivery has been rerouted to protect the delivery time.",
                "SPLIT": "Your order is being delivered in two parts; an urgent part has been prioritised.",
                "CONTINUE": "Our logistics team reviewed this delivery; it continues on the current plan."}.get(
            applied.impact_json.get("option"))
    conf = data_confidence(sh, now, a)[0] if sh.state == "IN_TRANSIT" else None
    return s.CustomerShipmentOut(
        id=sh.id, order_id=order.id, product_code=order.product_code, quantity_tonnes=sh.quantity_tonnes,
        lot_type=sh.lot_type, state=sh.state, state_label=LABEL[sh.state], promised_at=order.promised_at,
        updated_expected_delivery=pred.p50_at if pred else None, eta_from=pred.p10_at if pred else None,
        eta_to=pred.p90_at if pred else None, risk_level=pred.risk_category.capitalize() if pred else None,
        data_confidence=conf, route_name="Planned delivery route", destination_name=route.destination_name,
        route_points=[s.CustomerPoint(name=p.name, lat=p.lat, lon=p.lon) for p in pts],
        last_reported_position=pos, milestones=milestones(db, sh), arrived_at=sh.arrived_at,
        delivered_at=sh.delivered_at, action_note=note,
        stock_note=STOCK_NOTE if inventory_for(db, order) else "Stock data unavailable",
        progress_pct=_progress_pct(sh, segs), delay_explanation=_delay_explanation(pred, conf),
        pod_status=("Proof of delivery signed" if sh.state == "DELIVERED" else
                    "Arrived. Waiting for proof of delivery" if sh.state == "ARRIVED_AT_CUSTOMER_GATE" else
                    "Not yet delivered"),
        pod_recipient=sh.pod_recipient if sh.state == "DELIVERED" else None, timeline=_customer_timeline(db, sh))


def _progress_pct(sh: m.Shipment, segs) -> int:
    """Share of the road covered, from the last REPORTED position (never an assumed one)."""
    if sh.arrived_at is not None or sh.state in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
        return 100
    if sh.state != "IN_TRANSIT":
        return 0
    return min(99, round(100 * (sh.last_progress_km or 0.0) / max(total_km(segs), 1e-9)))


def _delay_explanation(pred: Optional[m.Prediction], confidence: Optional[str]) -> Optional[str]:
    """Plain-language reason for a delay risk. No costs, penalties, stock or transporter information."""
    if pred is None or pred.risk_category == "LOW":
        return None
    chips = {c["key"]: c["hours"] for c in pred.reasons_json.get("chips", [])}
    top = max((k for k in chips if k != "variability"), key=lambda k: chips[k], default="variability")
    if chips.get(top, 0.0) < 0.25:
        top = "variability"
    text = CUSTOMER_REASON[top] + " Our team is monitoring it and will tell you if anything changes."
    if confidence == "STALE":
        text += " The vehicle has not reported its position recently, so the delivery window is wider than usual."
    return text


CUSTOMER_EVENT_TEXT = {
    "PLANNED": "Order planned", "LOADING": "Loading started at Plant X",
    "AT_PLANT_GATE": "Loaded and waiting at the plant gate", "IN_TRANSIT": "Left Plant X, on its way to you",
    "ARRIVED_AT_CUSTOMER_GATE": "Arrived at your receiving gate", "DELIVERED": "Delivered. Proof of delivery recorded",
}


def _customer_timeline(db: Session, sh: m.Shipment) -> list[s.CustomerEvent]:
    """Customer-safe event history: milestones, progress, route changes. Internal notes are never copied."""
    out: list[s.CustomerEvent] = []
    for ev in (db.query(m.ShipmentEvent).filter(m.ShipmentEvent.shipment_id == sh.id)
               .order_by(m.ShipmentEvent.occurred_at, m.ShipmentEvent.id)):
        text = None
        if ev.type == "MILESTONE" and ev.state in CUSTOMER_EVENT_TEXT:
            text = CUSTOMER_EVENT_TEXT[ev.state]
        elif ev.type == "POSITION":
            text = ev.note.replace("Latest position reported: ", "Position update: ")
        elif ev.type == "DISRUPTION_START" and "Telemetry" not in ev.note:
            text = "A disruption was detected affecting your delivery. We are re-checking the delivery time."
        elif ev.type == "DISRUPTION_END" and "Telemetry" not in ev.note:
            text = "The disruption has cleared."
        elif ev.type == "REROUTED":
            text = "Your delivery was rerouted to protect the delivery time."
        elif ev.type == "SPLIT":
            text = "Your order was split so an urgent part reaches you first."
        elif ev.type == "DECISION":
            text = "Our team reviewed your delivery and kept the current plan."
        if text and not (out and out[-1].text == text):
            out.append(s.CustomerEvent(at=ev.occurred_at, kind=ev.type, text=text))
    return out[-14:]


def customer_history(db: Session, customer_id: str, a: Assumptions) -> list[s.CustomerHistoryItem]:
    rows = (db.query(m.Shipment, m.Order).join(m.Order, m.Order.id == m.Shipment.order_id)
            .filter(m.Order.customer_id == customer_id, m.Shipment.disposition == "ACTIVE",
                    m.Shipment.arrived_at.isnot(None)).order_by(m.Shipment.arrived_at.desc(), m.Shipment.id).limit(40))
    out = []
    for sh, o in rows:
        gap = hours(sh.arrived_at - o.promised_at)
        out.append(s.CustomerHistoryItem(
            shipment_id=sh.id, order_id=o.id, product_code=o.product_code, quantity_tonnes=sh.quantity_tonnes,
            promised_at=o.promised_at, arrived_at=sh.arrived_at, delivered_at=sh.delivered_at,
            on_time=gap <= a.grace_hours, hours_vs_promise=round(gap, 2)))
    return out


def driver_history(db: Session, driver_id: int, a: Assumptions) -> list[s.DriverHistoryItem]:
    rows = (db.query(m.Shipment, m.Order).join(m.Order, m.Order.id == m.Shipment.order_id)
            .filter(m.Shipment.driver_user_id == driver_id, m.Shipment.disposition == "ACTIVE",
                    m.Shipment.arrived_at.isnot(None)).order_by(m.Shipment.arrived_at.desc(), m.Shipment.id).limit(30))
    out = []
    for sh, o in rows:
        out.append(s.DriverHistoryItem(
            shipment_id=sh.id, destination_name=db.get(m.Route, sh.route_id).destination_name,
            product_code=o.product_code, quantity_tonnes=sh.quantity_tonnes, promised_at=o.promised_at,
            arrived_at=sh.arrived_at, delivered_at=sh.delivered_at,
            on_time=hours(sh.arrived_at - o.promised_at) <= a.grace_hours))
    return out


def clock_out(st: m.SimulationState) -> s.ClockOut:
    return s.ClockOut(sim_now=st.sim_now, speed=st.speed, paused=st.paused, clock_version=st.clock_version,
                      pause_on_alert=runtime.RUNNER["pause_on_alert"])


def customer_order(db: Session, order: m.Order, now: datetime, a: Assumptions) -> s.CustomerOrderOut:
    from .core import leaf_shipments
    leaves = leaf_shipments(db, order.id)
    ships = [customer_shipment(db, x, now, a) for x in leaves]
    etas = [x.updated_expected_delivery for x in ships if x.updated_expected_delivery]
    if all(x.state == "DELIVERED" for x in leaves):
        status = "Delivered"
    elif all(x.arrived_at is not None for x in leaves):
        status = "Arrived at your gate"
    elif any(x.state == "IN_TRANSIT" for x in leaves):
        status = "In transit"
    else:
        status = "Being prepared at Plant X"
    return s.CustomerOrderOut(id=order.id, product_code=order.product_code, quantity_tonnes=order.quantity_tonnes,
                              promised_at=order.promised_at, updated_expected_delivery=max(etas) if etas else None,
                              status=status, shipments=ships)


def customer_alert(al: m.Alert) -> s.CustomerAlertOut:
    d = al.data_json or {}
    return s.CustomerAlertOut(id=al.id, shipment_id=al.shipment_id, order_id=al.order_id, severity=al.severity,
                              title=al.title, message=al.message, suggested_action=al.suggested_action,
                              risk_level=d.get("risk_level"), eta_from=d.get("eta_from"), eta_to=d.get("eta_to"),
                              promised_at=d.get("promised_at"),
                              updated_expected_delivery=d.get("updated_expected_delivery"),
                              acknowledged=al.acknowledged, created_sim_at=al.created_sim_at)


# ---------- transporter ----------
def driver_shipment(db: Session, sh: m.Shipment) -> s.DriverShipmentOut:
    order = db.get(m.Order, sh.order_id)
    route = db.get(m.Route, sh.route_id)
    alt = db.get(m.Route, sh.active_alternative_route_id) if sh.active_alternative_route_id else None
    nxt = NEXT.get(sh.state)
    _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    total = total_km(segs)
    rep_ = report_svc.active_report(db, sh)
    pod = (db.query(m.Document).filter(m.Document.shipment_id == sh.id, m.Document.kind == "POD",
                                       m.Document.is_current.is_(True)).first())
    return s.DriverShipmentOut(
        id=sh.id, order_id=order.id, product_code=order.product_code, quantity_tonnes=sh.quantity_tonnes,
        lot_type=sh.lot_type, vehicle_label=sh.vehicle_label, route_name=route.name,
        alternative_route_name=alt.name if alt else None, destination_name=route.destination_name, state=sh.state,
        state_label=LABEL[sh.state], next_state=nxt, next_state_label=LABEL[nxt] if nxt else None,
        planned_loading_at=sh.planned_loading_at, promised_at=order.promised_at, milestones=milestones(db, sh),
        pod_recipient=sh.pod_recipient,
        instruction=f"Route change approved: follow {alt.name}." if alt else None,
        customer_name=db.get(m.Customer, order.customer_id).name, priority=order.priority,
        progress_pct=_progress_pct(sh, segs), progress_km=sh.last_progress_km or 0.0, total_km=total,
        last_reported_at=sh.last_telemetry_at,
        can_report=bool(sh.disposition == "ACTIVE" and sh.state == "IN_TRANSIT" and rep_ is None),
        active_report=None if rep_ is None else ("Breakdown reported" if rep_.kind == "VEHICLE_STOPPAGE"
                                                  else "Road hazard reported"),
        pod_document_id=pod.id if pod else None, pod_document_name=pod.original_filename if pod else None,
        pod_uploaded_at=pod.uploaded_sim_at if pod else None)


# ---------- war room ----------
def _dt(iso_s: str) -> datetime:
    return datetime.fromisoformat(iso_s.replace("Z", ""))


def _ist(iso_s: str) -> str:
    """Display a stored UTC time as Asia/Kolkata (UTC+05:30) for explanation text."""
    from datetime import timedelta
    return (_dt(iso_s) + timedelta(hours=5, minutes=30)).strftime("%H:%M IST")


def case_out(db: Session, iv: m.Intervention) -> s.CaseOut:
    scs = wr.scenarios_of(db, iv)
    by = {x.code: x for x in scs}
    rec = dict(iv.recommendation_json)
    ctx = iv.context_json
    lines: list[str] = []
    cont = by["CONTINUE"].metrics_json
    if rec["code"] == "NO_FEASIBLE_OPTION":
        lines.append("Every eligible option violates at least one hard constraint, so nothing is recommended.")
        lines.append(f"Least-violating option (information only, NOT recommended): {rec['least_violating_code']}.")
        lines.append("Approving any option requires a reason and is logged as CONSTRAINT OVERRIDE.")
    elif rec["code"] == "NO_JUSTIFIED_INTERVENTION":
        lines.append("Late is not the same as costly.")
        lines.append(f"Continue is feasible and no option beats its modelled expected total (Rs {cont['total']:,.0f}) "
                     f"by more than the tie-break threshold (Rs {rec['threshold']:,.0f}).")
        lines.append("Trade-off: an intervention would add certain freight cost for a small modelled benefit.")
    else:
        o = by[rec["code"]].metrics_json
        dh = hours(_dt(cont["p50_at"]) - _dt(o["p50_at"]))
        lines.append(f"Why: lowest modelled expected total among feasible options - Rs {o['total']:,.0f} versus "
                     f"Rs {cont['total']:,.0f} for Continue (advantage Rs {rec['saving_vs_continue']:,.0f}).")
        if rec["code"] == "SPLIT":
            lots = {l["lot_type"]: l for l in o["lots"]}
            u, r = lots["URGENT"], lots["REMAINDER"]
            when = ""
            if ctx.get("stock_depletion_at"):
                gap = hours(_dt(ctx["stock_depletion_at"]) - _dt(u["p50_at"]))
                when = f", {abs(gap):.1f} h {'before' if gap >= 0 else 'after'} the customer's stock runs out"
            lines.append(f"ETA: the urgent {u['quantity_t']:g} t arrives at median {_ist(u['p50_at'])}{when}; "
                         f"the remaining {r['quantity_t']:g} t follows at {_ist(r['p50_at'])} "
                         f"({abs(dh):.1f} h {'earlier' if dh >= 0 else 'later'} than Continue for the whole order).")
        else:
            lines.append(f"ETA difference: median arrival {abs(dh):.1f} h {'earlier' if dh >= 0 else 'later'} than Continue.")
        ps = "n/a" if o["p_stockout"] is None else f"{o['p_stockout']:.0%}"
        lines.append(f"Main risk: P(late) is still {o['p_late']:.0%} and P(stock-out) {ps}.")
        lines.append(f"Trade-off: Rs {o['freight']:,.0f} extra freight is certain; the avoided penalty and "
                     f"stock-out costs are modelled expectations.")
        if not by["CONTINUE"].feasible:
            lines.append("Continue violates a hard constraint: " + "; ".join(v["text"] for v in by["CONTINUE"].violations_json) + ".")
    lines.append(f"Assumptions: SLA Rs {ctx['sla_penalty_per_late_hour']:,.0f} per late hour; stock-out "
                 f"Rs {ctx['stockout_cost_per_hour_rs']:,.0f} per hour; N = {ctx['n_samples']} samples; all rates fictional.")
    rec["explanation"] = lines
    sh = db.get(m.Shipment, iv.shipment_id)
    stale = wr._stale_reason(db, iv, sh) if iv.status == "AWAITING_APPROVAL" else None
    decider = db.get(m.User, iv.decided_by) if iv.decided_by else None
    return s.CaseOut(
        id=iv.id, shipment_id=iv.shipment_id, status=iv.status, recommendation=s.RecommendationOut(**rec),
        stability=s.StabilityOut(**iv.stability_json) if iv.stability_json else None,
        constraints=iv.constraints_json, context=ctx, shipment_state_version=iv.shipment_state_version,
        assumptions_version=iv.assumptions_version, clock_version=iv.clock_version, created_sim_at=iv.created_sim_at,
        scenarios=[s.ScenarioOut(id=x.id, code=x.code, eligible=x.eligible, ineligible_reason=x.ineligible_reason,
                                 feasible=x.feasible,
                                 metrics=s.ScenarioMetrics(**x.metrics_json) if x.eligible else None,
                                 violations=[s.ViolationOut(**v) for v in x.violations_json],
                                 summary=x.plan_json.get("summary", "")) for x in scs],
        selected_scenario_id=iv.selected_scenario_id, decided_sim_at=iv.decided_sim_at,
        decided_by_name=decider.display_name if decider else None, is_override=iv.is_override,
        override_reason=iv.override_reason, impact=iv.impact_json, is_stale=stale is not None, stale_reason=stale)
