"""Bonus features: gate slot booking, invoice / proof-of-delivery documents, and the customer chat assistant."""
import threading
from datetime import datetime, timedelta

import pytest

from app import config
from app import models as m
from app.db import SessionLocal
from app.services import docgen, gate as gate_svc
from tests.conftest import login, stage_g1

NEW_ORDER = {"route_id": "R2", "transporter_id": "TR-1", "product_code": "FILM-L30", "quantity_tonnes": 20}
PDF = docgen.make_pdf("TEST INVOICE", ["line one", "line two"])
PNG = docgen.make_png()
JPG = b"\xff\xd8\xff\xe0" + b"0" * 200 + b"\xff\xd9"
IST = timedelta(hours=5, minutes=30)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def slot_at(client, co, hour, day=0):
    """The slot starting at this IST hour of the simulated day (day 0 = 16 Nov 2026)."""
    start = datetime(2026, 11, 16, hour) - IST + timedelta(days=day)
    slots = client.get("/api/gate/overview", headers=co).json()["slots"]
    return next(x for x in slots if x["slot_start"] == iso(start))


def new_order(client, co, **over):
    r = client.post("/api/orders", headers=co, json={**NEW_ORDER, **over})
    assert r.status_code == 201, r.text
    return r.json()


def book(client, co, shipment_id, slot_id, **extra):
    return client.post("/api/gate/bookings", headers=co, json={"shipment_id": shipment_id, "slot_id": slot_id, **extra})


def upload(client, hdr, path, data, content_type="application/octet-stream"):
    return client.post(path, headers={**hdr, "Content-Type": content_type}, content=data)


# =============================================================================== GATE SLOTS
def test_gate_overview_has_hourly_slots_capacity_and_states(client, auth):
    co = auth("coordinator")
    ov = client.get("/api/gate/overview", headers=co).json()
    assert len(ov["slots"]) == 5 * 24 and ov["default_capacity"] == 3 and "Gate 2" in ov["gate_name"]
    full, closed, two = slot_at(client, co, 7), slot_at(client, co, 13), slot_at(client, co, 6)
    assert full["state"] == "FULL" and full["booked"] == 3 and full["available"] == 0
    assert closed["state"] == "UNAVAILABLE" and closed["note"] == "Weighbridge calibration"
    assert two["booked"] == 2 and two["available"] == 1 and two["state"] == "OPEN"
    assert {b["status"] for b in two["bookings"]} == {"CHECKED_IN"}
    assert slot_at(client, co, 3, day=0)["state"] == "PAST"                  # simulated time is 06:00 IST
    assert all(slot_at(client, co, h)["state"] == "OPEN" for h in (9, 14))


def test_booking_flow_driver_sees_it_checks_in_and_departure_completes_it(client, auth):
    co = auth("coordinator")
    o = new_order(client, co)
    sid, dr = o["shipment_id"], auth("driver15")
    s8 = slot_at(client, co, 8)
    r = book(client, co, sid, s8["id"])
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "BOOKED" and b["vehicle_label"] == o["vehicle_label"] and b["driver_username"] == "driver15"
    assert slot_at(client, co, 8)["booked"] == 1 and slot_at(client, co, 8)["available"] == 2
    # the driver sees the appointment with the gate details, but cannot check in yet (simulated 06:00; opens 07:00)
    mine = client.get("/api/transporter/me/gate", headers=dr).json()
    assert [x["id"] for x in mine] == [b["id"]] and mine[0]["status"] == "BOOKED" and "Gate 2" in mine[0]["gate_name"]
    assert mine[0]["can_check_in"] is False and "opens at" in mine[0]["check_in_hint"]
    early = client.post(f"/api/transporter/gate/bookings/{b['id']}/check-in", headers=dr)
    assert early.status_code == 409 and "Too early" in early.json()["detail"]
    # the simulation clock moves to 07:00 IST: now the driver can check in
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 60})
    assert client.get("/api/transporter/me/gate", headers=dr).json()[0]["can_check_in"] is True
    ok = client.post(f"/api/transporter/gate/bookings/{b['id']}/check-in", headers=dr)
    assert ok.status_code == 200 and ok.json()["status"] == "CHECKED_IN" and ok.json()["checked_in_at"]
    assert client.post(f"/api/transporter/gate/bookings/{b['id']}/check-in", headers=dr).status_code == 200   # idempotent
    # coordinator sees the new status; capacity is unchanged by check-in
    bk = next(x for x in client.get("/api/gate/bookings?scope=upcoming", headers=co).json() if x["id"] == b["id"])
    assert bk["status"] == "CHECKED_IN" and slot_at(client, co, 8)["booked"] == 1
    # the vehicle leaves Plant X: the appointment completes by itself and still counts as used
    for st in ("LOADING", "AT_PLANT_GATE", "IN_TRANSIT"):
        assert client.post(f"/api/transporter/shipments/{sid}/milestones", headers=dr, json={"to_state": st}).status_code == 200
    done = next(x for x in client.get("/api/gate/bookings?scope=history", headers=co).json() if x["id"] == b["id"])
    assert done["status"] == "COMPLETED" and done["completed_at"] and slot_at(client, co, 8)["booked"] == 1
    actions = [a["action"] for a in client.get("/api/audit-events?limit=200", headers=co).json()]
    for needed in ("GATE_BOOKING_CREATED", "GATE_BOOKING_CHECKED_IN", "GATE_BOOKING_COMPLETED"):
        assert needed in actions
    assert any(i["kind"] == "GATE" and sid in i["title"] for i in client.get("/api/activity?limit=100", headers=co).json())


