"""Role x endpoint x ownership matrix (one parameterised test), 404 for other
users' resources, and customer key-absence on every customer endpoint."""
import json

import pytest

from app.main import app
from tests.conftest import scenario, stage_g1

C, U, T = "COORDINATOR", "CUSTOMER", "TRANSPORTER"
LOGIN = {C: "coordinator", U: "customer_a", T: "driver1"}
ASSUMP = None   # filled lazily with the current assumptions for the PUT body

# (method, path template, concrete path, allowed roles or "PUBLIC", json body)
MATRIX = [
    ("GET", "/health", "/health", "PUBLIC", None),
    ("POST", "/api/auth/login", "/api/auth/login", "PUBLIC", {"username": "nobody", "password": "x"}),
    ("GET", "/api/auth/me", "/api/auth/me", (C, U, T), None),
    ("GET", "/api/simulation/clock", "/api/simulation/clock", (C, U, T), None),
    ("GET", "/api/customer/me/orders", "/api/customer/me/orders", (U,), None),
    ("GET", "/api/customer/me/shipments", "/api/customer/me/shipments", (U,), None),
    ("GET", "/api/customer/me/shipments/{shipment_id}", "/api/customer/me/shipments/SHP-PTH-1116-01", (U,), None),
    ("GET", "/api/customer/me/alerts", "/api/customer/me/alerts", (U,), None),
    ("POST", "/api/customer/me/alerts/{alert_id}/acknowledge", "/api/customer/me/alerts/999999/acknowledge", (U,), None),
    ("GET", "/api/transporter/me/shipments", "/api/transporter/me/shipments", (T,), None),
    ("POST", "/api/transporter/shipments/{shipment_id}/milestones", "/api/transporter/shipments/SHP-PTH-1116-01/milestones", (T,), {"to_state": "AT_PLANT_GATE"}),
    ("POST", "/api/transporter/shipments/{shipment_id}/pod", "/api/transporter/shipments/SHP-PTH-1116-01/pod", (T,), {"recipient_name": "Gate desk"}),
    ("GET", "/api/control-tower/overview", "/api/control-tower/overview", (C,), None),
    ("GET", "/api/control-tower/map-data", "/api/control-tower/map-data", (C,), None),
    ("GET", "/api/orders/{order_id}", "/api/orders/ORD-PTH-1116-01", (C,), None),
    ("GET", "/api/shipments", "/api/shipments", (C,), None),
    ("GET", "/api/shipments/{shipment_id}", "/api/shipments/SHP-PTH-1116-01", (C,), None),
    ("GET", "/api/shipments/{shipment_id}/events", "/api/shipments/SHP-PTH-1116-01/events", (C,), None),
    ("GET", "/api/shipments/{shipment_id}/prediction", "/api/shipments/SHP-PTH-1116-01/prediction", (C,), None),
    ("POST", "/api/shipments/{shipment_id}/recalculate", "/api/shipments/SHP-PTH-1116-01/recalculate", (C,), None),
    ("POST", "/api/simulation/clock/advance", "/api/simulation/clock/advance", (C,), {"minutes": 5}),
    ("GET", "/api/simulations/disruptions", "/api/simulations/disruptions", (C,), None),
    ("POST", "/api/simulations/disruptions", "/api/simulations/disruptions", (C,), {"preset": "GATE_CONGESTION"}),
    ("POST", "/api/simulations/disruptions/{disruption_id}/end", "/api/simulations/disruptions/DSR-NONE/end", (C,), None),
    ("POST", "/api/shipments/{shipment_id}/scenarios", "/api/shipments/SHP-PTH-1116-01/scenarios", (C,), None),
    ("GET", "/api/shipments/{shipment_id}/scenarios", "/api/shipments/SHP-PTH-1116-01/scenarios", (C,), None),
    ("GET", "/api/interventions", "/api/interventions", (C,), None),
    ("POST", "/api/interventions/{intervention_id}/approve", "/api/interventions/999999/approve", (C,), {"selected_scenario_id": 1}),
    ("POST", "/api/interventions/{intervention_id}/reject", "/api/interventions/999999/reject", (C,), {}),
    ("GET", "/api/alerts", "/api/alerts", (C,), None),
    ("POST", "/api/alerts/{alert_id}/acknowledge", "/api/alerts/999999/acknowledge", (C,), None),
    ("GET", "/api/audit-events", "/api/audit-events", (C,), None),
    ("GET", "/api/analytics/overview", "/api/analytics/overview", (C,), None),
    ("GET", "/api/analytics/delay-causes", "/api/analytics/delay-causes", (C,), None),
    ("GET", "/api/analytics/routes", "/api/analytics/routes", (C,), None),
    ("GET", "/api/analytics/transporters", "/api/analytics/transporters", (C,), None),
    ("GET", "/api/analytics/business-impact", "/api/analytics/business-impact", (C,), None),
    ("GET", "/api/assumptions", "/api/assumptions", (C,), None),
    ("PUT", "/api/assumptions", "/api/assumptions", (C,), "ASSUMPTIONS"),
    ("GET", "/api/reference-data", "/api/reference-data", (C,), None),
    ("GET", "/api/demo/use-cases", "/api/demo/use-cases", (C,), None),
    ("POST", "/api/demo/use-cases/{code}/setup", "/api/demo/use-cases/dashboard-privacy/setup", (C,), {"mode": "start"}),
    ("POST", "/api/orders", "/api/orders", (C,), {"route_id": "R2", "transporter_id": "TR-1", "product_code": "FILM-L30", "quantity_tonnes": 20}),
    ("GET", "/api/activity", "/api/activity", (C,), None),
    ("GET", "/api/sync/state", "/api/sync/state", (C, U, T), None),
    ("POST", "/api/simulation/clock/control", "/api/simulation/clock/control", (C,), {"speed": 5}),
    ("GET", "/api/customer/me/history", "/api/customer/me/history", (U,), None),
    ("GET", "/api/transporter/me/history", "/api/transporter/me/history", (T,), None),
    ("POST", "/api/transporter/shipments/{shipment_id}/report", "/api/transporter/shipments/SHP-PTH-1116-01/report", (T,), {"kind": "BREAKDOWN"}),
    ("GET", "/api/gate/overview", "/api/gate/overview", (C,), None),
    ("GET", "/api/gate/summary", "/api/gate/summary", (C,), None),
    ("GET", "/api/gate/bookings", "/api/gate/bookings", (C,), None),
    ("POST", "/api/gate/bookings", "/api/gate/bookings", (C,), {"shipment_id": "SHP-AMV-1116-02", "slot_id": 1}),
    ("POST", "/api/gate/bookings/{booking_id}/reschedule", "/api/gate/bookings/999999/reschedule", (C,), {"slot_id": 1}),
    ("POST", "/api/gate/bookings/{booking_id}/cancel", "/api/gate/bookings/999999/cancel", (C,), {}),
    ("POST", "/api/gate/bookings/{booking_id}/complete", "/api/gate/bookings/999999/complete", (C,), None),
    ("PUT", "/api/gate/slots/{slot_id}", "/api/gate/slots/1", (C,), {"capacity": 3}),
    ("GET", "/api/transporter/me/gate", "/api/transporter/me/gate", (T,), None),
    ("POST", "/api/transporter/gate/bookings/{booking_id}/check-in", "/api/transporter/gate/bookings/999999/check-in", (T,), None),
    ("GET", "/api/documents/overview", "/api/documents/overview", (C,), None),
    ("GET", "/api/orders/{order_id}/documents", "/api/orders/ORD-PTH-1116-01/documents", (C,), None),
    ("POST", "/api/orders/{order_id}/invoice", "/api/orders/ORD-PTH-1116-01/invoice?filename=a.pdf", (C,), None),
    ("POST", "/api/documents/{document_id}/verify", "/api/documents/999999/verify", (C,), None),
    ("GET", "/api/documents/{document_id}/download", "/api/documents/999999/download", (C, U, T), None),
    ("POST", "/api/transporter/shipments/{shipment_id}/pod-document", "/api/transporter/shipments/SHP-PTH-1116-01/pod-document?filename=a.png&recipient_name=Bob", (T,), None),
    ("POST", "/api/shipments/{shipment_id}/pod-document", "/api/shipments/SHP-PTH-1116-01/pod-document?filename=a.png&recipient_name=Bob", (C,), None),
    ("POST", "/api/shipments/{shipment_id}/complete-delivery", "/api/shipments/SHP-PTH-1116-01/complete-delivery", (C,), {"recipient_name": "Bob"}),
    ("GET", "/api/customer/me/documents", "/api/customer/me/documents", (U,), None),
    ("POST", "/api/customer/me/chat", "/api/customer/me/chat", (U,), {"message": "hi"}),
    ("POST", "/api/admin/reset", "/api/admin/reset", (C,), None),
]


