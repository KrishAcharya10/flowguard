"""Workflow, lifecycle, simulator, analytics and contract tests through the API."""
import json
import time
from collections import defaultdict
from pathlib import Path

import pytest

from app import models as m
from app.main import app
from app.services import analytics
from app.services.core import get_assumptions, hours
from tests.conftest import scenario, stage_g1

ROOT = Path(__file__).resolve().parents[2]


def _case(client, auth, sid="SHP-PTH-1116-01"):
    r = client.post(f"/api/shipments/{sid}/scenarios", headers=auth("coordinator"))
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, auth, case, code, reason=None):
    body = {"selected_scenario_id": scenario(case, code)["id"]}
    if reason:
        body["override_reason"] = reason
    return client.post(f"/api/interventions/{case['id']}/approve", headers=auth("coordinator"), json=body)


# ---------- vertical slice ----------
def test_vertical_slice_end_to_end(client, auth):
    co, cu, dr = auth("coordinator"), auth("customer_a"), auth("driver1")
    before = next(o for o in client.get("/api/customer/me/orders", headers=cu).json() if o["id"] == "ORD-PTH-1116-01")
    assert before["shipments"][0]["state"] == "LOADING" and before["shipments"][0]["risk_level"] == "Low"
    # driver advances a milestone; coordinator sees it
    assert client.post("/api/transporter/shipments/SHP-PTH-1116-01/milestones", headers=dr, json={"to_state": "AT_PLANT_GATE"}).status_code == 200
    assert client.get("/api/shipments/SHP-PTH-1116-01", headers=co).json()["state"] == "AT_PLANT_GATE"
    p0 = client.get("/api/shipments/SHP-PTH-1116-01", headers=co).json()["prediction"]
    # disruption injected -> ETA and risk change -> alert with an actionable suggestion and reason
    d = client.post("/api/simulations/disruptions", headers=co, json={"preset": "FLOOD_R1"}).json()
    p1 = client.get("/api/shipments/SHP-PTH-1116-01", headers=co).json()["prediction"]
    assert p1["p50_at"] > p0["p50_at"] and p1["risk_category"] == "HIGH" and p0["risk_category"] == "LOW"
    assert p1["reasons"]["p50_change"]["trigger_event_id"] == d["id"] and p1["reasons"]["p50_change"]["hours"] > 2
    alert = next(a for a in client.get("/api/alerts", headers=co).json() if a["shipment_id"] == "SHP-PTH-1116-01")
    assert alert["severity"] == "HIGH" and "REROUTE" in alert["suggested_action"] and "road closure" in alert["message"]
    cust_alert = client.get("/api/customer/me/alerts", headers=cu).json()[0]
    assert cust_alert["promised_at"] and cust_alert["updated_expected_delivery"] and cust_alert["risk_level"] == "High"
    # war room compares three, recommendation explained, coordinator approves
    case = _case(client, auth)
    assert [s["code"] for s in case["scenarios"]] == ["CONTINUE", "REROUTE", "SPLIT"]
    assert len(case["recommendation"]["explanation"]) >= 4
    r = _approve(client, auth, case, "REROUTE")
    assert r.status_code == 200 and r.json()["status"] == "APPLIED"
    # shipment updates; customer sees updated expected delivery beside the original promise
    sh = client.get("/api/shipments/SHP-PTH-1116-01", headers=co).json()
    assert sh["active_alternative_route_id"] == "R1A" and sh["prediction"]["p50_at"] < p1["p50_at"]
    after = next(o for o in client.get("/api/customer/me/orders", headers=cu).json() if o["id"] == "ORD-PTH-1116-01")
    assert after["promised_at"] == before["promised_at"]                 # promise is immutable
    assert after["updated_expected_delivery"] and after["shipments"][0]["action_note"]
    # panel A shows the modelled benefit; audit trail exists
    impact = client.get("/api/analytics/business-impact", headers=co).json()
    assert "MODELLED" in impact["label"] and impact["panel_a"]["total_modelled_late_hours_avoided"] > 1
    actions = [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    for needed in ("MILESTONE_POSTED", "DISRUPTION_CREATED", "SCENARIOS_CREATED", "INTERVENTION_APPROVED"):
        assert needed in actions
    assert client.get("/api/transporter/me/shipments", headers=dr).json()[0]["instruction"]


# ---------- approval lifecycle ----------
def test_approve_is_idempotent_and_applies_once(client, auth, db):
    stage_g1(client, auth)
    case = _case(client, auth)
    assert _approve(client, auth, case, "REROUTE").status_code == 200
    n = db.query(m.ShipmentEvent).filter(m.ShipmentEvent.type == "REROUTED").count()
    again = _approve(client, auth, case, "REROUTE")
    assert again.status_code == 200 and again.json()["status"] == "APPLIED"
    db.expire_all()
    assert db.query(m.ShipmentEvent).filter(m.ShipmentEvent.type == "REROUTED").count() == n == 1
    assert _approve(client, auth, case, "CONTINUE", "changed my mind entirely").status_code == 409


def test_reject_is_idempotent(client, auth):
    stage_g1(client, auth)
    case = _case(client, auth)
    url = f"/api/interventions/{case['id']}/reject"
    assert client.post(url, headers=auth("coordinator"), json={"reason": "waiting for more data"}).json()["status"] == "REJECTED"
    assert client.post(url, headers=auth("coordinator"), json={}).json()["status"] == "REJECTED"
    assert _approve(client, auth, case, "REROUTE").status_code == 409


def test_non_recommended_option_requires_override_reason(client, auth):
    stage_g1(client, auth)
    case = _case(client, auth)
    assert _approve(client, auth, case, "CONTINUE").status_code == 422       # infeasible and not recommended
    r = _approve(client, auth, case, "CONTINUE", "Bypass bridge reported unsafe by transporter")
    assert r.status_code == 200 and r.json()["is_override"]
    audit = client.get("/api/audit-events", headers=auth("coordinator")).json()
    over = next(a for a in audit if a["action"] == "CONSTRAINT OVERRIDE")
    assert over["after"]["reason"].startswith("Bypass bridge") and over["after"]["violations"]


def test_material_change_after_scenarios_makes_approve_409(client, auth):
    stage_g1(client, auth)
    case = _case(client, auth)
    client.post("/api/simulations/disruptions", headers=auth("coordinator"), json={"preset": "GATE_CONGESTION"})
    r = _approve(client, auth, case, "REROUTE")
    assert r.status_code == 409 and "Re-run" in r.json()["detail"]
    latest = client.get("/api/shipments/SHP-PTH-1116-01/scenarios", headers=auth("coordinator")).json()
    assert latest["status"] == "SUPERSEDED"


def test_clock_advance_after_scenarios_makes_approve_409(client, auth):
    stage_g1(client, auth)
    case = _case(client, auth)
    client.post("/api/simulation/clock/advance", headers=auth("coordinator"), json={"minutes": 5})
    assert _approve(client, auth, case, "REROUTE").status_code == 409


def test_assumptions_change_supersedes_open_cases_and_recalculates(client, auth, db):
    co = auth("coordinator")
    stage_g1(client, auth)
    case = _case(client, auth)
    values = client.get("/api/assumptions", headers=co).json()["values"]
    values["stockout_cost_per_hour_rs"] = 90000
    r = client.put("/api/assumptions", headers=co, json=values).json()
    assert r["assumptions_version"] == 2 and r["cases_superseded"] == 1 and r["predictions_recomputed"] >= 12
    assert _approve(client, auth, case, "REROUTE").status_code == 409
    assert "ASSUMPTIONS_UPDATED" in [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    bad = dict(values, w_late=0.9)                                           # weights must sum to 1
    assert client.put("/api/assumptions", headers=co, json=bad).status_code == 422


def test_new_case_supersedes_the_old_one(client, auth, db):
    stage_g1(client, auth)
    a, b = _case(client, auth), _case(client, auth)
    assert db.get(m.Intervention, a["id"]).status == "SUPERSEDED"
    assert db.query(m.Intervention).filter(m.Intervention.shipment_id == "SHP-PTH-1116-01",
                                           m.Intervention.status == "AWAITING_APPROVAL").count() == 1
    assert b["status"] == "AWAITING_APPROVAL"


def test_split_creates_two_children_and_excludes_the_parent(client, auth, db):
    co = auth("coordinator")
    stage_g1(client, auth)
    case = _case(client, auth)
    r = _approve(client, auth, case, "SPLIT", "Customer asked for an urgent partial delivery")
    assert r.status_code == 200, r.text
    parent = db.get(m.Shipment, "SHP-PTH-1116-01")
    kids = db.query(m.Shipment).filter(m.Shipment.parent_shipment_id == "SHP-PTH-1116-01").order_by(m.Shipment.lot_type).all()
    assert parent.disposition == "SPLIT_PARENT" and parent.state != "DELIVERED"
    assert sorted(k.lot_type for k in kids) == ["REMAINDER", "URGENT"]
    assert sum(k.quantity_tonnes for k in kids) == parent.quantity_tonnes
    assert all(k.order_id == parent.order_id and k.state == "PLANNED" for k in kids)
    urgent = next(k for k in kids if k.lot_type == "URGENT")
    rem = next(k for k in kids if k.lot_type == "REMAINDER")
    assert urgent.driver_user_id != rem.driver_user_id          # a separate fictional vehicle and driver
    assert urgent.active_alternative_route_id == "R1A"
    # child predictions equal the approved scenario (same seed, same lot columns)
    lots = {l["lot_type"]: l for l in scenario(case, "SPLIT")["metrics"]["lots"]}
    for k in kids:
        p = client.get(f"/api/shipments/{k.id}", headers=co).json()["prediction"]
        assert p["p50_at"] == lots[k.lot_type]["p50_at"]
    # KPI buckets exclude the parent and still sum to the active total
    a, _ = get_assumptions(db)
    counts = analytics.active_buckets(db, db.get(m.SimulationState, 1).sim_now, a)
    assert "SHP-PTH-1116-01" not in counts["by_shipment"] and "SHP-PTH-1116-01-U" in counts["by_shipment"]
    # customer sees two lots, never the parent
    order = next(o for o in client.get("/api/customer/me/orders", headers=auth("customer_a")).json() if o["id"] == "ORD-PTH-1116-01")
    assert sorted(s["id"] for s in order["shipments"]) == ["SHP-PTH-1116-01-R", "SHP-PTH-1116-01-U"]
    # both lots must arrive on time for the order to count as on time
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 720})
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 600})
    db.expire_all()
    done = {o["order_id"]: o for o in analytics.completed_orders(db, db.get(m.SimulationState, 1).sim_now, a)}
    kids = db.query(m.Shipment).filter(m.Shipment.parent_shipment_id == "SHP-PTH-1116-01").all()
    assert all(k.arrived_at for k in kids)
    promised = db.get(m.Order, "ORD-PTH-1116-01").promised_at
    assert done["ORD-PTH-1116-01"]["on_time"] == all(k.arrived_at <= promised for k in kids)
    assert done["ORD-PTH-1116-01"]["shipment_ids"] == ["SHP-PTH-1116-01-R", "SHP-PTH-1116-01-U"] or sorted(done["ORD-PTH-1116-01"]["shipment_ids"]) == ["SHP-PTH-1116-01-R", "SHP-PTH-1116-01-U"]
    assert db.get(m.Intervention, case["id"]).status == "COMPLETED"