def test_booking_rules_are_enforced(client, auth):
    co = auth("coordinator")
    o = new_order(client, co)
    sid = o["shipment_id"]
    open_slot, full, closed, past = (slot_at(client, co, h) for h in (9, 7, 13, 3))
    assert book(client, co, sid, full["id"]).status_code == 409 and "full" in book(client, co, sid, full["id"]).json()["detail"]
    assert "unavailable" in book(client, co, sid, closed["id"]).json()["detail"]
    assert "past" in book(client, co, sid, past["id"]).json()["detail"]
    assert book(client, co, "SHP-1003", open_slot["id"]).status_code == 409                   # already in transit
    assert book(client, co, "NOPE", open_slot["id"]).status_code == 404
    assert book(client, co, sid, open_slot["id"], transporter_id="TR-2").status_code == 422   # not the shipment's transporter
    other_driver = next(u for u in client.get("/api/reference-data", headers=co).json()["drivers"] if u["transporter_id"] == "TR-2")
    assert book(client, co, sid, open_slot["id"], driver_user_id=other_driver["id"]).status_code == 422
    assert book(client, co, sid, open_slot["id"]).status_code == 201
    dup = book(client, co, sid, slot_at(client, co, 10)["id"])
    assert dup.status_code == 409 and "already has an active booking" in dup.json()["detail"]
    assert slot_at(client, co, 10)["booked"] == 0                                              # nothing leaked into the other slot
    assert "SHP-1004" in [b["shipment_id"] for b in client.get("/api/gate/bookings?scope=upcoming", headers=co).json()]


def test_reschedule_releases_the_old_slot_and_never_double_books(client, auth):
    co = auth("coordinator")
    sid = new_order(client, co)["shipment_id"]
    a, b, full = slot_at(client, co, 9), slot_at(client, co, 10), slot_at(client, co, 7)
    bk = book(client, co, sid, a["id"]).json()
    assert slot_at(client, co, 9)["booked"] == 2                                                 # seeded SHP-1004 + the new one
    bad = client.post(f"/api/gate/bookings/{bk['id']}/reschedule", headers=co, json={"slot_id": full["id"]})
    assert bad.status_code == 409
    assert slot_at(client, co, 9)["booked"] == 2 and slot_at(client, co, 7)["booked"] == 3     # a failed move changes nothing
    assert client.post(f"/api/gate/bookings/{bk['id']}/reschedule", headers=co, json={"slot_id": a["id"]}).status_code == 422
    ok = client.post(f"/api/gate/bookings/{bk['id']}/reschedule", headers=co, json={"slot_id": b["id"]})
    assert ok.status_code == 200 and ok.json()["slot_id"] == b["id"] and ok.json()["rescheduled_from"] == a["slot_start"]
    assert slot_at(client, co, 9)["booked"] == 1 and slot_at(client, co, 10)["booked"] == 1
    assert "GATE_BOOKING_RESCHEDULED" in [x["action"] for x in client.get("/api/audit-events", headers=co).json()]