def test_matrix_covers_every_route_in_the_app():
    listed = {(m_, tpl) for m_, tpl, *_ in MATRIX}
    actual = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            actual.add((method.upper(), path))
    assert actual == listed, f"unlisted: {actual - listed}; stale: {listed - actual}"


@pytest.mark.parametrize("method,tpl,path,allowed,body", MATRIX, ids=[f"{m_} {t}" for m_, t, *_ in MATRIX])
def test_role_endpoint_matrix(client, auth, method, tpl, path, allowed, body):
    if body == "ASSUMPTIONS":
        body = client.get("/api/assumptions", headers=auth("coordinator")).json()["values"]
    anon = client.request(method, path, json=body)
    if allowed == "PUBLIC":
        assert anon.status_code not in (403,) and (tpl != "/health" or anon.status_code == 200)
        return
    assert anon.status_code == 401, f"anonymous got {anon.status_code}"
    for role in (U, T, C):                       # coordinator last: it may reset the database
        r = client.request(method, path, json=body, headers=auth(LOGIN[role]))
        if role in allowed:
            assert r.status_code not in (401, 403), f"{role} wrongly blocked: {r.status_code} {r.text[:200]}"
        else:
            assert r.status_code == 403, f"{role} should get 403, got {r.status_code}"


def test_other_customers_shipment_returns_404_not_403(client, auth):
    assert client.get("/api/customer/me/shipments/SHP-PTH-1116-01", headers=auth("customer_a")).status_code == 200
    assert client.get("/api/customer/me/shipments/SHP-PTH-1116-01", headers=auth("customer_b")).status_code == 404
    assert client.get("/api/customer/me/shipments/SHP-AMV-1116-01", headers=auth("customer_a")).status_code == 404
    assert client.get("/api/customer/me/shipments/SHP-H001", headers=auth("customer_a")).status_code == 404
    mine = client.get("/api/customer/me/orders", headers=auth("customer_b")).json()
    assert mine and all(o["id"] not in ("ORD-PTH-1116-01", "ORD-PTH-1116-02") for o in mine)