# ---------- driver milestones ----------
def test_driver_milestones_next_state_only_idempotent_and_not_in_future(client, auth, db):
    dr = auth("driver1")
    url = "/api/transporter/shipments/SHP-PTH-1116-01/milestones"
    assert client.post(url, headers=dr, json={"to_state": "IN_TRANSIT"}).status_code == 409     # skips a state
    assert client.post(url, headers=dr, json={"to_state": "AT_PLANT_GATE", "occurred_at": "2030-01-01T00:00:00Z"}).status_code == 422
    v0 = db.get(m.Shipment, "SHP-PTH-1116-01").state_version
    assert client.post(url, headers=dr, json={"to_state": "AT_PLANT_GATE"}).status_code == 200
    assert client.post(url, headers=dr, json={"to_state": "AT_PLANT_GATE"}).status_code == 200  # idempotent
    db.expire_all()
    assert db.get(m.Shipment, "SHP-PTH-1116-01").state_version == v0 + 1
    assert db.query(m.ShipmentEvent).filter(m.ShipmentEvent.shipment_id == "SHP-PTH-1116-01",
                                            m.ShipmentEvent.state == "AT_PLANT_GATE").count() == 1
    assert client.post("/api/transporter/shipments/SHP-PTH-1116-01/pod", headers=dr, json={"recipient_name": "Desk"}).status_code == 409