def test_cancel_releases_capacity_and_allows_a_new_booking(client, auth):
    co = auth("coordinator")
    sid = new_order(client, co)["shipment_id"]
    s9 = slot_at(client, co, 9)
    bk = book(client, co, sid, s9["id"]).json()
    r = client.post(f"/api/gate/bookings/{bk['id']}/cancel", headers=co, json={"reason": "Truck not ready"})
    assert r.json()["status"] == "CANCELLED" and r.json()["cancel_reason"] == "Truck not ready"
    assert slot_at(client, co, 9)["booked"] == 1
    assert client.post(f"/api/gate/bookings/{bk['id']}/cancel", headers=co, json={}).status_code == 200   # idempotent
    assert client.post(f"/api/gate/bookings/{bk['id']}/reschedule", headers=co, json={"slot_id": s9["id"]}).status_code == 409
    assert book(client, co, sid, slot_at(client, co, 10)["id"]).status_code == 201                    # rebooking after a cancel
    seeded = next(b for b in client.get("/api/gate/bookings?scope=history", headers=co).json() if b["status"] == "COMPLETED")
    assert client.post(f"/api/gate/bookings/{seeded['id']}/cancel", headers=co, json={}).status_code == 409


def test_slot_capacity_changes_show_overbooked_and_unavailable(client, auth):
    co = auth("coordinator")
    s7 = slot_at(client, co, 7)
    r = client.put(f"/api/gate/slots/{s7['id']}", headers=co, json={"capacity": 1})
    assert r.json()["state"] == "OVERBOOKED" and r.json()["booked"] == 3 and r.json()["available"] == 0
    s9 = slot_at(client, co, 9)
    client.put(f"/api/gate/slots/{s9['id']}", headers=co, json={"closed": True, "note": "Gate cleaning"})
    assert slot_at(client, co, 9)["state"] == "UNAVAILABLE"
    sid = new_order(client, co)["shipment_id"]
    assert book(client, co, sid, s9["id"]).status_code == 409
    assert client.put(f"/api/gate/slots/{s9['id']}", headers=co, json={"capacity": 99}).status_code == 422
    assert "GATE_SLOT_UPDATED" in [a["action"] for a in client.get("/api/audit-events", headers=co).json()]


def test_unused_booking_becomes_missed_and_releases_capacity(client, auth):
    co = auth("coordinator")
    sid = new_order(client, co)["shipment_id"]
    bk = book(client, co, sid, slot_at(client, co, 6)["id"]).json()                              # the slot we are in
    assert slot_at(client, co, 6)["booked"] == 3
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 90})              # simulated 07:30: slot ended
    missed = next(b for b in client.get("/api/gate/bookings?scope=history", headers=co).json() if b["id"] == bk["id"])
    assert missed["status"] == "MISSED"
    assert slot_at(client, co, 6)["booked"] == 2
    assert "GATE_BOOKING_MISSED" in [a["action"] for a in client.get("/api/audit-events?limit=200", headers=co).json()]
    assert book(client, co, sid, slot_at(client, co, 9)["id"]).status_code == 201                # a missed booking can be rebooked


