"""Live operations: order creation, driver flow across roles, driver reports, activity feed, change-stamp,
simulation auto-run, history lists and the new dashboard KPIs. Everything goes through the real API/services."""
import json
import re

import pytest

from app import models as m
from app.simulator import runner
from tests.conftest import login, stage_g1

NEW_ORDER = {"route_id": "R2", "transporter_id": "TR-1", "product_code": "FILM-L30", "quantity_tonnes": 20}


def _create(client, co, **over):
    r = client.post("/api/orders", headers=co, json={**NEW_ORDER, **over})
    return r


def _feed(client, co, limit=100):
    return client.get(f"/api/activity?limit={limit}", headers=co).json()


# ---------- orders ----------
def test_create_order_assigns_a_free_driver_and_every_role_sees_it(client, auth):
    co = auth("coordinator")
    before = client.get("/api/sync/state", headers=co).json()["stamp"]
    r = _create(client, co)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["shipment_id"].startswith("SHP-") and o["driver_username"] == "driver15"
    assert o["vehicle_label"].startswith("MH20") and "Sai Krupa" in o["transporter_name"]
    assert client.get("/api/sync/state", headers=co).json()["stamp"] != before
    # driver sees it, ready for the first milestone
    mine = client.get("/api/transporter/me/shipments", headers=auth("driver15")).json()
    assert [x["id"] for x in mine] == [o["shipment_id"]] and mine[0]["next_state"] == "LOADING"
    # the right customer sees it, another does not
    seen = [x["id"] for x in client.get("/api/customer/me/orders", headers=auth("customer_b")).json()]
    assert o["order_id"] in seen
    assert o["order_id"] not in [x["id"] for x in client.get("/api/customer/me/orders", headers=auth("customer_a")).json()]
    # coordinator: a real prediction exists and the assignment is in the feed
    d = client.get(f"/api/shipments/{o['shipment_id']}", headers=co).json()
    assert d["prediction"] is not None and d["state"] == "PLANNED" and d["promised_at"] > d["planned_loading_at"]
    assert any(i["kind"] == "ASSIGNED" and o["shipment_id"] in i["title"] for i in _feed(client, co))
    assert "ORDER_CREATED" in [a["action"] for a in client.get("/api/audit-events", headers=co).json()]


def test_create_order_validation_and_driver_capacity(client, auth):
    co = auth("coordinator")
    assert _create(client, co, route_id="R1A").status_code == 422          # alternatives are not destinations
    assert _create(client, co, product_code="NOPE").status_code == 422
    assert _create(client, co, quantity_tonnes=0).status_code == 422
    assert _create(client, co, transporter_id="TR-9").status_code == 422
    assert _create(client, co).status_code == 201
    second = _create(client, co)                                           # TR-1 has one spare driver only
    assert second.status_code == 409 and "No free driver" in second.json()["detail"]
    assert _create(client, co, transporter_id="TR-2").status_code == 201   # another company still has one


def test_new_order_flows_through_driver_coordinator_and_customer(client, auth):
    co, cu = auth("coordinator"), auth("customer_b")
    o = _create(client, co).json()
    sid, dr = o["shipment_id"], auth("driver15")
    stamps = {client.get("/api/sync/state", headers=cu).json()["stamp"]}
    for to_state, customer_text, feed_text in (
            ("LOADING", "Loading started at Plant X", "Driver started loading"),
            ("AT_PLANT_GATE", "Loaded and waiting at the plant gate", "loaded and waiting at the plant gate"),
            ("IN_TRANSIT", "Left Plant X, on its way to you", "departed Plant X")):
        r = client.post(f"/api/transporter/shipments/{sid}/milestones", headers=dr, json={"to_state": to_state})
        assert r.status_code == 200 and r.json()["state"] == to_state
        assert client.get(f"/api/shipments/{sid}", headers=co).json()["state"] == to_state        # coordinator
        order = next(x for x in client.get("/api/customer/me/orders", headers=cu).json() if x["id"] == o["order_id"])
        assert customer_text in [e["text"] for e in order["shipments"][0]["timeline"]]            # customer, safe text
        assert any(feed_text in i["title"] for i in _feed(client, co))                            # activity feed
        stamps.add(client.get("/api/sync/state", headers=cu).json()["stamp"])
    assert len(stamps) == 4                      # the change-stamp moved at every step (so tabs refresh)
    d = client.get(f"/api/shipments/{sid}", headers=co).json()
    assert d["state"] == "IN_TRANSIT" and d["last_progress_km"] == 0 and d["last_telemetry_at"]
    assert any(v["shipment_id"] == sid for v in client.get("/api/control-tower/map-data", headers=co).json()["vehicles"])
    # the clock moves it and the simulated position shows up as an event
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 60})
    assert client.get(f"/api/shipments/{sid}", headers=co).json()["last_progress_km"] > 20
    assert any(i["kind"] == "POSITION" and sid in i["title"] for i in _feed(client, co))