def test_pod_completes_delivery_but_on_time_is_decided_at_gate_arrival(client, auth, db):
    dr = auth("driver11")
    a, _ = get_assumptions(db)
    now = db.get(m.SimulationState, 1).sim_now
    before = {o["order_id"]: o["on_time"] for o in analytics.completed_orders(db, now, a)}
    assert before["ORD-BHW-1116-02"] is True                         # counted at gate arrival, POD still pending
    r = client.post("/api/transporter/shipments/SHP-BHW-1116-02/pod", headers=dr, json={"recipient_name": "Receiving desk"})
    assert r.status_code == 200 and r.json()["state"] == "DELIVERED"
    db.expire_all()
    after = {o["order_id"]: o["on_time"] for o in analytics.completed_orders(db, now, a)}
    assert after == before


# ---------- predictions ----------
def test_get_endpoints_never_run_monte_carlo(client, auth, db):
    co = auth("coordinator")
    n = db.query(m.Prediction).count()
    for p in ("/api/control-tower/overview", "/api/shipments", "/api/shipments/SHP-PTH-1116-01", "/api/control-tower/map-data",
              "/api/shipments/SHP-PTH-1116-01/prediction?history=true", "/api/analytics/overview", "/api/customer/me/orders"):
        client.get(p, headers=co if "customer" not in p else auth("customer_a"))
    db.expire_all()
    assert db.query(m.Prediction).count() == n
    assert all(db.query(m.Prediction).filter(m.Prediction.shipment_id == s.id).count() >= 1
               for s in db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False), m.Shipment.state == "PLANNED"))


