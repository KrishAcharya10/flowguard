"""War Room service: build the three options, store the decision case,
approve / reject with version checks, and apply in ONE transaction (spec 4.8 / 4.9)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from ..engine.contracts import Constraints, CostParams, LotSpec, OptionSpec
from ..engine.warroom import REC_NONE, evaluate_case
from ..seeds import seed_pred
from . import alerts as alert_svc
from .core import (add_event, audit, get_assumptions, hours, iso, leaf_shipments, next_id, plus_hours,
                   sim_state)
from .mapping import active_disruptions, build_inputs, inventory_for, stock_params
from .paths import alternative_topology, entry_km, get_path, total_km

PRE_DEPARTURE = ("PLANNED", "LOADING", "AT_PLANT_GATE")


def root_id(sh: m.Shipment) -> str:
    return sh.parent_shipment_id or sh.id


def constraints_from(a: Assumptions) -> Constraints:
    return Constraints(alpha=a.alpha, max_freight_rs=a.max_incremental_freight_rs,
                       min_urgent_qty_t=a.min_urgent_qty_t, beta=a.beta,
                       tie_pct=a.tie_pct, tie_min_abs_rs=a.tie_min_abs_rs)


def find_alternative(db: Session, sh: m.Shipment) -> Optional[m.Route]:
    return (db.query(m.Route).filter(m.Route.alternative_of_route_id == sh.route_id)
            .order_by(m.Route.id).first())


def reroute_eligibility(db: Session, sh: m.Shipment) -> tuple[bool, str, Optional[m.Route]]:
    if sh.state not in PRE_DEPARTURE + ("IN_TRANSIT",):
        return False, "Shipment has already reached the customer gate", None
    if sh.active_alternative_route_id:
        return False, "Shipment is already on the alternative route", None
    alt = find_alternative(db, sh)
    if alt is None:
        return False, "No alternative route is defined for this route", None
    ei, _, why = alternative_topology(db, alt)
    if ei is None:
        return False, why, None
    pts, _ = get_path(db, sh.route_id)
    if sh.state == "IN_TRANSIT" and (sh.last_progress_km or 0.0) >= entry_km(db, sh.route_id, alt) - 1e-6:
        return False, f"Vehicle has already passed the decision node ({pts[ei].name})", None
    return True, "", alt


def build_option_specs(db: Session, sh: m.Shipment, order: m.Order, now: datetime, a: Assumptions,
                       disruptions: list[m.Disruption]):
    """Returns (specs, plans, stock). Every option uses the same mapping and the same engine."""
    stock = stock_params(db, order, now)
    inv = inventory_for(db, order)
    lot = sh.lot_type
    _, cur_segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    specs, plans = [], {}

    specs.append(OptionSpec("CONTINUE", True, lots=(LotSpec(lot, sh.quantity_tonnes,
                 build_inputs(db, sh, order, now, a, disruptions)),)))
    plans["CONTINUE"] = {"summary": "Keep the current plan"}

    ok, why, alt = reroute_eligibility(db, sh)
    alt_km = None
    if ok:
        _, alt_segs = get_path(db, sh.route_id, alt.id)
        alt_km = total_km(alt_segs)
        extra = max(0.0, alt_km - total_km(cur_segs))
        specs.append(OptionSpec("REROUTE", True, lots=(LotSpec(lot, sh.quantity_tonnes,
                     build_inputs(db, sh, order, now, a, disruptions, alt_route_id=alt.id)),),
                     freight_rs=extra * alt.cost_per_km + a.reroute_fixed_rs, extra_km=extra))
        plans["REROUTE"] = {"summary": f"Reroute via {alt.name}", "alt_route_id": alt.id, "alt_route_name": alt.name}
    else:
        specs.append(OptionSpec("REROUTE", False, why))
        plans["REROUTE"] = {}

    # SPLIT: only before departure; urgent lot on a second (separate, fictional) vehicle
    q = sh.quantity_tonnes
    if inv is not None:
        q_u = max(inv.min_priority_qty_tonnes, inv.consumption_tph * a.split_cover_hours)
    else:
        q_u = max(a.min_urgent_qty_t, q / 3.0)
    q_u = min(q, round(q_u, 3))
    if sh.state not in PRE_DEPARTURE:
        specs.append(OptionSpec("SPLIT", False, "Split is only possible before the vehicle leaves Plant X"))
        plans["SPLIT"] = {}
    elif sh.lot_type != "SINGLE":
        specs.append(OptionSpec("SPLIT", False, "This lot is already part of a split shipment"))
        plans["SPLIT"] = {}
    elif q_u >= q - 1e-9:
        specs.append(OptionSpec("SPLIT", False, "The urgent quantity would be the whole load, so a split adds nothing"))
        plans["SPLIT"] = {}
    else:
        closure_on_path = any(d.kind == "CLOSURE" and f"{d.route_id}:{d.segment_waypoint_id}" in {s.key for s in cur_segs}
                              for d in disruptions)
        urgent_alt = alt.id if (ok and closure_on_path) else sh.active_alternative_route_id
        _, u_segs = get_path(db, sh.route_id, urgent_alt)
        route_cost = (alt.cost_per_km if (ok and closure_on_path) else db.get(m.Route, sh.route_id).cost_per_km)
        lead = a.second_vehicle_lead_h
        # The remainder stays on the ORIGINAL vehicle, so it keeps that vehicle's own delay: a planned start that
        # is still in the future and any late-dispatch offset. It never leaves earlier than the split lead time.
        rem_lead = lead
        if sh.state == "PLANNED":
            own_delay = max(0.0, hours(sh.planned_loading_at - now)) + sum(
                d.dur_mode_h for d in disruptions if d.kind == "DEPARTURE_OFFSET" and d.shipment_id == sh.id)
            rem_lead = max(lead, own_delay)
        specs.append(OptionSpec("SPLIT", True, lots=(
            LotSpec("URGENT", q_u, build_inputs(db, sh, order, now, a, disruptions, alt_route_id=urgent_alt,
                                                as_new_lot="URGENT", lead_h=lead)),
            LotSpec("REMAINDER", q - q_u, build_inputs(db, sh, order, now, a, disruptions,
                                                       as_new_lot="REMAINDER", lead_h=rem_lead))),
            freight_rs=a.second_vehicle_fixed_rs + route_cost * total_km(u_segs), extra_km=total_km(u_segs)))
        plans["SPLIT"] = {"summary": f"Split: {q_u:g} t urgent on a second vehicle, {q - q_u:g} t on the original plan",
                          "urgent_qty_t": q_u, "remainder_qty_t": q - q_u, "urgent_alt_route_id": urgent_alt,
                          "lead_h": lead, "remainder_lead_h": rem_lead}
    return specs, plans, stock


def run_case(db: Session, sh: m.Shipment, order: m.Order, now: datetime, a: Assumptions,
             with_stability: bool = True) -> tuple[dict, dict]:
    st = sim_state(db)
    specs, plans, stock = build_option_specs(db, sh, order, now, a, active_disruptions(db))
    costs = CostParams(order.sla_penalty_per_late_hour, a.stockout_cost_per_hour_rs)
    case = evaluate_case(specs, stock, costs, constraints_from(a), a.n_samples,
                         seed_pred(st.global_seed, root_id(sh)), with_stability)
    return case, plans


def _public_metrics(o: dict, now: datetime) -> dict:
    """Engine output -> stored metrics with absolute timestamps."""
    if not o["eligible"]:
        return {}
    keys = ("p_late", "p_stockout", "exp_late_h", "exp_stockout_h", "p_priority_ok", "freight", "sla_cost",
            "stockout_cost", "total", "extra_km", "urgent_qty_t")
    out = {k: o[k] for k in keys}
    out["p50_at"] = iso(plus_hours(now, o["p50"]))
    out["p90_at"] = iso(plus_hours(now, o["p90"]))
    out["lots"] = [{"lot_type": l["lot_type"], "quantity_t": l["quantity_t"], "p_late": l["p_late"],
                    "p50_at": iso(plus_hours(now, l["p50"])), "p90_at": iso(plus_hours(now, l["p90"]))}
                   for l in o["lots"]]
    return out


def create_case(db: Session, sh: m.Shipment, user: m.User) -> m.Intervention:
    if sh.disposition != "ACTIVE" or sh.state not in PRE_DEPARTURE + ("IN_TRANSIT",):
        raise HTTPException(409, "Scenarios are only available for shipments that have not yet reached the customer gate")
    st = sim_state(db)
    now = st.sim_now
    a, av = get_assumptions(db)
    order = db.get(m.Order, sh.order_id)
    for old in db.query(m.Intervention).filter(m.Intervention.shipment_id == sh.id,
                                               m.Intervention.status == "AWAITING_APPROVAL"):
        old.status = "SUPERSEDED"            # at most one open case per shipment
    case, plans = run_case(db, sh, order, now, a)
    rec = case["recommendation"]
    inv = inventory_for(db, order)
    stock = stock_params(db, order, now)
    iv = m.Intervention(
        shipment_id=sh.id, recommendation_code=rec["code"], recommendation_json=rec,
        stability_json=case["stability"], constraints_json=constraints_from(a).__dict__,
        context_json={
            "promised_at": iso(order.promised_at), "sim_now": iso(now), "n_samples": case["n"],
            "sla_penalty_per_late_hour": order.sla_penalty_per_late_hour,
            "stockout_cost_per_hour_rs": a.stockout_cost_per_hour_rs,
            "stock_available": inv is not None,
            "stock_depletion_at": iso(plus_hours(now, stock.depletion_rel_h)) if stock else None,
            "scope_note": "Single-shipment decision support. Not fleet optimisation.",
        },
        shipment_state_version=sh.state_version, assumptions_version=av, clock_version=st.clock_version,
        created_sim_at=now, created_by=user.id)
    db.add(iv)
    db.flush()
    for o in case["options"]:
        db.add(m.InterventionScenario(
            intervention_id=iv.id, code=o["code"], eligible=o["eligible"],
            ineligible_reason=o.get("ineligible_reason", ""), feasible=o["feasible"],
            metrics_json=_public_metrics(o, now), violations_json=o["violations"], plan_json=plans[o["code"]]))
    if rec["code"] == REC_NONE:
        lines = "; ".join(f"{o['code']}: " + ", ".join(v["text"] for v in o["violations"])
                          for o in case["options"] if o["eligible"])
        alert_svc.create(db, audience_role="COORDINATOR", shipment=sh, order=order, kind="NO_FEASIBLE_OPTION",
                         severity="CRITICAL", title=f"NO FEASIBLE OPTION - ESCALATE: {sh.id}",
                         message=f"Every option violates a hard constraint. {lines}",
                         suggested_action="Escalate. Any approval now requires a reason and is logged as CONSTRAINT OVERRIDE.",
                         dedupe_key=f"{sh.id}|NO_FEASIBLE|sv{sh.state_version}|av{av}|cv{st.clock_version}", now=now)
    audit(db, user, "SCENARIOS_CREATED", "intervention", iv.id,
          after={"shipment_id": sh.id, "recommendation": rec["code"],
                 "stability": case["stability"]["label"] if case["stability"] else None})
    return iv


def scenarios_of(db: Session, iv: m.Intervention) -> list[m.InterventionScenario]:
    return (db.query(m.InterventionScenario).filter(m.InterventionScenario.intervention_id == iv.id)
            .order_by(m.InterventionScenario.id).all())


def latest_case(db: Session, shipment_id: str) -> Optional[m.Intervention]:
    return (db.query(m.Intervention).filter(m.Intervention.shipment_id == shipment_id)
            .order_by(m.Intervention.id.desc()).first())


def _stale_reason(db: Session, iv: m.Intervention, sh: m.Shipment) -> Optional[str]:
    st = sim_state(db)
    _, av = get_assumptions(db)
    if sh.state_version != iv.shipment_state_version:
        return "the shipment changed (new milestone, disruption or intervention)"
    if av != iv.assumptions_version:
        return "the assumptions were edited"
    if st.clock_version != iv.clock_version:
        return "the simulation clock advanced"
    return None


def approve(db: Session, iv: m.Intervention, scenario_id: int, override_reason: Optional[str], user: m.User) -> m.Intervention:
    from . import predictions as pred_svc
    if iv.status in ("APPLIED", "COMPLETED", "APPROVED"):
        if iv.selected_scenario_id == scenario_id:
            return iv                                       # idempotent
        raise HTTPException(409, "This case was already approved with a different option")
    if iv.status != "AWAITING_APPROVAL":
        raise HTTPException(409, f"This case is {iv.status}. Re-run the scenarios.")
    sh = db.get(m.Shipment, iv.shipment_id)
    stale = _stale_reason(db, iv, sh)
    if stale:
        iv.status = "SUPERSEDED"
        audit(db, user, "INTERVENTION_SUPERSEDED", "intervention", iv.id, after={"reason": stale})
        db.commit()
        raise HTTPException(409, f"Scenarios are out of date because {stale}. Re-run the scenarios before approving.")
    sc = db.get(m.InterventionScenario, scenario_id)
    if sc is None or sc.intervention_id != iv.id:
        raise HTTPException(404, "Scenario not found")
    if not sc.eligible:
        raise HTTPException(422, f"{sc.code} is not eligible: {sc.ineligible_reason}")
    rec = iv.recommendation_json
    is_override = (not sc.feasible) or sc.code != rec.get("option_code")
    reason = (override_reason or "").strip()
    if is_override and len(reason) < 5:
        raise HTTPException(422, "This option is not the recommended feasible option. An override reason is required.")

    st = sim_state(db)
    now = st.sim_now
    a, _ = get_assumptions(db)
    order = db.get(m.Order, sh.order_id)
    scs = {s.code: s for s in scenarios_of(db, iv)}
    cont = scs["CONTINUE"].metrics_json
    chosen = sc.metrics_json
    iv.status = "APPROVED"
    iv.selected_scenario_id = sc.id
    iv.decided_by, iv.decided_sim_at = user.id, now
    iv.is_override, iv.override_reason = is_override, reason or None
    # Panel A: model expectations at approval time, not realised savings
    iv.impact_json = {
        "option": sc.code,
        "modelled_late_hours_avoided": cont["exp_late_h"] - chosen["exp_late_h"],
        "modelled_cost_difference_rs": cont["total"] - chosen["total"],
        "incremental_freight_rs": chosen["freight"],
        "continue_total_rs": cont["total"], "chosen_total_rs": chosen["total"],
    }
    before = {"route_id": sh.route_id, "alt_route_id": sh.active_alternative_route_id,
              "disposition": sh.disposition, "state_version": sh.state_version}
    affected = [sh]
    if sc.code == "REROUTE":
        sh.active_alternative_route_id = sc.plan_json["alt_route_id"]
        add_event(db, sh.id, "REROUTED", now, f"Rerouted via {sc.plan_json['alt_route_name']} (approved by coordinator)",
                  state=sh.state, user=user, source="COORDINATOR")
        action_text = f"The shipment has been rerouted via {sc.plan_json['alt_route_name']}."
        customer_action = "Rerouting has been initiated to protect your delivery."
    elif sc.code == "SPLIT":
        affected = _apply_split(db, sh, order, sc.plan_json, now, a, user)
        action_text = sc.plan_json["summary"] + "."
        customer_action = "Your order is being sent as two deliveries; an urgent part has been prioritised."
    else:
        add_event(db, sh.id, "DECISION", now, "Coordinator decision: continue the current plan",
                  state=sh.state, user=user, source="COORDINATOR")
        action_text = "Decision: continue the current plan."
        customer_action = "Our logistics team has reviewed the shipment and it is continuing on the current plan."
    sh.state_version += 1
    iv.status = "APPLIED"
    db.flush()
    pred_svc.recompute(db, trigger="INTERVENTION_APPLIED", trigger_event_id=f"IV-{iv.id}",
                       trigger_label=f"intervention {iv.id} ({sc.code})", order_ids=[order.id], raise_alerts=False)
    leaves = [s for s in leaf_shipments(db, order.id)]
    preds = [p for p in (pred_svc.latest(db, s.id) for s in leaves) if p is not None]
    updated = max((p.p50_at for p in preds), default=None)
    if updated:
        order.revised_eta_communicated, order.revised_eta_communicated_at = updated, now
    alert_svc.create(db, audience_role="CUSTOMER", customer_id=order.customer_id, shipment=sh, order=order,
                     kind="ACTION_TAKEN", severity="INFO", title=f"Update on order {order.id}",
                     message=customer_action, suggested_action="No action is required from you.",
                     data={"promised_at": iso(order.promised_at), "updated_expected_delivery": iso(updated),
                           "action_taken": sc.code},
                     dedupe_key=f"{sh.id}|ACTION|IV{iv.id}|CUSTOMER", now=now)
    alert_svc.create(db, audience_role="COORDINATOR", shipment=sh, order=order, kind="ACTION_TAKEN", severity="INFO",
                     title=f"Intervention applied: {sc.code} on {sh.id}", message=action_text,
                     suggested_action="", data={"updated_expected_delivery": iso(updated), "action_taken": sc.code},
                     dedupe_key=f"{sh.id}|ACTION|IV{iv.id}|COORDINATOR", now=now)
    after = {"option": sc.code, "feasible": sc.feasible, "recommended": rec.get("option_code"),
             "shipments": [s.id for s in affected], "impact": iv.impact_json}
    audit(db, user, "INTERVENTION_APPROVED", "intervention", iv.id, before=before, after=after)
    if is_override:
        audit(db, user, "CONSTRAINT OVERRIDE", "intervention", iv.id,
              after={"option": sc.code, "reason": reason, "violations": [v["text"] for v in sc.violations_json],
                     "recommended": rec.get("option_code")})
    return iv


def _apply_split(db: Session, parent: m.Shipment, order: m.Order, plan: dict, now: datetime,
                 a: Assumptions, user: m.User) -> list[m.Shipment]:
    """Parent -> SPLIT_PARENT; two child lots under the same order, quantities summing exactly."""
    q_u = plan["urgent_qty_t"]
    q_r = parent.quantity_tonnes - q_u                     # exact complement
    start = {"URGENT": plus_hours(now, plan["lead_h"]),
             "REMAINDER": plus_hours(now, plan.get("remainder_lead_h", plan["lead_h"]))}
    busy = {s.driver_user_id for s in db.query(m.Shipment).filter(
        m.Shipment.disposition == "ACTIVE", m.Shipment.state != "DELIVERED", m.Shipment.is_historical.is_(False))}
    crew = [u for u in db.query(m.User).filter(
        m.User.role == "TRANSPORTER", m.User.transporter_id == parent.transporter_id,
        m.User.is_active.is_(True)).order_by(m.User.id) if u.id not in busy]
    # the reserved relief driver first; a spare driver (normally used for new orders) only if none is free
    relief = next((u for u in crew if u.username.startswith("relief_")), crew[0] if crew else None)
    children = []
    for lot, qty, driver, vehicle, alt in (
            ("URGENT", q_u, relief.id if relief else None, f"{parent.vehicle_label}-B (second vehicle)",
             plan.get("urgent_alt_route_id")),
            ("REMAINDER", q_r, parent.driver_user_id, parent.vehicle_label, parent.active_alternative_route_id)):
        ch = m.Shipment(
            id=f"{parent.id}-{lot[0]}", order_id=order.id, transporter_id=parent.transporter_id,
            driver_user_id=driver, vehicle_label=vehicle, route_id=parent.route_id,
            active_alternative_route_id=alt, parent_shipment_id=parent.id, lot_type=lot, quantity_tonnes=qty,
            planned_loading_at=start[lot], planned_arrival_at=parent.planned_arrival_at, state="PLANNED",
            state_entered_at=now, disposition="ACTIVE", state_version=1, last_progress_km=0.0)
        db.add(ch)
        children.append(ch)
    db.flush()
    # A late dispatch belonged to the original vehicle: it is now part of the remainder's planned start
    # (so it is not counted twice), and it stays linked to the remainder for delay attribution.
    remainder = children[1]
    for d in db.query(m.Disruption).filter(m.Disruption.kind == "DEPARTURE_OFFSET", m.Disruption.shipment_id == parent.id,
                                           m.Disruption.status == "ACTIVE"):
        d.shipment_id, d.status, d.ended_at = remainder.id, "ENDED", now
    parent.disposition = "SPLIT_PARENT"                    # terminal; not DELIVERED; excluded from delivery KPIs
    add_event(db, parent.id, "SPLIT", now, plan["summary"], state=parent.state, user=user, source="COORDINATOR")
    for ch in children:
        add_event(db, ch.id, "MILESTONE", now, f"{ch.lot_type} lot created by split of {parent.id}; "
                  f"loading starts after the second-vehicle lead time", state="PLANNED", user=user, source="COORDINATOR")
    return children


def reject(db: Session, iv: m.Intervention, reason: Optional[str], user: m.User) -> m.Intervention:
    if iv.status == "REJECTED":
        return iv                                           # idempotent
    if iv.status != "AWAITING_APPROVAL":
        raise HTTPException(409, f"This case is {iv.status} and cannot be rejected")
    iv.status = "REJECTED"
    iv.decided_by, iv.decided_sim_at = user.id, sim_state(db).sim_now
    iv.override_reason = (reason or "").strip() or None
    audit(db, user, "INTERVENTION_REJECTED", "intervention", iv.id, after={"reason": iv.override_reason})
    return iv


def supersede_open_cases(db: Session, why: str, user: Optional[m.User] = None) -> int:
    n = 0
    for iv in db.query(m.Intervention).filter(m.Intervention.status == "AWAITING_APPROVAL"):
        iv.status = "SUPERSEDED"
        audit(db, user, "INTERVENTION_SUPERSEDED", "intervention", iv.id, after={"reason": why})
        n += 1
    return n


def complete_if_arrived(db: Session, order_id: str) -> None:
    """APPLIED -> COMPLETED once every leaf lot of the order reached the customer gate."""
    leaves = leaf_shipments(db, order_id)
    if not leaves or any(s.arrived_at is None for s in leaves):
        return
    ids = [s.id for s in db.query(m.Shipment).filter(m.Shipment.order_id == order_id)]
    for iv in db.query(m.Intervention).filter(m.Intervention.shipment_id.in_(ids), m.Intervention.status == "APPLIED"):
        iv.status = "COMPLETED"