def test_two_simultaneous_requests_cannot_both_take_the_last_place(client, auth):
    co = auth("coordinator")
    a = new_order(client, co)["shipment_id"]
    b = new_order(client, co, transporter_id="TR-2")["shipment_id"]
    slot = slot_at(client, co, 14)
    client.put(f"/api/gate/slots/{slot['id']}", headers=co, json={"capacity": 1})
    me = login(client, "coordinator")
    with SessionLocal() as db:
        user = db.query(m.User).filter(m.User.username == "coordinator").one()
    results = []

    def attempt(shipment):
        with SessionLocal() as db:
            try:
                gate_svc.book(db, user, shipment, slot["id"], None, None)
                results.append("ok")
            except Exception as e:  # HTTPException 409
                results.append(getattr(e, "status_code", repr(e)))
    threads = [threading.Thread(target=attempt, args=(x,)) for x in (a, b)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(map(str, results)) == ["409", "ok"]
    assert slot_at(client, co, 14)["booked"] == 1 and me


def test_gate_access_rules(client, auth):
    co = auth("coordinator")
    sid = new_order(client, co)["shipment_id"]
    bk = book(client, co, sid, slot_at(client, co, 8)["id"]).json()
    client.post("/api/simulation/clock/advance", headers=co, json={"minutes": 60})
    assert client.post(f"/api/transporter/gate/bookings/{bk['id']}/check-in", headers=auth("driver2")).status_code == 404   # not their booking
    assert client.get("/api/transporter/me/gate", headers=auth("driver2")).json() == [] or all(
        x["id"] != bk["id"] for x in client.get("/api/transporter/me/gate", headers=auth("driver2")).json())
    for who in ("customer_a", "driver1"):
        assert client.get("/api/gate/overview", headers=auth(who)).status_code == 403
        assert client.post("/api/gate/bookings", headers=auth(who), json={"shipment_id": sid, "slot_id": 1}).status_code == 403
    assert client.post(f"/api/gate/bookings/{bk['id']}/complete", headers=co).status_code == 409        # must be checked in first
    assert client.get("/api/gate/summary", headers=co).json()["booked"] >= 5


# ================================================================================ DOCUMENTS
def test_invoice_upload_download_and_customer_isolation(client, auth):
    co = auth("coordinator")
    r = upload(client, co, "/api/orders/ORD-G1/invoice?filename=invoice-g1.pdf&invoice_number=INV-G1-001", PDF)
    assert r.status_code == 201, r.text
    doc = r.json()["document"]
    assert doc["version"] == 1 and doc["status"] == "ISSUED" and doc["content_type"] == "application/pdf" and doc["invoice_number"] == "INV-G1-001"
    cust = client.get("/api/customer/me/documents", headers=auth("customer_a")).json()
    mine = next(d for d in cust if d["id"] == doc["id"])
    assert mine["kind"] == "INVOICE" and mine["status"] == "Available" and mine["uploaded_at"]
    got = client.get(f"/api/documents/{doc['id']}/download", headers=auth("customer_a"))
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf" and "attachment" in got.headers["content-disposition"]
    assert got.headers["x-content-type-options"] == "nosniff" and "no-store" in got.headers["cache-control"]
    # nobody else can read it
    assert client.get(f"/api/documents/{doc['id']}/download", headers=auth("customer_b")).status_code == 404
    assert client.get(f"/api/documents/{doc['id']}/download", headers=auth("driver1")).status_code == 404
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 401
    assert doc["id"] not in [d["id"] for d in client.get("/api/customer/me/documents", headers=auth("customer_b")).json()]
    assert client.get(f"/api/documents/{doc['id']}/download", headers=co).content == PDF
    audit = client.get("/api/audit-events?limit=100", headers=co).json()
    assert {"DOCUMENT_UPLOADED", "DOCUMENT_DOWNLOADED"} <= {a["action"] for a in audit}
    # the customer is notified in safe words
    note = next(a for a in client.get("/api/customer/me/alerts", headers=auth("customer_a")).json() if "Invoice" in a["title"])
    assert "Documents tab" in note["message"]


def test_invoice_replacement_creates_an_audited_new_version(client, auth):
    co = auth("coordinator")
    first = upload(client, co, "/api/orders/ORD-G1/invoice?filename=v1.pdf", PDF).json()["document"]
    refused = upload(client, co, "/api/orders/ORD-G1/invoice?filename=v2.pdf", docgen.make_pdf("v2", ["x"]))
    assert refused.status_code == 409 and "reason" in refused.json()["detail"]
    v2_bytes = docgen.make_pdf("CORRECTED", ["fixed amount"])
    ok = upload(client, co, "/api/orders/ORD-G1/invoice?filename=v2.pdf&reason=Wrong%20quantity%20on%20the%20first%20invoice", v2_bytes)
    assert ok.status_code == 201
    v2 = ok.json()["document"]
    assert v2["version"] == 2 and v2["is_current"] and v2["replace_reason"].startswith("Wrong quantity")
    docs = client.get("/api/orders/ORD-G1/documents", headers=co).json()
    assert [d["version"] for d in docs["invoices"]] == [2, 1] and docs["invoices"][1]["status"] == "SUPERSEDED"
    # the customer now sees ONLY the current version; the old one is gone for them but kept for the coordinator
    ids = [d["id"] for d in client.get("/api/customer/me/documents", headers=auth("customer_a")).json() if d["kind"] == "INVOICE" and d["order_id"] == "ORD-G1"]
    assert ids == [v2["id"]]
    assert client.get(f"/api/documents/{first['id']}/download", headers=auth("customer_a")).status_code == 404
    assert client.get(f"/api/documents/{first['id']}/download", headers=co).content == PDF
    assert client.get(f"/api/documents/{v2['id']}/download", headers=auth("customer_a")).content == v2_bytes
    rep = next(a for a in client.get("/api/audit-events?limit=100", headers=co).json() if a["action"] == "DOCUMENT_REPLACED")
    assert rep["before"]["version"] == 1 and rep["after"]["version"] == 2 and "Wrong quantity" in rep["after"]["reason"]


@pytest.mark.parametrize("name,data,status", [
    ("fake.pdf", b"this is not a pdf at all", 415),                    # content does not match
    ("photo.jpg", PNG, 415),                                           # PNG content, JPG name
    ("script.exe", PDF, 415),                                          # extension not allowed
    ("noext", PDF, 415),
    ("empty.pdf", b"", 422),
])
def test_upload_validation_uses_the_file_content(client, auth, name, data, status):
    r = upload(client, auth("coordinator"), f"/api/orders/ORD-G1/invoice?filename={name}", data)
    assert r.status_code == status, r.text


def test_all_allowed_types_work_and_filenames_are_sanitised(client, auth, tmp_path):
    co = auth("coordinator")
    out = {}
    for i, (name, data) in enumerate([("a.pdf", PDF), ("b.png", PNG), ("c.jpg", JPG), ("d.jpeg", JPG)]):
        reason = "&reason=Replacing%20for%20test" if i else ""
        r = upload(client, co, f"/api/orders/ORD-G1/invoice?filename={name}{reason}", data)
        assert r.status_code == 201, (name, r.text)
        out[name] = r.json()["document"]["content_type"]
    assert out == {"a.pdf": "application/pdf", "b.png": "image/png", "c.jpg": "image/jpeg", "d.jpeg": "image/jpeg"}
    nasty = upload(client, co, "/api/orders/ORD-G1/invoice?filename=..%2F..%2Fetc%2Fpasswd%20%3Cscript%3E.pdf&reason=Path%20traversal%20test", PDF)
    d = nasty.json()["document"]
    assert nasty.status_code == 201 and "/" not in d["original_filename"] and ".." not in d["original_filename"] and "<" not in d["original_filename"]
    with SessionLocal() as db:
        row = db.get(m.Document, d["id"])
        stored = config.DOC_DIR / row.stored_name
        assert stored.is_file() and stored.parent == config.DOC_DIR and row.stored_name != d["original_filename"]
        assert len(row.stored_name) > 30                                  # generated, not user-controlled
    # the private folder is not reachable through the website
    leak = client.get(f"/{row.stored_name}")
    assert leak.content != PDF and leak.headers.get("content-type", "").split(";")[0] != "application/pdf"
    assert client.get(f"/documents/{row.stored_name}").content != PDF
    assert client.get(f"/api/documents/{d['id']}/download", headers=co).headers["content-disposition"].count("..") == 0


def test_size_limit_is_enforced(client, auth, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1500)
    big = docgen.make_pdf("big", ["x" * 100] * 30)
    assert len(big) > 1500
    r = upload(client, auth("coordinator"), "/api/orders/ORD-G1/invoice?filename=big.pdf", big)
    assert r.status_code == 413 and "limit" in r.json()["detail"]
    assert config.MAX_UPLOAD_MB == 10                                       # the real default is 10 MB


def test_proof_of_delivery_driver_coordinator_customer_flow(client, auth, db):
    co, dr, cust = auth("coordinator"), auth("driver11"), auth("customer_c")
    state = client.get("/api/shipments/SHP-1011", headers=co).json()
    assert state["state"] == "ARRIVED_AT_CUSTOMER_GATE"
    # before the document exists the customer is told it is not available
    assert not [d for d in client.get("/api/customer/me/documents", headers=cust).json() if d["kind"] == "POD"]
    r = upload(client, dr, "/api/transporter/shipments/SHP-1011/pod-document?filename=signed-note.png&recipient_name=Anita%20Rao", PNG)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["shipment"]["state"] == "DELIVERED" and out["shipment"]["pod_recipient"] == "Anita Rao"
    d = out["document"]
    assert d["kind"] == "POD" and d["status"] == "UPLOADED" and d["recipient_name"] == "Anita Rao" and d["shipment_id"] == "SHP-1011"
    now = client.get("/api/simulation/clock", headers=co).json()["sim_now"]
    assert d["delivered_sim_at"] == now                                    # the delivery time is the SIMULATION clock
    sh = client.get("/api/shipments/SHP-1011", headers=co).json()
    assert sh["state"] == "DELIVERED" and sh["delivered_at"] == now
    # coordinator sees and verifies it
    docs = client.get("/api/orders/ORD-1011/documents", headers=co).json()
    pod = next(x for x in docs["shipments"] if x["shipment_id"] == "SHP-1011")
    assert pod["pod_status"] == "UPLOADED" and pod["documents"][0]["id"] == d["id"]
    assert client.get(f"/api/documents/{d['id']}/download", headers=co).content == PNG
    v = client.post(f"/api/documents/{d['id']}/verify", headers=co)
    assert v.status_code == 200 and v.json()["status"] == "VERIFIED" and v.json()["verified_by_name"]
    # the customer downloads it; others cannot
    got = client.get(f"/api/documents/{d['id']}/download", headers=cust)
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    for hidden in ("customer_a", "customer_b"):
        assert client.get(f"/api/documents/{d['id']}/download", headers=auth(hidden)).status_code == 404
    assert client.get(f"/api/documents/{d['id']}/download", headers=auth("driver10")).status_code == 404
    assert client.get(f"/api/documents/{d['id']}/download", headers=dr).status_code == 200            # the uploading driver
    assert any("Proof of delivery" in a["title"] for a in client.get("/api/customer/me/alerts", headers=cust).json())
    actions = [a["action"] for a in client.get("/api/audit-events?limit=100", headers=co).json()]
    assert {"POD_DOCUMENT_UPLOADED", "POD_VERIFIED", "DOCUMENT_DOWNLOADED"} <= set(actions)
    # a replacement document is a new audited version
    r2 = upload(client, dr, "/api/transporter/shipments/SHP-1011/pod-document?filename=clearer.png&recipient_name=Anita%20Rao", PNG)
    assert r2.status_code == 201 and r2.json()["document"]["version"] == 2
    assert [x["id"] for x in client.get("/api/customer/me/documents", headers=cust).json() if x["kind"] == "POD"] == [r2.json()["document"]["id"]]


def test_pod_rules(client, auth):
    dr1 = auth("driver1")
    base = "/api/transporter/shipments/SHP-G1/pod-document?filename=x.png&recipient_name=Bob"
    assert upload(client, dr1, base, PNG).status_code == 409                                 # still loading, not at the customer gate
    assert upload(client, auth("driver2"), base, PNG).status_code == 404                     # not their shipment
    r = upload(client, auth("driver11"), "/api/transporter/shipments/SHP-1011/pod-document?filename=x.png&recipient_name=B", PNG)
    assert r.status_code == 422                                                              # recipient too short (query validation)
    assert upload(client, auth("driver11"), "/api/transporter/shipments/SHP-1011/pod-document?filename=x.pdf&recipient_name=Bob", PNG).status_code == 415
    assert client.get("/api/shipments/SHP-1011", headers=auth("coordinator")).json()["state"] == "ARRIVED_AT_CUSTOMER_GATE"  # nothing changed
    assert client.post("/api/documents/999999/verify", headers=auth("coordinator")).status_code == 404


def test_documents_overview_and_seeded_invoices(client, auth):
    co = auth("coordinator")
    rows = {r["order_id"]: r for r in client.get("/api/documents/overview", headers=co).json()}
    assert rows["ORD-1003"]["invoice"]["invoice_number"] == "INV-2026-1003" and rows["ORD-G1"]["invoice"] is None
    assert rows["ORD-1011"]["pods_expected"] == 1 and rows["ORD-1011"]["pods_delivered"] == 0
    seeded = client.get("/api/customer/me/documents", headers=auth("customer_b")).json()
    inv = next(d for d in seeded if d["order_id"] == "ORD-1003")
    assert client.get(f"/api/documents/{inv['id']}/download", headers=auth("customer_b")).content.startswith(b"%PDF-")
    assert client.get(f"/api/documents/{inv['id']}/download", headers=auth("customer_a")).status_code == 404


def test_document_ids_are_integers_and_unknown_ids_are_404(client, auth):
    co = auth("coordinator")
    trav = client.get("/api/documents/../../etc/passwd/download", headers=co)       # the client normalises the dots
    assert trav.status_code == 404 or trav.headers["content-type"].startswith("text/html")   # website page, never a file
    assert b"root:" not in trav.content
    assert client.get("/api/documents/%2e%2e%2f%2e%2e%2fetc%2fpasswd/download", headers=co).status_code in (404, 422)
    assert client.get("/api/documents/abc/download", headers=co).status_code == 422
    assert client.get("/api/documents/999999/download", headers=co).status_code == 404


# ================================================================================= CHAT
def ask(client, hdr, message, order_id=None):
    r = client.post("/api/customer/me/chat", headers=hdr, json={"message": message, "order_id": order_id})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("message,intent", [
    ("Where is my order?", "WHERE"), ("What is my current shipment status?", "STATUS"),
    ("When will my delivery arrive?", "ETA"), ("Has my order been dispatched?", "DISPATCH"),
    ("Why is my order delayed?", "DELAY"), ("What was the original promised delivery date?", "PROMISE"),
    ("What is the updated expected delivery?", "UPDATED_ETA"), ("Has my shipment reached the customer gate?", "GATE"),
    ("Is my proof of delivery available?", "POD"), ("Is my invoice ready?", "INVOICE"),
    ("hello", "HELLO"), ("asdf qwer", "UNKNOWN"), ("How much is the freight cost?", "COMMERCIAL"),
])
def test_chat_understands_the_example_questions(client, auth, message, intent):
    assert ask(client, auth("customer_a"), message)["intent"] == intent


def test_chat_where_is_my_order_uses_real_position_and_timestamp(client, auth):
    cu, co = auth("customer_a"), auth("coordinator")
    r = ask(client, cu, "Where is my order ORD-1007?")
    assert r["order_id"] == "ORD-1007" and r["position"]["near"] and r["position"]["progress_pct"] > 0
    assert "Latest reported position: near" in r["text"] and "IST" in r["text"]
    truth = client.get("/api/customer/me/shipments/SHP-1007", headers=cu).json()["last_reported_position"]
    assert r["position"]["lat"] == truth["lat"] and r["position"]["reported_at"] == truth["reported_at"]   # not invented
    facts = {f["label"]: f["value"] for f in r["facts"]}
    assert facts["Status"] == "In transit" and "Original promise" in facts and "Updated expected delivery" in facts
    assert any(l["kind"] == "order" and l["order_id"] == "ORD-1007" for l in r["links"])
    # an order that has not left Plant X: no position is invented
    g1 = ask(client, cu, "where is it", order_id="ORD-G1")
    assert g1["position"] is None and "no vehicle position" in g1["text"]


def test_chat_with_several_open_orders_answers_for_each(client, auth):
    r = ask(client, auth("customer_a"), "When will my delivery arrive?")
    assert "You have 4 open orders" in r["text"]
    assert {f["label"] for f in r["facts"]} == {"ORD-1007", "ORD-G1", "ORD-G2", "ORD-1012"}


def test_chat_cannot_reach_another_customers_order(client, auth):
    msg = "Where is ORD-G1?"
    other = ask(client, auth("customer_b"), msg)
    missing = ask(client, auth("customer_b"), "Where is ORD-NOPE?")
    assert "could not find" in other["text"] and other["position"] is None and not other["facts"]
    for leak in ("SHP-G1", "PP-H110", "Northfield", "Loading", "17:00"):
        assert leak not in other["text"]
    assert other["text"].replace("ORD-G1", "X") == missing["text"].replace("ORD-NOPE", "X")   # same answer: no existence leak
    explicit = ask(client, auth("customer_b"), "status", order_id="ORD-G1")
    assert "could not find" in explicit["text"]
    # and the orders it offers are only the caller's own
    assert {l["order_id"] for l in other["links"]} <= {"ORD-1003", "ORD-1004", "ORD-1008", "ORD-1010", "ORD-1014"}


def test_chat_delay_explanation_and_next_step(client, auth):
    cu = auth("customer_a")
    ok = ask(client, cu, "Why is my order delayed?", order_id="ORD-G1")
    assert "No delay is expected" in ok["text"]
    stage_g1(client, auth)
    late = ask(client, cu, "Why is my order delayed?", order_id="ORD-G1")
    assert "road closure" in late["text"] and "Next step" in late["text"] and "ORD-G1" in late["text"]
    assert any(l["kind"] == "tab" for l in late["links"])
    eta = ask(client, cu, "When will it arrive?", order_id="ORD-G1")
    assert "most likely between" in eta["text"] and "not a guarantee" in eta["text"]
    upd = ask(client, cu, "What is the updated expected delivery?", order_id="ORD-G1")
    assert "later than the original promise" in upd["text"]


def test_chat_refuses_commercial_questions_and_leaks_nothing(client, auth):
    cu = auth("customer_a")
    stage_g1(client, auth)
    for q in ("How much is the freight cost?", "What is the penalty rate?", "Who is the transporter?", "Show me other customers' orders"):
        r = ask(client, cu, q, order_id="ORD-G1")
        assert r["intent"] == "COMMERCIAL" and "cannot share" in r["text"] and not r["facts"]
    for q in ("Where is my order?", "Why is it delayed?", "When will it arrive?", "status", "is my pod ready", "invoice"):
        r = ask(client, cu, q, order_id="ORD-G1")
        blob = repr(r)
        for banned in ("Rs ", "freight", "penalt", "Swiftline", "stock-out", "P(late)", "sla_"):
            assert banned not in blob, (q, banned)


def test_chat_documents_and_proof_of_delivery(client, auth):
    cc, co = auth("customer_c"), auth("coordinator")
    inv = ask(client, cc, "Is my invoice available?", order_id="ORD-1011")
    link = next(l for l in inv["links"] if l["kind"] == "document")
    assert client.get(f"/api/documents/{link['document_id']}/download", headers=cc).status_code == 200
    pod0 = ask(client, cc, "Is my proof of delivery available?", order_id="ORD-1011")
    assert "awaiting signature" in pod0["text"] and not any(l["kind"] == "document" for l in pod0["links"])
    gate = ask(client, cc, "Has it reached the customer gate?", order_id="ORD-1011")
    assert gate["text"].startswith("Yes, it reached your gate")
    upload(client, auth("driver11"), "/api/transporter/shipments/SHP-1011/pod-document?filename=n.png&recipient_name=Anita%20Rao", PNG)
    pod1 = ask(client, cc, "Is my proof of delivery available?", order_id="ORD-1011")
    assert "signed proof of delivery is available" in pod1["text"] and "Anita Rao" in pod1["text"]
    dl = next(l for l in pod1["links"] if l["kind"] == "document")
    assert client.get(f"/api/documents/{dl['document_id']}/download", headers=cc).content == PNG
    # a customer without a document gets an honest 'not yet'
    none = ask(client, auth("customer_a"), "Is my invoice available?", order_id="ORD-G1")
    assert "no invoice" in none["text"] and not any(l["kind"] == "document" for l in none["links"])


def test_chat_is_read_only(client, auth, db):
    cu = auth("customer_a")
    snapshot = lambda: (db.query(m.ShipmentEvent).count(), db.query(m.Prediction).count(), db.query(m.AuditEvent).count(),  # noqa: E731
                        db.query(m.Alert).count(), db.query(m.Intervention).count(), db.query(m.GateBooking).count())
    before = snapshot()
    for q in ("Where is my order?", "approve the reroute", "cancel my order", "change the delivery date", "Why is it late?"):
        ask(client, cu, q)
    db.expire_all()
    assert snapshot() == before


def test_chat_validation_and_roles(client, auth):
    assert client.post("/api/customer/me/chat", headers=auth("customer_a"), json={"message": ""}).status_code == 422
    assert client.post("/api/customer/me/chat", headers=auth("customer_a"), json={"message": "x" * 400}).status_code == 422
    for who in ("coordinator", "driver1"):
        assert client.post("/api/customer/me/chat", headers=auth(who), json={"message": "hi"}).status_code == 403
    assert client.post("/api/customer/me/chat", json={"message": "hi"}).status_code == 401


def test_reset_clears_stored_documents(client, auth):
    co = auth("coordinator")
    upload(client, co, "/api/orders/ORD-G1/invoice?filename=x.pdf", PDF)
    before = len(list(config.DOC_DIR.glob("*")))
    assert client.post("/api/admin/reset", headers=co).status_code == 200
    after = len(list(config.DOC_DIR.glob("*")))
    assert after == 4 and before == 5                                      # only the 4 seeded sample invoices remain