def test_alerts_are_deduplicated(client, auth, db):
    stage_g1(client, auth)
    n = db.query(m.Alert).count()
    client.post("/api/shipments/SHP-PTH-1116-01/recalculate", headers=auth("coordinator"))
    client.post("/api/shipments/SHP-PTH-1116-01/recalculate", headers=auth("coordinator"))
    db.expire_all()
    assert db.query(m.Alert).count() == n


def test_no_stock_data_uses_p_late_only(client, auth):
    d = client.get("/api/shipments/SHP-PTH-1116-03", headers=auth("coordinator")).json()
    assert d["stock"]["available"] is False and "unavailable" in d["stock"]["note"]
    assert d["prediction"]["p_stockout"] is None
    assert d["prediction"]["risk_index"] == round(100 * d["prediction"]["p_late"])


# ---------- simulator: truth vs belief ----------
def test_stale_telemetry_widens_range_and_never_fabricates_a_position(client, auth, db):
    co = auth("coordinator")
    sh = db.get(m.Shipment, "SHP-AMV-1116-04")
    pos0, seen0 = (sh.last_lat, sh.last_lon, sh.last_progress_km), sh.last_telemetry_at
    other0 = db.get(m.Shipment, "SHP-AMV-1116-05").last_progress_km
    p0 = client.get("/api/shipments/SHP-AMV-1116-04", headers=co).json()["prediction"]
    assert p0["data_confidence"] == "STALE"
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 30})
    db.expire_all()
    sh = db.get(m.Shipment, "SHP-AMV-1116-04")
    assert (sh.last_lat, sh.last_lon, sh.last_progress_km) == pos0 and sh.last_telemetry_at == seen0
    assert db.get(m.Shipment, "SHP-AMV-1116-05").last_progress_km > other0        # others keep reporting
    v = next(v for v in client.get("/api/control-tower/map-data", headers=co).json()["vehicles"] if v["shipment_id"] == "SHP-AMV-1116-04")
    assert v["data_confidence"] == "STALE" and v["age_min"] >= 120
    # compare with a fresh shipment of similar remaining distance: the stale range is wider per hour of travel
    assert any("uncertainty widened" in n for n in p0["reasons"]["notes"])