# ---------- driver reports ----------
def test_driver_breakdown_report_becomes_a_real_disruption(client, auth):
    co, dr = auth("coordinator"), auth("driver14")
    before = client.get("/api/shipments/SHP-AMV-1116-05", headers=co).json()["prediction"]
    sh = client.get("/api/transporter/me/shipments", headers=dr).json()[0]
    assert sh["can_report"] is True and sh["active_report"] is None
    r = client.post("/api/transporter/shipments/SHP-AMV-1116-05/report", headers=dr,
                    json={"kind": "BREAKDOWN", "note": "Tyre blown, waiting for the service truck"})
    assert r.status_code == 200, r.text
    assert r.json()["shipment"]["active_report"] == "Breakdown reported" and r.json()["shipment"]["can_report"] is False
    after = client.get("/api/shipments/SHP-AMV-1116-05", headers=co).json()["prediction"]
    chips = {c["key"]: c["hours"] for c in after["reasons"]["chips"]}
    assert chips["repair_wait"] > 0.9 and after["p50_at"] > before["p50_at"]
    assert any(i["kind"] == "REPORT" and "Tyre blown" in i["detail"] for i in _feed(client, co))
    assert client.post("/api/transporter/shipments/SHP-AMV-1116-05/report", headers=dr, json={"kind": "BREAKDOWN"}).status_code == 409
    audit = client.get("/api/audit-events", headers=co).json()
    assert "DRIVER_REPORT" in [a["action"] for a in audit]


def test_driver_hazard_report_slows_the_road_and_stays_customer_safe(client, auth):
    co, dr = auth("coordinator"), auth("driver3")
    before = client.get("/api/shipments/SHP-AMV-1116-01", headers=co).json()["prediction"]
    r = client.post("/api/transporter/shipments/SHP-AMV-1116-01/report", headers=dr,
                    json={"kind": "ROAD_HAZARD", "note": "internal-note-xyz oil spill"})
    assert r.status_code == 200 and r.json()["shipment"]["active_report"] == "Road hazard reported"
    after = client.get("/api/shipments/SHP-AMV-1116-01", headers=co).json()["prediction"]
    assert after["p50_at"] > before["p50_at"] and {c["key"]: c["hours"] for c in after["reasons"]["chips"]}["slowdown"] > 0
    order = next(o for o in client.get("/api/customer/me/orders", headers=auth("customer_b")).json() if o["id"] == "ORD-AMV-1116-01")
    text = json.dumps(order)
    assert "internal-note-xyz" not in text and "oil spill" not in text and "Sai Krupa" not in text
    assert any("disruption was detected" in e["text"] for e in order["shipments"][0]["timeline"])


def test_report_rules(client, auth):
    dr1 = auth("driver1")                                                    # SHP-PTH-1116-01 is still LOADING
    assert client.post("/api/transporter/shipments/SHP-PTH-1116-01/report", headers=dr1, json={"kind": "BREAKDOWN"}).status_code == 409
    assert client.post("/api/transporter/shipments/SHP-AMV-1116-05/report", headers=dr1, json={"kind": "BREAKDOWN"}).status_code == 404
    assert client.post("/api/transporter/shipments/SHP-AMV-1116-05/report", headers=auth("driver14"), json={"kind": "FIRE"}).status_code == 422


# ---------- activity feed ----------
def test_activity_feed_is_built_from_real_records_without_duplicates(client, auth, db):
    co = auth("coordinator")
    stage_g1(client, auth)
    client.post("/api/shipments/SHP-PTH-1116-01/recalculate", headers=co)
    client.post("/api/shipments/SHP-PTH-1116-01/recalculate", headers=co)             # must not duplicate alerts or lines
    items = _feed(client, co, 200)
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    kinds = {i["kind"] for i in items}
    assert {"MILESTONE", "DISRUPTION", "RISK", "ALERT", "NOTIFICATION", "ASSIGNED"} <= kinds
    assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
    risk = next(i for i in items if i["kind"] == "RISK" and "SHP-PTH-1116-01" in i["title"])
    assert "from LOW to HIGH" in risk["title"] and risk["severity"] == "alert"
    # every id points at a real row
    tables = {"ev": m.ShipmentEvent, "al": m.Alert, "pr": m.Prediction, "au": m.AuditEvent}
    for i in items:
        prefix, n = i["id"].split(":")
        assert db.get(tables[prefix], int(n)) is not None
    flood = next(i for i in items if i["kind"] == "DISRUPTION")
    assert "Flooding" in flood["title"] and "SHP-PTH-1116-01" in flood["detail"]       # merged: one row for many shipments
    assert sum(1 for i in items if i["kind"] == "DISRUPTION") == 1


