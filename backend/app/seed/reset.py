"""Deterministic seed with one-command reset:  python -m app.seed.reset

All data is fictional. Demo credentials are seeded only when DEMO_MODE=true.
No value depends on the wall clock: the simulation starts at SIM_START.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta

import numpy as np
from argon2 import PasswordHasher

from .. import config
from .. import models as m
from ..assumptions import Assumptions
from ..db import Base, SessionLocal, engine
from ..engine.eta import simulate_arrival
from ..engine.geo import position_at_km
from ..seeds import seed_pred
from ..services import docgen, documents as doc_svc, gate as gate_svc, paths, predictions
from ..services.core import add_event
from ..services.mapping import build_inputs
from ..services.shipments import attribute_delay
from ..simulator import truth
from .network import CIRCUITY, CUSTOMERS, ROUTES, TRANSPORTERS

SIM_START = datetime(2026, 11, 16, 0, 30)        # 06:00 Asia/Kolkata, stored as UTC
HISTORY_COUNT = 160
ROUTE_CUSTOMER = {"R1": "CUST-A", "R2": "CUST-B", "R3": "CUST-C", "R4": "CUST-C"}
DRIVER_NAMES = ["Ramesh Patil", "Suresh Jadhav", "Imran Shaikh", "Vijay Kale", "Anil Pawar", "Sanjay More", "Prakash Chavan",
                "Deepak Shinde", "Mahesh Gaikwad", "Rajesh Kulkarni", "Santosh Bhosale", "Ganesh Salunkhe", "Nitin Deshmukh",
                "Farooq Khan", "Dilip Wagh", "Amit Kadam", "Yusuf Ansari"]
RELIEF_NAMES = {"TR-1": "Sunil Mane (relief)", "TR-2": "Pramod Thorat (relief)", "TR-3": "Ashok Nikam (relief)"}
ROUTE_PRODUCT = {"R1": "PP-H110", "R2": "FILM-L30", "R3": "PACK-P40", "R4": "CAP-H08"}

# id, customer, product, qty, route, transporter, state, spec
ACTIVE = [
    ("PTH-1116-01", "CUST-A", "PP-H110", 24, "R1", "TR-1", "LOADING", {"entered_h": -0.8, "promised_h": 11.0, "planned_h": 9.0, "sla": 20000, "prio": "HIGH"}),
    ("PTH-1116-02", "CUST-A", "HDPE-B52", 24, "R1", "TR-2", "AT_PLANT_GATE", {"entered_h": -0.1, "promised_h": 11.0, "planned_h": 9.0, "sla": 2500, "prio": "NORMAL"}),
    ("AMV-1116-01", "CUST-B", "FILM-L30", 22, "R2", "TR-2", "IN_TRANSIT", {"departed_h": -1.3, "buffer_h": 2.0, "sla": 8000}),
    ("AMV-1116-02", "CUST-B", "FILM-L30", 20, "R2", "TR-1", "PLANNED", {"loading_h": 2.0, "buffer_h": 2.5, "sla": 5000}),
    ("SAT-1116-01", "CUST-C", "PACK-P40", 18, "R3", "TR-3", "IN_TRANSIT", {"departed_h": -3.0, "buffer_h": 0.25, "sla": 12000, "prio": "HIGH"}),
    ("BHW-1116-01", "CUST-C", "CAP-H08", 20, "R4", "TR-3", "IN_TRANSIT", {"departed_h": -3.0, "promised_h": -0.5, "planned_h": -2.5, "sla": 5000}),
    ("PTH-1116-03", "CUST-A", "LDPE-F20", 26, "R1", "TR-1", "IN_TRANSIT", {"departed_h": -4.4, "buffer_h": 2.0, "sla": 8000}),
    ("AMV-1116-03", "CUST-B", "FILM-L30", 24, "R2", "TR-2", "LOADING", {"entered_h": -0.3, "buffer_h": 2.5, "sla": 5000}),
    ("SAT-1116-02", "CUST-C", "PACK-P40", 18, "R3", "TR-1", "AT_PLANT_GATE", {"entered_h": -0.2, "buffer_h": 2.0, "sla": 8000}),
    ("AMV-1116-04", "CUST-B", "FILM-L30", 22, "R2", "TR-3", "IN_TRANSIT", {"departed_h": -2.5, "buffer_h": 1.5, "sla": 15000, "prio": "HIGH", "outage_h": -1.5}),
    ("BHW-1116-02", "CUST-C", "CAP-H08", 20, "R4", "TR-2", "ARRIVED_AT_CUSTOMER_GATE", {"departed_h": -6.0, "arrived_h": -0.4, "promised_h": 0.5, "planned_h": -0.6, "sla": 5000}),
    ("PTH-1116-04", "CUST-A", "HDPE-B52", 24, "R1", "TR-3", "PLANNED", {"loading_h": 4.0, "buffer_h": 3.0, "sla": 2500}),
    ("BHW-1116-03", "CUST-C", "CAP-H08", 20, "R4", "TR-1", "PLANNED", {"loading_h": 1.0, "buffer_h": 3.0, "sla": 5000}),
    ("AMV-1116-05", "CUST-B", "FILM-L30", 22, "R2", "TR-1", "IN_TRANSIT", {"departed_h": -0.4, "buffer_h": 1.5, "sla": 8000}),
]
INVENTORY = [  # customer, product, tonnes at SIM_START, t/h, unloading h, min priority qty
    ("CUST-A", "PP-H110", 25.0, 2.0, 0.5, 6.0),
    ("CUST-A", "HDPE-B52", 120.0, 1.5, 0.5, 6.0),
    ("CUST-B", "FILM-L30", 60.0, 1.2, 0.75, 5.0),
    ("CUST-C", "PACK-P40", 18.0, 1.0, 0.5, 5.0),
    ("CUST-C", "CAP-H08", 10.0, 1.0, 0.5, 6.0),     # split use case: stock lasts 10 h
]


def _h(x: float) -> datetime:
    return SIM_START + timedelta(seconds=round(x * 3600))


def _network(db) -> None:
    for cid, c in CUSTOMERS.items():
        db.add(m.Customer(id=cid, name=c["name"]))
    for tid, t in TRANSPORTERS.items():
        db.add(m.Transporter(id=tid, name=t["name"], sigma_factor=t["sigma_factor"]))
    db.flush()
    for rid, r in ROUTES.items():                      # primaries first (FK from the alternative)
        if "alternative_of" not in r:
            db.add(m.Route(id=rid, name=r["name"], destination_name=r["destination"], cost_per_km=r["cost_per_km"],
                           road_circuity_factor=CIRCUITY))
    db.flush()
    for rid, r in ROUTES.items():
        if "alternative_of" in r:
            db.add(m.Route(id=rid, name=r["name"], destination_name=r["destination"], cost_per_km=r["cost_per_km"],
                           road_circuity_factor=CIRCUITY, alternative_of_route_id=r["alternative_of"],
                           alternative_entry_decision_node_id=r["entry"], alternative_rejoin_waypoint_id=r["rejoin"]))
    db.flush()
    for rid, r in ROUTES.items():
        for seq, (wid, name, lat, lon, dn, speed) in enumerate(r["waypoints"]):
            db.add(m.RouteWaypoint(id=wid, route_id=rid, sequence=seq, name=name, lat=lat, lon=lon,
                                   is_decision_node=dn, speed_kmh_to_next=speed))
    db.flush()


def _users(db) -> dict:
    ph = PasswordHasher()
    users = {}

    def add(username, role, name, customer=None, transporter=None):
        u = m.User(username=username, password_hash=ph.hash(config.DEMO_PASSWORD), role=role, display_name=name,
                   customer_id=customer, transporter_id=transporter, is_active=True)
        db.add(u)
        users[username] = u

    add("coordinator", "COORDINATOR", "Priya Deshmukh")
    add("coordinator2", "COORDINATOR", "Arjun Mehta")
    add("customer_a", "CUSTOMER", "Meera Sharma", customer="CUST-A")
    add("customer_b", "CUSTOMER", "Rohit Deshmukh", customer="CUST-B")
    add("customer_c", "CUSTOMER", "Kavita Jadhav", customer="CUST-C")
    for i, row in enumerate(ACTIVE, start=1):
        add(f"driver{i}", "TRANSPORTER", DRIVER_NAMES[i - 1], transporter=row[5])
    for j, tid in enumerate(TRANSPORTERS, start=len(ACTIVE) + 1):     # spare drivers: free for newly created orders
        add(f"driver{j}", "TRANSPORTER", DRIVER_NAMES[j - 1], transporter=tid)
    for tid in TRANSPORTERS:                                          # reserved for the urgent lot of a split
        add(f"relief_{tid.lower().replace('-', '')}", "TRANSPORTER", RELIEF_NAMES[tid], transporter=tid)
    db.flush()
    return users


def _active(db, users, a: Assumptions) -> None:
    for i, (sid, cust, product, qty, route, trans, state, s) in enumerate(ACTIVE, start=1):
        order = m.Order(id=f"ORD-{sid}", customer_id=cust, product_code=product, quantity_tonnes=qty,
                        promised_at=_h(s.get("promised_h", 24.0)), sla_penalty_per_late_hour=s["sla"],
                        priority=s.get("prio", "NORMAL"))
        entered = s.get("entered_h", s.get("departed_h", 0.0))
        sh = m.Shipment(id=f"SHP-{sid}", order_id=order.id, transporter_id=trans, driver_user_id=users[f"driver{i}"].id,
                        vehicle_label=f"MH20 GH {4100 + i}", route_id=route, lot_type="SINGLE",
                        quantity_tonnes=qty, planned_loading_at=_h(s.get("loading_h", entered - 1.0)),
                        planned_arrival_at=_h(s.get("planned_h", 22.0)), state=state,
                        state_entered_at=_h(entered if state != "PLANNED" else 0.0), disposition="ACTIVE",
                        state_version=1, last_progress_km=0.0)
        db.add_all([order, sh])
        db.flush()
        pts, segs = paths.get_path(db, route)
        if "departed_h" in s:
            sh.departed_at = _h(s["departed_h"])
            sh.planned_loading_at = _h(s["departed_h"] - 1.6)
            timeline = truth.transit_timeline(db, config.GLOBAL_SEED, sh, a, [])
            seen_h = s.get("outage_h", 0.0)                  # last time a position was reported
            km = min(truth.position_km(timeline, seen_h - s["departed_h"]), segs[-1].km_end * 0.97)
            sh.last_progress_km, sh.last_telemetry_at = km, _h(seen_h)
            sh.last_lat, sh.last_lon = position_at_km(pts, segs, km)
        if state == "ARRIVED_AT_CUSTOMER_GATE":
            sh.arrived_at, sh.state_entered_at = _h(s["arrived_h"]), _h(s["arrived_h"])
            sh.last_progress_km, sh.last_lat, sh.last_lon = segs[-1].km_end, pts[-1].lat, pts[-1].lon
            sh.last_telemetry_at = sh.arrived_at
            attribute_delay(db, sh)
        if "outage_h" in s:
            db.add(m.Disruption(id=f"DSR-SEED-{sid}", preset="TELEMETRY_OUTAGE", label="Telemetry outage (seeded)",
                                cause=None, kind="TELEMETRY_OUTAGE", shipment_id=sh.id, start_at=_h(s["outage_h"]),
                                dur_min_h=3.0, dur_mode_h=4.0, dur_max_h=5.0, multiplier=1.0, status="ACTIVE"))
        if "buffer_h" in s:                                  # promise = modelled median arrival + buffer
            db.flush()
            res = simulate_arrival(build_inputs(db, sh, order, SIM_START, a, []), a.n_samples,
                                   seed_pred(config.GLOBAL_SEED, sh.id))
            order.promised_at = _h(round(res.p50 + s["buffer_h"], 2))
            sh.planned_arrival_at = _h(round(res.p50 - 0.3, 2))
        add_event(db, sh.id, "ASSIGNED", _h(-3.0 - i * 0.05),
                  f"Order {order.id} assigned to {TRANSPORTERS[trans]['name']}, vehicle {sh.vehicle_label}, "
                  f"driver {users[f'driver{i}'].display_name}", state="PLANNED", source="COORDINATOR")
        add_event(db, sh.id, "MILESTONE", sh.state_entered_at, "Seeded demo state", state=state, source="SYSTEM")
    db.flush()


def _history(db, users) -> None:
    """160 delivered shipments over 8 weeks with deliberate fictional patterns:
    TR-3 is weak on R3; R2 has recurring congestion; CUST-A often orders urgently."""
    rng = np.random.default_rng([config.GLOBAL_SEED, zlib.crc32(b"history")])
    routes = ["R1", "R2", "R3", "R4"]
    base_h = {r: paths.get_path(db, r)[1][-1].km_end / 45.0 + 1.6 for r in routes}
    crews = {t: [u for u in users.values() if u.role == "TRANSPORTER" and u.transporter_id == t
                 and not u.username.startswith("relief_")] for t in TRANSPORTERS}
    generic = ["GATE_CONGESTION", "SLOW_LOADING", "ROUTE_CONGESTION", "LATE_DISPATCH", "FLOODING", "BREAKDOWN"]
    for i in range(1, HISTORY_COUNT + 1):
        route = routes[int(rng.choice(4, p=[0.3, 0.3, 0.2, 0.2]))]
        trans = f"TR-{int(rng.integers(1, 4))}"
        cust = ROUTE_CUSTOMER[route]
        prio = "HIGH" if rng.random() < (0.6 if cust == "CUST-A" else 0.15) else "NORMAL"
        qty = float(rng.choice([18, 20, 22, 24, 26]))
        planned_arrival = SIM_START - timedelta(hours=float(rng.uniform(8.0, 55.5 * 24)))
        planned_arrival = planned_arrival.replace(microsecond=0)
        p_delay, mean_h, weights = 0.22, 1.5, [0.25, 0.2, 0.3, 0.15, 0.05, 0.05]
        if route == "R1":
            weights = [0.2, 0.15, 0.25, 0.1, 0.25, 0.05]
        if route == "R2":
            p_delay, mean_h, weights = 0.45, 2.2, [0.08, 0.06, 0.7, 0.06, 0.05, 0.05]
        if route == "R3" and trans == "TR-3":
            p_delay, mean_h, weights = 0.75, 3.6, [0.05, 0.05, 0.1, 0.35, 0.05, 0.4]
        order = m.Order(id=f"ORD-H{i:03d}", customer_id=cust, product_code=ROUTE_PRODUCT[route], quantity_tonnes=qty,
                        promised_at=planned_arrival + timedelta(hours=2),
                        sla_penalty_per_late_hour=20000.0 if prio == "HIGH" else float(rng.choice([2500, 5000, 8000])),
                        priority=prio)
        parts: list[tuple[str, float]] = []
        if rng.random() < p_delay:
            total = float(np.clip(rng.lognormal(np.log(mean_h) - 0.18, 0.6), 0.2, 9.0))
            total = round(total * 60) / 60.0                 # whole minutes
            c1 = generic[int(rng.choice(6, p=weights))]
            if total > 1.0 and rng.random() < 0.4:
                c2 = generic[int(rng.choice(6, p=weights))]
                if c2 != c1:
                    first = round(total * float(rng.uniform(0.3, 0.7)) * 60) / 60.0
                    parts = [(c1, first), (c2, total - first)]
            if not parts:
                parts = [(c1, total)]
            arrived = planned_arrival + timedelta(hours=total)
        else:
            arrived = planned_arrival - timedelta(minutes=int(rng.integers(0, 48)))
        loading = planned_arrival - timedelta(hours=base_h[route])
        delivered = arrived + timedelta(minutes=int(rng.integers(25, 90)))
        crew = crews[trans]                                  # deterministic, no extra random draw
        sh = m.Shipment(id=f"SHP-H{i:03d}", order_id=order.id, transporter_id=trans, vehicle_label=f"VEH-H{i:03d}",
                        driver_user_id=crew[i % len(crew)].id,
                        route_id=route, lot_type="SINGLE", quantity_tonnes=qty, planned_loading_at=loading,
                        planned_arrival_at=planned_arrival, state="DELIVERED", state_entered_at=delivered,
                        disposition="ACTIVE", state_version=1, departed_at=loading + timedelta(hours=1.6),
                        arrived_at=arrived, delivered_at=delivered, pod_recipient="Receiving desk (fictional)",
                        is_historical=True)
        db.add_all([order, sh])
        db.flush()
        cursor = planned_arrival
        for j, (cause, h) in enumerate(parts):
            end = arrived if j == len(parts) - 1 else cursor + timedelta(hours=h)
            db.add(m.DelayEvent(shipment_id=sh.id, cause=cause, start_at=cursor, end_at=end,
                                hours=(end - cursor).total_seconds() / 3600.0))
            cursor = end
        add_event(db, sh.id, "MILESTONE", arrived, "Arrived at customer gate (historical)",
                  state="ARRIVED_AT_CUSTOMER_GATE", source="SIMULATED")
        add_event(db, sh.id, "POD", delivered, "Proof of delivery (historical)", state="DELIVERED", source="SIMULATED")


GATE_BOOKINGS = [  # shipment, IST hour of the slot, status
    ("SHP-PTH-1116-01", 7, "BOOKED"), ("SHP-AMV-1116-03", 7, "BOOKED"), ("SHP-BHW-1116-03", 7, "BOOKED"),          # 07:00 is full (capacity 3)
    ("SHP-PTH-1116-02", 6, "CHECKED_IN"), ("SHP-SAT-1116-02", 6, "CHECKED_IN"),
    ("SHP-AMV-1116-02", 9, "BOOKED"), ("SHP-PTH-1116-04", 11, "BOOKED"),
    ("SHP-BHW-1116-02", 0, "COMPLETED"), ("SHP-PTH-1116-03", 1, "COMPLETED"), ("SHP-SAT-1116-01", 3, "COMPLETED"),
    ("SHP-BHW-1116-01", 3, "COMPLETED"), ("SHP-AMV-1116-04", 3, "COMPLETED"), ("SHP-AMV-1116-01", 4, "COMPLETED"), ("SHP-AMV-1116-05", 5, "COMPLETED"),
]
SAMPLE_INVOICES = [("ORD-AMV-1116-01", "INV-2026-1003"), ("ORD-PTH-1116-03", "INV-2026-1007"), ("ORD-AMV-1116-04", "INV-2026-1010"),
                   ("ORD-BHW-1116-02", "INV-2026-1011")]


def _gate(db) -> None:
    """Hourly slots around the simulated day, a full slot, a closed slot and bookings for the live shipments."""
    gate_svc.ensure_slots(db, commit=False)
    today = (SIM_START + gate_svc.IST).date()
    slot = lambda hour: db.query(m.GateSlot).filter(m.GateSlot.slot_start == gate_svc.slot_start_utc(today, hour)).one()  # noqa: E731
    slot(13).closed, slot(13).note = True, "Weighbridge calibration"
    for sid, hour, status in GATE_BOOKINGS:
        sh = db.get(m.Shipment, sid)
        b = m.GateBooking(shipment_id=sid, slot_id=slot(hour).id, transporter_id=sh.transporter_id,
                          driver_user_id=sh.driver_user_id, vehicle_label=sh.vehicle_label, status=status,
                          created_sim_at=SIM_START - timedelta(hours=12))
        if status == "CHECKED_IN":
            b.checked_in_at = SIM_START - timedelta(minutes=10)
        if status == "COMPLETED":
            b.checked_in_at = (sh.departed_at or SIM_START) - timedelta(minutes=40)
            b.completed_at = sh.departed_at
        db.add(b)
    db.flush()


def _documents(db, users) -> None:
    """A few fictional invoices (real, valid PDFs in private storage) so the customer can download one at once."""
    doc_svc.purge_storage()
    coordinator = users["coordinator"]
    for order_id, number in SAMPLE_INVOICES:
        o = db.get(m.Order, order_id)
        data = docgen.make_pdf(f"INVOICE {number}", [
            f"Order: {o.id}", f"Customer: {db.get(m.Customer, o.customer_id).name}", f"Product: {o.product_code}",
            f"Quantity: {o.quantity_tonnes:g} tonnes", "Terms: 30 days (fictional)", "Seller: Plant X (fictional)"])
        import hashlib
        db.add(m.Document(kind="INVOICE", order_id=o.id, version=1, is_current=True, status="ISSUED",
                          original_filename=f"{number}.pdf", stored_name=doc_svc._store(data, "pdf"),
                          content_type="application/pdf", size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                          invoice_number=number, uploaded_by=coordinator.id,
                          uploaded_sim_at=SIM_START - timedelta(hours=6)))
    db.flush()


def seed(db) -> None:
    if not config.DEMO_MODE:
        raise RuntimeError("Seeding demo data requires DEMO_MODE=true")
    a = Assumptions()
    db.add(m.SimulationState(id=1, sim_now=SIM_START, speed=1.0, paused=True, clock_version=1,
                             global_seed=config.GLOBAL_SEED, next_seq=1))
    db.add(m.BusinessAssumptions(id=1, values_json=a.model_dump(), assumptions_version=1))
    _network(db)
    users = _users(db)
    for cust, product, tonnes, rate, unload, min_q in INVENTORY:
        db.add(m.CustomerInventory(customer_id=cust, product_code=product, inventory_tonnes=tonnes,
                                   measured_at=SIM_START, consumption_tph=rate, unloading_hours=unload,
                                   min_priority_qty_tonnes=min_q))
    db.flush()
    _active(db, users, a)
    _history(db, users)
    _gate(db)
    _documents(db, users)
    db.flush()
    predictions.recompute(db, trigger="SEED", trigger_label="initial seed")
    db.commit()


def reset() -> None:
    """Drop everything and rebuild the deterministic demo dataset."""
    engine.dispose()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    paths.clear_cache()
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    reset()
    with SessionLocal() as db:
        print("Seeded:", db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False)).count(), "active shipments,",
              db.query(m.Shipment).filter(m.Shipment.is_historical.is_(True)).count(), "historical,",
              db.query(m.Prediction).count(), "predictions,", db.query(m.Alert).count(), "alerts")