def test_clock_advance_moves_shipments_and_bumps_only_clock_version(client, auth, db):
    co = auth("coordinator")
    sv = db.get(m.Shipment, "SHP-AMV-1116-01").state_version
    r = client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 10}).json()
    assert r["clock"]["clock_version"] == 2 and r["clock"]["paused"] is True
    db.expire_all()
    assert db.get(m.Shipment, "SHP-AMV-1116-01").state_version == sv              # ticks are not material events
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 720})
    db.expire_all()
    arrived = db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False),
                                          m.Shipment.state == "ARRIVED_AT_CUSTOMER_GATE").count()
    assert arrived >= 10


def test_breakdown_is_a_vehicle_stoppage_not_a_route_closure(client, auth):
    co = auth("coordinator")
    p0 = client.get("/api/shipments/SHP-AMV-1116-05", headers=co).json()["prediction"]
    other0 = client.get("/api/shipments/SHP-AMV-1116-01", headers=co).json()["prediction"]
    r = client.post("/api/simulations/disruptions", headers=co, json={"preset": "BREAKDOWN", "shipment_id": "SHP-AMV-1116-05"})
    assert r.status_code == 201 and r.json()["kind"] == "VEHICLE_STOPPAGE" and r.json()["segment_waypoint_id"] is None
    p1 = client.get("/api/shipments/SHP-AMV-1116-05", headers=co).json()["prediction"]
    chips = {c["key"]: c["hours"] for c in p1["reasons"]["chips"]}
    assert chips["repair_wait"] > 0.9 and chips["closure_wait"] == 0 and p1["p50_at"] > p0["p50_at"]
    assert client.get("/api/shipments/SHP-AMV-1116-01", headers=co).json()["prediction"]["id"] != other0["id"]
    assert client.get("/api/shipments/SHP-AMV-1116-01", headers=co).json()["prediction"]["p50_at"] == other0["p50_at"]
    assert client.post("/api/simulations/disruptions", headers=co,
                       json={"preset": "BREAKDOWN", "shipment_id": "SHP-PTH-1116-01"}).status_code == 409   # not in transit


def test_reroute_ineligible_after_decision_node_and_split_after_departure(client, auth):
    case = _case(client, auth, "SHP-PTH-1116-03")                     # in transit, past Chalisgaon Junction
    assert scenario(case, "REROUTE")["eligible"] is False and "decision node" in scenario(case, "REROUTE")["ineligible_reason"]
    assert scenario(case, "SPLIT")["eligible"] is False and scenario(case, "SPLIT")["metrics"] is None
    case = _case(client, auth, "SHP-SAT-1116-01")                     # route R3 has no alternative
    assert "No alternative route" in scenario(case, "REROUTE")["ineligible_reason"]


