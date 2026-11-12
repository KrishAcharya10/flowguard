"""Create an order and assign it to a transporter, a free driver and a vehicle (coordinator action).

Everything is persisted like any seeded order: order + shipment + events + audit + a first prediction
(and alerts, if the new shipment is already at risk). Nothing here is frontend-only state.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..engine.eta import simulate_arrival
from ..seed.network import PRODUCTS, ROUTE_CODE, ROUTE_CUSTOMER
from ..seeds import seed_pred
from . import predictions as pred_svc
from .core import add_event, audit, get_assumptions, hours, plus_hours, sim_state
from .mapping import build_inputs


def free_drivers(db: Session, transporter_id: str) -> list[m.User]:
    """Active drivers of this company with no unfinished shipment. Relief drivers are reserved for splits."""
    busy = {r[0] for r in db.query(m.Shipment.driver_user_id).filter(
        m.Shipment.is_historical.is_(False), m.Shipment.disposition == "ACTIVE", m.Shipment.state != "DELIVERED",
        m.Shipment.driver_user_id.isnot(None))}
    return [u for u in db.query(m.User).filter(
        m.User.role == "TRANSPORTER", m.User.transporter_id == transporter_id, m.User.is_active.is_(True)
    ).order_by(m.User.id) if u.id not in busy and not u.username.startswith("relief_")]


def create_order(db: Session, user: m.User, *, route_id: str, transporter_id: str, product_code: str,
                 quantity_tonnes: float, priority: str, sla_penalty_per_late_hour: Optional[float],
                 loading_in_h: float, promised_in_h: Optional[float]) -> tuple[m.Order, m.Shipment, m.User]:
    route = db.get(m.Route, route_id)
    if route is None or route.alternative_of_route_id or route_id not in ROUTE_CUSTOMER:
        raise HTTPException(422, "Choose one of the main routes (each ends at one customer's gate)")
    if db.get(m.Transporter, transporter_id) is None:
        raise HTTPException(422, "Unknown transporter")
    if product_code not in PRODUCTS:
        raise HTTPException(422, f"Unknown product. Choose one of: {', '.join(PRODUCTS)}")
    drivers = free_drivers(db, transporter_id)
    if not drivers:
        raise HTTPException(409, "No free driver at this transporter. Choose another transporter, or wait until "
                                 "a delivery is completed.")
    driver = drivers[0]
    st = sim_state(db)
    now = st.sim_now
    a, _ = get_assumptions(db)
    n = st.next_seq
    st.next_seq = n + 1
    # Meaningful reference: where it goes (route code), the IST date, and the next free number for that day.
    base = f"{ROUTE_CODE[route_id]}-{plus_hours(now, 5.5):%m%d}"
    k = 1
    while db.get(m.Order, f"ORD-{base}-{k:02d}") is not None:
        k += 1
    code = f"{base}-{k:02d}"
    sla = sla_penalty_per_late_hour if sla_penalty_per_late_hour is not None else (20000.0 if priority == "HIGH" else 5000.0)
    order = m.Order(id=f"ORD-{code}", customer_id=ROUTE_CUSTOMER[route_id], product_code=product_code,
                    quantity_tonnes=quantity_tonnes, promised_at=plus_hours(now, 48), sla_penalty_per_late_hour=sla,
                    priority=priority)
    sh = m.Shipment(id=f"SHP-{code}", order_id=order.id, transporter_id=transporter_id, driver_user_id=driver.id,
                    vehicle_label=f"MH20 GH {4200 + n}", route_id=route_id, lot_type="SINGLE",
                    quantity_tonnes=quantity_tonnes, planned_loading_at=plus_hours(now, loading_in_h),
                    planned_arrival_at=plus_hours(now, 48), state="PLANNED", state_entered_at=now,
                    disposition="ACTIVE", state_version=1, last_progress_km=0.0)
    db.add_all([order, sh])
    db.flush()
    # The promise is the undisturbed median arrival plus a 2 h buffer (same rule as the seeded orders),
    # unless the coordinator typed one.
    res = simulate_arrival(build_inputs(db, sh, order, now, a, []), a.n_samples, seed_pred(st.global_seed, sh.id))
    order.promised_at = plus_hours(now, promised_in_h) if promised_in_h is not None else plus_hours(now, res.p50 + 2.0)
    sh.planned_arrival_at = plus_hours(now, min(res.p50 - 0.3, hours(order.promised_at - now)))
    customer = db.get(m.Customer, order.customer_id)
    transporter = db.get(m.Transporter, transporter_id)
    add_event(db, sh.id, "ASSIGNED", now,
              f"Order {order.id} for {customer.name.replace(' (fictional)', '')} assigned to {transporter.name.replace(' (fictional)', '')}, "
              f"vehicle {sh.vehicle_label}, driver {driver.display_name}", state="PLANNED", user=user,
              source="COORDINATOR")
    add_event(db, sh.id, "MILESTONE", now, "Order created and planned", state="PLANNED", user=user, source="COORDINATOR")
    audit(db, user, "ORDER_CREATED", "order", order.id,
          after={"shipment_id": sh.id, "route_id": route_id, "transporter_id": transporter_id, "driver": driver.username,
                 "quantity_tonnes": quantity_tonnes, "priority": priority})
    db.flush()
    pred_svc.recompute(db, trigger="ORDER_CREATED", trigger_event_id=sh.id, trigger_label=f"new order {order.id}",
                       order_ids=[order.id])
    return order, sh, driver
