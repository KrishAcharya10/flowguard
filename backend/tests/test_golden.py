"""Golden scenarios G1-G3 through the REAL stack (seed -> API -> engine).
Target ranges are copied from docs/GOLDEN_SCENARIO.md and must never be edited to pass."""
from datetime import datetime

from tests.conftest import scenario, stage_g1


def _h(a, b):
    f = lambda x: datetime.fromisoformat(x.replace("Z", ""))  # noqa: E731
    return (f(a) - f(b)).total_seconds() / 3600


def test_g1_before_injection_is_low(client, auth):
    co = auth("coordinator")
    d = client.get("/api/shipments/SHP-G1", headers=co).json()
    assert d["state"] == "LOADING"                              # seeded LOADING
    p = d["prediction"]
    assert p["p_late"] <= 0.15 and p["p_stockout"] <= 0.05 and p["risk_category"] == "LOW"
    client.post("/api/transporter/shipments/SHP-G1/milestones", headers=auth("driver1"), json={"to_state": "AT_PLANT_GATE"})
    p = client.get("/api/shipments/SHP-G1", headers=co).json()["prediction"]
    assert p["p_late"] <= 0.15 and p["p_stockout"] <= 0.05 and p["risk_category"] == "LOW"
    # stock relation: S about 1-2 h after D, u <= 1 h, S - u >= D
    stock = client.get("/api/shipments/SHP-G1", headers=co).json()["stock"]
    s_minus_d = _h(stock["depletion_at"], d["promised_at"])
    assert 1.0 <= s_minus_d <= 2.0 and stock["unloading_hours"] <= 1.0 and s_minus_d - stock["unloading_hours"] >= 0


def test_g1_flooding_recommends_reroute_and_is_stable(client, auth):
    co = auth("coordinator")
    stage_g1(client, auth)
    d = client.get("/api/shipments/SHP-G1", headers=co).json()
    p = d["prediction"]
    assert p["risk_category"] == "HIGH" and p["p_late"] >= 0.70 and p["p_stockout"] >= 0.30
    assert 2.0 <= _h(p["p50_at"], d["promised_at"]) <= 4.0

    r = client.post("/api/shipments/SHP-G1/scenarios", headers=co)
    assert r.status_code == 201
    case = r.json()
    cont, rer, split = (scenario(case, c) for c in ("CONTINUE", "REROUTE", "SPLIT"))
    assert cont["metrics"]["p_late"] >= 0.70 and cont["metrics"]["p_stockout"] >= 0.30
    assert rer["eligible"] and split["eligible"]                # both eligible at injection
    assert rer["metrics"]["p_late"] <= 0.30
    assert 0.02 <= rer["metrics"]["p_stockout"] <= 0.08
    assert rer["metrics"]["freight"] > 0
    assert rer["metrics"]["total"] <= 0.6 * cont["metrics"]["total"]
    assert split["metrics"]["freight"] > rer["metrics"]["freight"]
    assert case["recommendation"]["code"] == "REROUTE" and rer["feasible"]
    assert case["stability"]["label"] == "STABLE" and case["stability"]["holds"] == 16
    # the stored prediction and the Continue scenario come from the same engine and seed
    assert abs(cont["metrics"]["p_late"] - p["p_late"]) < 1e-9
    assert abs(cont["metrics"]["p_stockout"] - p["p_stockout"]) < 1e-9


def test_g2_same_flood_high_stock_means_no_justified_intervention(client, auth):
    co = auth("coordinator")
    stage_g1(client, auth)
    case = client.post("/api/shipments/SHP-G2/scenarios", headers=co).json()
    cont = scenario(case, "CONTINUE")
    assert cont["metrics"]["p_late"] >= 0.50 and cont["metrics"]["p_stockout"] <= 0.05 and cont["feasible"]
    rec = case["recommendation"]
    assert rec["code"] == "NO_JUSTIFIED_INTERVENTION" and rec["option_code"] == "CONTINUE"
    others = [s["metrics"]["total"] for s in case["scenarios"] if s["code"] != "CONTINUE" and s["feasible"]]
    assert all(cont["metrics"]["total"] - t <= rec["threshold"] for t in others)
    assert any("Late is not the same as costly" in line for line in rec["explanation"])
    print("G2 stability (recorded, not asserted):", case["stability"]["label"], case["stability"]["holds"])


def test_g3_no_feasible_option_escalates_to_all_coordinators(client, auth):
    co = auth("coordinator")
    stage_g1(client, auth)
    base = client.post("/api/shipments/SHP-G1/scenarios", headers=co).json()
    split_freight = scenario(base, "SPLIT")["metrics"]["freight"]
    values = client.get("/api/assumptions", headers=co).json()["values"]
    values.update(alpha=0.01, max_incremental_freight_rs=20000)
    assert values["max_incremental_freight_rs"] < split_freight
    assert client.put("/api/assumptions", headers=co, json=values).status_code == 200

    case = client.post("/api/shipments/SHP-G1/scenarios", headers=co).json()
    names = {s["code"]: {v["constraint"] for v in s["violations"]} for s in case["scenarios"]}
    assert "MAX_P_STOCKOUT" in names["CONTINUE"] and "MAX_P_STOCKOUT" in names["REROUTE"]
    assert "MAX_FREIGHT" in names["SPLIT"]
    rec = case["recommendation"]
    assert rec["code"] == "NO_FEASIBLE_OPTION" and rec["option_code"] is None
    assert "ESCALATE" in rec["banner"] and rec["least_violating_code"] is not None
    assert not any(s["feasible"] for s in case["scenarios"])
    for who in ("coordinator", "coordinator2"):                 # no fourth role: every coordinator sees it
        alerts = client.get("/api/alerts", headers=auth(who)).json()
        assert any(a["severity"] == "CRITICAL" and a["kind"] == "NO_FEASIBLE_OPTION" for a in alerts)
    # an override needs a reason and is logged as CONSTRAINT OVERRIDE
    rid = scenario(case, "REROUTE")["id"]
    assert client.post(f"/api/interventions/{case['id']}/approve", headers=co,
                       json={"selected_scenario_id": rid}).status_code == 422
    r = client.post(f"/api/interventions/{case['id']}/approve", headers=co,
                    json={"selected_scenario_id": rid, "override_reason": "Customer line would stop; duty manager agreed"})
    assert r.status_code == 200 and r.json()["is_override"] is True
    actions = [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    assert "CONSTRAINT OVERRIDE" in actions