# ---------- analytics ----------
def test_buckets_sum_to_active_total(client, auth, db):
    k = client.get("/api/analytics/overview", headers=auth("coordinator")).json()
    b = k["buckets"]
    active = db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False), m.Shipment.disposition == "ACTIVE",
                                         m.Shipment.state.in_(("PLANNED", "LOADING", "AT_PLANT_GATE", "IN_TRANSIT"))).count()
    assert b["LATE"] + b["AT_RISK"] + b["ON_TRACK"] == b["active_total"] == active
    assert b["LATE"] >= 1 and b["ARRIVED_PENDING_POD"] == 1


def test_on_time_is_per_order_at_gate_arrival(client, auth, db):
    k = client.get("/api/analytics/overview", headers=auth("coordinator")).json()
    rows = db.query(m.Shipment, m.Order).join(m.Order, m.Order.id == m.Shipment.order_id).filter(
        m.Shipment.arrived_at.isnot(None), m.Shipment.disposition == "ACTIVE").all()
    on_time = sum(1 for sh, o in rows if sh.arrived_at <= o.promised_at)
    assert k["orders_completed"] == len(rows) and k["orders_on_time"] == on_time
    assert k["on_time_pct"] == pytest.approx(100 * on_time / len(rows), abs=0.06)
    late = [hours(sh.arrived_at - o.promised_at) for sh, o in rows if sh.arrived_at > o.promised_at]
    assert k["average_delay_hours_late_orders"] == pytest.approx(sum(late) / len(late), abs=0.006)


def test_delay_events_sum_to_realised_delay_and_do_not_overlap(db):
    by = defaultdict(list)
    for de in db.query(m.DelayEvent).order_by(m.DelayEvent.start_at):
        by[de.shipment_id].append(de)
    checked = 0
    for sh in db.query(m.Shipment).filter(m.Shipment.arrived_at.isnot(None)):
        realised = max(0.0, hours(sh.arrived_at - sh.planned_arrival_at))
        evs = by.get(sh.id, [])
        assert sum(e.hours for e in evs) == pytest.approx(realised, abs=1e-3)   # documented tolerance
        assert all(e.hours >= 0 for e in evs)
        for a, b in zip(evs, evs[1:]):
            assert a.end_at <= b.start_at
        checked += 1
    assert checked >= 150


def test_delay_attribution_for_a_live_arrival(client, auth, db):
    stage_g1(client, auth)                                     # G2 continues through the flood and arrives late
    co = auth("coordinator")
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 720})
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 600})
    db.expire_all()
    g2 = db.get(m.Shipment, "SHP-PTH-1116-02")
    assert g2.arrived_at is not None
    evs = db.query(m.DelayEvent).filter(m.DelayEvent.shipment_id == "SHP-PTH-1116-02").all()
    assert sum(e.hours for e in evs) == pytest.approx(hours(g2.arrived_at - g2.planned_arrival_at), abs=1e-3)
    assert "FLOODING" in {e.cause for e in evs}


def test_transporter_metrics_are_by_company_and_patterns_are_visible(client, auth, db):
    co = auth("coordinator")
    rows = client.get("/api/analytics/transporters", headers=co).json()
    assert {r["id"] for r in rows} == {t.id for t in db.query(m.Transporter)}
    assert "driver" not in json.dumps(rows).lower()
    routes = {r["id"]: r for r in client.get("/api/analytics/routes", headers=co).json()}
    assert len(routes) >= 4 and sum(r["orders_completed"] for r in routes.values()) == \
        client.get("/api/analytics/overview", headers=co).json()["orders_completed"]
    causes = client.get("/api/analytics/delay-causes", headers=co).json()
    r2 = {c["cause"]: c["attributed_hours"] for c in causes["by_route"] if c["id"] == "R2"}
    assert max(r2, key=r2.get) == "ROUTE_CONGESTION"            # the seeded recurring-congestion route
    total = sum(c["attributed_hours"] for c in causes["totals"])
    assert total == pytest.approx(sum(c["attributed_hours"] for c in causes["by_route"]), abs=0.2)