def test_activity_feed_limit_and_access(client, auth):
    assert len(_feed(client, auth("coordinator"), 5)) <= 5
    for who in ("customer_a", "driver1"):
        assert client.get("/api/activity", headers=login(client, who)).status_code == 403


# ---------- change stamp ----------
def test_sync_stamp_is_stable_until_something_changes(client, auth):
    co = auth("coordinator")
    a = client.get("/api/sync/state", headers=co).json()
    b = client.get("/api/sync/state", headers=co).json()
    assert a["stamp"] == b["stamp"] and re.fullmatch(r"[0-9a-f]{12}", a["stamp"])
    client.post("/api/transporter/shipments/SHP-PTH-1116-01/milestones", headers=auth("driver1"), json={"to_state": "AT_PLANT_GATE"})
    assert client.get("/api/sync/state", headers=co).json()["stamp"] != a["stamp"]
    # everybody gets the same stamp (customers and drivers poll it too) and it exposes no counts
    assert client.get("/api/sync/state", headers=auth("customer_a")).json()["stamp"] == \
        client.get("/api/sync/state", headers=co).json()["stamp"]


# ---------- simulation control and auto-run ----------
def test_simulation_control_and_runner_tick(client, auth, db):
    co = auth("coordinator")
    clock = client.get("/api/simulation/clock", headers=co).json()
    assert clock["paused"] is True                                           # paused by default
    assert runner.step_once() is False                                       # nothing moves while paused
    assert client.post("/api/simulation/clock/control", headers=co, json={"speed": 7}).status_code == 422
    r = client.post("/api/simulation/clock/control", headers=co, json={"paused": False, "speed": 5})
    assert r.status_code == 200 and r.json()["clock"]["paused"] is False and r.json()["clock"]["speed"] == 5
    assert runner.step_once() is True
    now = client.get("/api/simulation/clock", headers=co).json()
    assert now["sim_now"] > clock["sim_now"] and now["clock_version"] > clock["clock_version"]
    actions = [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    assert "SIMULATION_CONTROL" in actions and "CLOCK_ADVANCED" not in actions     # one row per Start, not per tick
    client.post("/api/simulation/clock/control", headers=co, json={"paused": True})
    assert runner.step_once() is False


def test_runner_pauses_itself_on_a_new_high_alert(client, auth, db, monkeypatch):
    co = auth("coordinator")
    client.post("/api/simulation/clock/control", headers=co, json={"paused": False, "speed": 5, "pause_on_alert": True})
    real = runner.clock.advance

    def raising_alert(session, minutes, user=None, record_audit=True):
        out = real(session, minutes, user, record_audit)
        session.add(m.Alert(audience_role="COORDINATOR", kind="TEST", severity="HIGH", title="t", message="m",
                            dedupe_key="auto-pause-test", created_sim_at=session.get(m.SimulationState, 1).sim_now))
        session.flush()
        return out
    monkeypatch.setattr(runner.clock, "advance", raising_alert)
    assert runner.step_once() is True
    assert client.get("/api/simulation/clock", headers=co).json()["paused"] is True
    assert "SIMULATION_AUTO_PAUSED" in [a["action"] for a in client.get("/api/audit-events", headers=co).json()]
    # with the option off, the clock keeps running
    client.post("/api/simulation/clock/control", headers=co, json={"paused": False, "pause_on_alert": False})
    monkeypatch.setattr(runner.clock, "advance", lambda s, mi, u=None, record_audit=True: (
        s.add(m.Alert(audience_role="COORDINATOR", kind="TEST", severity="HIGH", title="t2", message="m",
                      dedupe_key="auto-pause-test-2", created_sim_at=s.get(m.SimulationState, 1).sim_now)), real(s, mi, u, record_audit))[1])
    assert runner.step_once() is True
    assert client.get("/api/simulation/clock", headers=co).json()["paused"] is False
    client.post("/api/simulation/clock/control", headers=co, json={"paused": True, "pause_on_alert": True})


def test_position_events_are_throttled(client, auth, db):
    co = auth("coordinator")

    def count():
        db.expire_all()
        return db.query(m.ShipmentEvent).filter(m.ShipmentEvent.shipment_id == "SHP-AMV-1116-01",
                                                m.ShipmentEvent.type == "POSITION").count()
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 15})
    assert count() == 1
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 15})     # < 30 simulated minutes later
    assert count() == 1
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 30})
    assert count() == 2


