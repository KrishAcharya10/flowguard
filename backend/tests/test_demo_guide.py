"""The demo guide's use cases set up exactly what their steps promise (through the real services)."""
import pytest

from tests.conftest import login, scenario


def _setup(client, code, mode="jump"):
    r = client.post(f"/api/demo/use-cases/{code}/setup", headers=login(client, "coordinator"), json={"mode": mode})
    assert r.status_code == 200, r.text
    return login(client, "coordinator"), r.json()


def _case(client, co, sid):
    r = client.post(f"/api/shipments/{sid}/scenarios", headers=co)
    assert r.status_code == 201
    return r.json()


def test_guide_lists_eight_use_cases_with_steps(client, auth):
    g = client.get("/api/demo/use-cases", headers=auth("coordinator")).json()
    assert g["demo_mode"] is True and len(g["use_cases"]) == 8
    covered = set()
    for uc in g["use_cases"]:
        assert uc["steps"] and uc["story"] and uc["takeaway"]
        covered |= set(uc["proves"])
    assert {"O1", "O2", "O3", "O4", "O5"} <= covered


def test_start_mode_resets_to_the_seed(client, auth):
    client.post("/api/simulations/disruptions", headers=auth("coordinator"), json={"preset": "FLOOD_R1"})
    co, out = _setup(client, "flood-reroute", "start")
    assert out["steps_done_automatically"] == 0
    assert client.get("/api/simulations/disruptions", headers=co).json()[0]["preset"] == "TELEMETRY_OUTAGE"
    assert client.get("/api/shipments/SHP-G1", headers=co).json()["state"] == "LOADING"


def test_jump_flood_reroute(client):
    co, out = _setup(client, "flood-reroute")
    assert out["steps_done_automatically"] == 2
    d = client.get("/api/shipments/SHP-G1", headers=co).json()
    assert d["state"] == "AT_PLANT_GATE" and d["prediction"]["risk_category"] == "HIGH"
    actions = [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    assert "MILESTONE_POSTED" in actions and "DISRUPTION_CREATED" in actions and "DEMO_SETUP" in actions
    case = _case(client, co, "SHP-G1")
    assert case["recommendation"]["code"] == "REROUTE" and case["stability"]["label"] == "STABLE"


def test_jump_late_not_costly(client):
    co, _ = _setup(client, "late-not-costly")
    assert _case(client, co, "SHP-G2")["recommendation"]["code"] == "NO_JUSTIFIED_INTERVENTION"


def test_jump_no_feasible(client):
    co, _ = _setup(client, "no-feasible")
    assert client.get("/api/assumptions", headers=co).json()["values"]["alpha"] == 0.01
    assert _case(client, co, "SHP-G1")["recommendation"]["code"] == "NO_FEASIBLE_OPTION"


def test_jump_split_recommends_split_and_remainder_keeps_the_late_truck_delay(client, db):
    from app import models as m
    co, _ = _setup(client, "split")
    case = _case(client, co, "SHP-1013")
    assert case["recommendation"]["code"] == "SPLIT" and case["stability"]["label"] == "STABLE"
    assert scenario(case, "REROUTE")["eligible"] is False
    sp = scenario(case, "SPLIT")
    assert sp["metrics"]["p_stockout"] <= 0.10 < scenario(case, "CONTINUE")["metrics"]["p_stockout"]
    lots = {l["lot_type"]: l for l in sp["metrics"]["lots"]}
    assert lots["REMAINDER"]["p50_at"] > lots["URGENT"]["p50_at"]        # remainder still waits for the late truck
    r = client.post(f"/api/interventions/{case['id']}/approve", headers=co, json={"selected_scenario_id": sp["id"]})
    assert r.status_code == 200 and r.json()["status"] == "APPLIED"
    db.expire_all()
    rem = db.get(m.Shipment, "SHP-1013-R")
    # the 4 h late dispatch moved into the remainder's plan (not counted twice) and stays linked to it
    p = client.get("/api/shipments/SHP-1013-R", headers=co).json()["prediction"]
    assert p["p50_at"] == lots["REMAINDER"]["p50_at"]
    late = db.query(m.Disruption).filter(m.Disruption.kind == "DEPARTURE_OFFSET").one()
    assert late.shipment_id == rem.id and late.status == "ENDED"
    urgent = db.get(m.Shipment, "SHP-1013-U")
    relief = db.get(m.User, urgent.driver_user_id)
    assert relief.username == "relief_tr1"
    assert [s["id"] for s in client.get("/api/transporter/me/shipments", headers=login(client, "relief_tr1")).json()] == ["SHP-1013-U"]


def test_jump_breakdown(client):
    co, _ = _setup(client, "breakdown")
    chips = {c["key"]: c["hours"] for c in client.get("/api/shipments/SHP-1014", headers=co).json()["prediction"]["reasons"]["chips"]}
    assert chips["repair_wait"] > 1.0 and chips["closure_wait"] == 0
    assert _case(client, co, "SHP-1014")["recommendation"]["code"] == "NO_JUSTIFIED_INTERVENTION"


def test_jump_lost_signal(client):
    co, _ = _setup(client, "lost-signal")
    v = next(v for v in client.get("/api/control-tower/map-data", headers=co).json()["vehicles"] if v["shipment_id"] == "SHP-1010")
    assert v["data_confidence"] == "STALE"
    assert any(a["kind"] == "STALE_HIGH_PRIORITY" for a in client.get("/api/alerts", headers=co).json())


def test_jump_day_unfolds_then_pod(client):
    co, _ = _setup(client, "day-unfolds")
    assert client.get("/api/shipments/SHP-1003", headers=co).json()["state"] == "ARRIVED_AT_CUSTOMER_GATE"
    r = client.post("/api/transporter/shipments/SHP-1003/pod", headers=login(client, "driver3"), json={"recipient_name": "Gate desk"})
    assert r.json()["state"] == "DELIVERED"
    orders = client.get("/api/customer/me/orders", headers=login(client, "customer_b")).json()
    assert next(o for o in orders if o["id"] == "ORD-1003")["status"] == "Delivered"


@pytest.mark.parametrize("who", ["customer_a", "driver1"])
def test_only_coordinators_can_use_the_guide(client, who):
    h = login(client, who)
    assert client.get("/api/demo/use-cases", headers=h).status_code == 403
    assert client.post("/api/demo/use-cases/split/setup", headers=h, json={"mode": "jump"}).status_code == 403


def test_unknown_use_case_is_404(client, auth):
    assert client.post("/api/demo/use-cases/nope/setup", headers=auth("coordinator"), json={"mode": "start"}).status_code == 404