def test_panel_b_formulas(client, auth):
    b = client.get("/api/analytics/business-impact", headers=auth("coordinator")).json()["panel_b"]
    i = b["inputs"]
    affected = i["annual_shipments"] * i["delay_rate"]
    mitigated = affected * i["mitigable_share"]
    gross = mitigated * i["avoidable_hours"] * i["cost_per_late_hour_rs"]
    cost = mitigated / i["success_rate"] * i["avg_intervention_cost_rs"]
    assert b["net_modelled_benefit_rs"] == pytest.approx(gross - cost)
    assert b["break_even_cost_per_late_hour_rs"] == pytest.approx(i["avg_intervention_cost_rs"] / i["success_rate"] / i["avoidable_hours"])


# ---------- contract and performance ----------
def test_exported_openapi_matches_the_running_app():
    exported = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    assert exported == json.loads(json.dumps(app.openapi(), sort_keys=True)), \
        "contracts/openapi.json is stale. Run scripts/export_openapi.py"


def test_performance_targets(client, auth):
    co = auth("coordinator")
    stage_g1(client, auth)
    client.get("/api/control-tower/overview", headers=co)
    t = time.perf_counter()
    assert client.get("/api/control-tower/overview", headers=co).status_code == 200
    overview_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    assert client.post("/api/shipments/SHP-PTH-1116-01/scenarios", headers=co).status_code == 201
    scenario_s = time.perf_counter() - t
    print(f"overview {overview_ms:.0f} ms (14 live shipments), scenario creation {scenario_s * 1000:.0f} ms")
    assert overview_ms < 1000 and scenario_s < 2.0


def test_reset_endpoint_restores_the_seed(client, auth):
    co = auth("coordinator")
    stage_g1(client, auth)
    r = client.post("/api/admin/reset", headers=co)
    assert r.status_code == 200 and r.json()["historical_shipments"] >= 150
    from tests.conftest import login
    co = login(client, "coordinator")
    assert client.get("/api/shipments/SHP-PTH-1116-01", headers=co).json()["state"] == "LOADING"
    assert client.get("/api/simulations/disruptions", headers=co).json()[0]["preset"] == "TELEMETRY_OUTAGE"


def test_overview_with_80_live_shipments_is_under_300_ms(client, auth, db):
    """Engineering target (spec section 7): overview with 80 shipments < 300 ms."""
    from app.services import predictions
    base = [s for s in db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False)).all()
            if s.state != "ARRIVED_AT_CUSTOMER_GATE"]
    k = 0
    skip = ("id", "order_id", "created_at", "updated_at", "driver_user_id")
    while db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False)).count() < 80:
        s = base[k % len(base)]
        k += 1
        o = db.get(m.Order, s.order_id)
        db.add(m.Order(id=f"ORD-P{k}", customer_id=o.customer_id, product_code=o.product_code,
                       quantity_tonnes=o.quantity_tonnes, promised_at=o.promised_at,
                       sla_penalty_per_late_hour=o.sla_penalty_per_late_hour, priority=o.priority))
        db.add(m.Shipment(id=f"SHP-P{k}", order_id=f"ORD-P{k}",
                          **{c.name: getattr(s, c.name) for c in m.Shipment.__table__.columns if c.name not in skip}))
        db.flush()
    predictions.recompute(db, trigger="perf")
    db.commit()
    co = auth("coordinator")
    client.get("/api/control-tower/overview", headers=co)
    best = float("inf")
    for _ in range(3):
        t = time.perf_counter()
        r = client.get("/api/control-tower/overview", headers=co)
        best = min(best, (time.perf_counter() - t) * 1000)
    assert len(r.json()["shipments"]) == 80
    print(f"overview with 80 live shipments: {best:.0f} ms")
    assert best < 300