# ---------- customer / driver extras ----------
def test_customer_delay_explanation_progress_and_history_are_safe(client, auth, db):
    co, cu = auth("coordinator"), auth("customer_a")
    stage_g1(client, auth)
    sh = next(s for s in client.get("/api/customer/me/shipments", headers=cu).json() if s["id"] == "SHP-PTH-1116-01")
    assert "road closure" in sh["delay_explanation"] and sh["progress_pct"] == 0
    assert sh["pod_status"] == "Not yet delivered" and isinstance(sh["timeline"], list)
    text = json.dumps(sh)
    for banned in ("Rs ", "penalt", "freight", "Sai Krupa", "stock-out", "P(late)"):
        assert banned not in sh["delay_explanation"] and banned not in text
    hist = client.get("/api/customer/me/history", headers=cu).json()
    assert len(hist) >= 10 and all(isinstance(h["on_time"], bool) for h in hist)
    mine = {o.id for o in db.query(m.Order).filter(m.Order.customer_id == "CUST-A")}
    assert {h["order_id"] for h in hist} <= mine                      # never another customer's deliveries
    other = client.get("/api/customer/me/history", headers=auth("customer_b")).json()
    assert not ({h["order_id"] for h in other} & {h["order_id"] for h in hist})
    client.post("/api/transporter/shipments/SHP-PTH-1116-01/milestones", headers=auth("driver1"), json={"to_state": "IN_TRANSIT"}) \
        if False else None


def test_driver_history_lists_only_own_runs(client, auth, db):
    hist = client.get("/api/transporter/me/history", headers=auth("driver1")).json()
    assert len(hist) >= 5
    me = db.query(m.User).filter(m.User.username == "driver1").one()
    owned = {s.id for s in db.query(m.Shipment).filter(m.Shipment.driver_user_id == me.id)}
    assert {h["shipment_id"] for h in hist} <= owned
    assert all(h["destination_name"] and isinstance(h["on_time"], bool) for h in hist)
    # a driver who is not assigned to history sees none of it
    assert not ({h["shipment_id"] for h in hist} & {h["shipment_id"] for h in client.get(
        "/api/transporter/me/history", headers=auth("driver2")).json()})


def test_driver_progress_and_milestone_chain(client, auth):
    dr = auth("driver1")
    s0 = client.get("/api/transporter/me/shipments", headers=dr).json()[0]
    assert s0["progress_pct"] == 0 and s0["customer_name"].startswith("Sharma") and s0["can_report"] is False
    for st in ("AT_PLANT_GATE", "IN_TRANSIT"):
        assert client.post("/api/transporter/shipments/SHP-PTH-1116-01/milestones", headers=dr, json={"to_state": st}).status_code == 200
    client.post("/api/simulation/clock/advance", headers=auth("coordinator"), json={"minutes": 120})
    s1 = client.get("/api/transporter/me/shipments", headers=dr).json()[0]
    assert s1["state"] == "IN_TRANSIT" and 5 <= s1["progress_pct"] <= 60 and s1["can_report"] is True


# ---------- dashboard KPIs ----------
def test_dashboard_kpis_come_from_records(client, auth, db):
    co = auth("coordinator")
    k0 = client.get("/api/analytics/overview", headers=co).json()
    stage_g1(client, auth)
    k1 = client.get("/api/analytics/overview", headers=co).json()
    assert k1["active_shipments"] == k1["buckets"]["active_total"] == k0["active_shipments"]
    assert 1 <= k1["active_orders"] <= k1["active_shipments"]
    assert k1["high_risk_shipments"] >= k0["high_risk_shipments"] + 2        # G1 and G2 after the flood
    assert k1["delayed_shipments"] > k0["delayed_shipments"]
    assert k1["avg_predicted_delay_hours"] > k0["avg_predicted_delay_hours"]
    live = db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False), m.Shipment.state.in_(
        ("PLANNED", "LOADING", "AT_PLANT_GATE", "IN_TRANSIT")), m.Shipment.disposition == "ACTIVE")
    assert k1["active_orders"] == len({s.order_id for s in live})


# ---------- caching (why changes "did not appear") ----------
def test_app_shell_is_never_cached_and_assets_are_immutable(client):
    from tests.conftest import ROOT_DIST
    if not (ROOT_DIST / "index.html").is_file():
        pytest.skip("frontend not built")
    shell = client.get("/")
    assert "no-cache" in shell.headers["cache-control"]
    asset = re.search(r'/assets/[^"]+\.js', shell.text).group(0)
    assert "immutable" in client.get(asset).headers["cache-control"]
    assert client.get("/health").json()["frontend_built_at"]