def test_other_drivers_shipment_returns_404_not_403(client, auth):
    r = client.post("/api/transporter/shipments/SHP-PTH-1116-01/milestones", headers=auth("driver2"), json={"to_state": "AT_PLANT_GATE"})
    assert r.status_code == 404
    assert client.post("/api/transporter/shipments/SHP-PTH-1116-01/pod", headers=auth("driver2"),
                       json={"recipient_name": "Someone"}).status_code == 404
    assert [s["id"] for s in client.get("/api/transporter/me/shipments", headers=auth("driver2")).json()] == ["SHP-PTH-1116-02"]


def test_other_customers_alert_returns_404(client, auth):
    stage_g1(client, auth)
    mine = client.get("/api/customer/me/alerts", headers=auth("customer_a")).json()
    assert mine
    r = client.post(f"/api/customer/me/alerts/{mine[0]['id']}/acknowledge", headers=auth("customer_b"))
    assert r.status_code == 404
    assert client.post(f"/api/customer/me/alerts/{mine[0]['id']}/acknowledge", headers=auth("customer_a")).status_code == 200


FORBIDDEN = ("freight", "sla", "penalty", "cost", "rate", "w_late", "w_stock", "risk_index", "p_late", "p_stockout",
             "transporter", "sigma", "total", "customer_id", "customer_name", "threshold", "saving")


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_customer_responses_contain_no_internal_keys(client, auth):
    """After a full intervention, every customer endpoint is still free of internal data."""
    co, cu = auth("coordinator"), auth("customer_a")
    stage_g1(client, auth)
    case = client.post("/api/shipments/SHP-PTH-1116-01/scenarios", headers=co).json()
    client.post(f"/api/interventions/{case['id']}/approve", headers=co,
                json={"selected_scenario_id": scenario(case, "REROUTE")["id"]})
    alerts = client.get("/api/customer/me/alerts", headers=cu).json()
    paths = ["/api/customer/me/orders", "/api/customer/me/shipments", "/api/customer/me/shipments/SHP-PTH-1116-01",
             "/api/customer/me/alerts"]
    for p in paths:
        r = client.get(p, headers=cu)
        assert r.status_code == 200
        bad = [k for k in _keys(r.json()) if any(f in k.lower() for f in FORBIDDEN)]
        assert not bad, f"{p} leaks keys {bad}"
        text = json.dumps(r.json())
        assert "Rs " not in text and "ORD-AMV-1116-01" not in text and "Sai Krupa" not in text
    # before/after wording: evaluating first, initiated only after the transactional apply
    msgs = " ".join(a["message"] + " " + a["suggested_action"] for a in alerts)
    assert "evaluating an alternate route" in msgs and "Rerouting has been initiated" in msgs
    assert "new commitment" not in json.dumps(client.get("/api/customer/me/orders", headers=cu).json()).lower()


def test_login_throttle_and_inactive_user(client, db):
    from app import models as m
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "customer_c", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "customer_c", "password": "wrong"}).status_code == 429
    # role and active flag are re-read from the database on every request
    from tests.conftest import login
    hdr = login(client, "customer_b")
    assert client.get("/api/auth/me", headers=hdr).status_code == 200
    db.query(m.User).filter(m.User.username == "customer_b").update({"is_active": False})
    db.commit()
    assert client.get("/api/auth/me", headers=hdr).status_code == 401
