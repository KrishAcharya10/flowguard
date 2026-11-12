"""Auth, customer and transporter endpoints."""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..db import get_db
from ..security import (ANY, CUST, TRANS, make_token, own_shipment, throttle_check, throttle_fail, verify_password)
from .. import config
from ..services import predictions as pred_svc
from ..services import reports as report_svc
from ..services import views
from ..services.core import audit, get_assumptions, sim_now
from ..services.shipments import NEXT, advance_state, record_delivery

router = APIRouter(prefix="/api")


def _user_out(db: Session, u: m.User) -> s.UserOut:
    org = None
    if u.customer_id:
        org = db.get(m.Customer, u.customer_id).name
    elif u.transporter_id:
        org = db.get(m.Transporter, u.transporter_id).name
    elif u.role == "COORDINATOR":
        org = "Plant X logistics (fictional)"
    return s.UserOut(id=u.id, username=u.username, role=u.role, display_name=u.display_name,
                     customer_id=u.customer_id, transporter_id=u.transporter_id, organisation=org)


# ---------- AUTH ----------
@router.post("/auth/login", response_model=s.TokenOut, tags=["auth"])
def login(body: s.LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    throttle_check(body.username, ip)
    user = db.query(m.User).filter(m.User.username == body.username).first()
    if user is None or not user.is_active or not verify_password(user.password_hash, body.password):
        throttle_fail(body.username, ip)
        raise HTTPException(401, "Wrong username or password")
    return s.TokenOut(access_token=make_token(user), expires_in_minutes=config.JWT_EXPIRE_MINUTES,
                      user=_user_out(db, user))


@router.get("/auth/me", response_model=s.UserOut, tags=["auth"])
def me(user: m.User = Depends(ANY), db: Session = Depends(get_db)):
    return _user_out(db, user)


# ---------- CUSTOMER (allow-list schemas only) ----------
@router.get("/customer/me/orders", response_model=list[s.CustomerOrderOut], tags=["customer"])
def my_orders(user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    now = sim_now(db)
    ids = [r[0] for r in db.query(m.Shipment.order_id).join(m.Order, m.Order.id == m.Shipment.order_id)
           .filter(m.Order.customer_id == user.customer_id, m.Shipment.is_historical.is_(False)).distinct()]
    orders = db.query(m.Order).filter(m.Order.id.in_(ids)).order_by(m.Order.promised_at, m.Order.id).all()
    return [views.customer_order(db, o, now, a) for o in orders]


@router.get("/customer/me/shipments", response_model=list[s.CustomerShipmentOut], tags=["customer"])
def my_shipments(user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    now = sim_now(db)
    rows = (db.query(m.Shipment).join(m.Order, m.Order.id == m.Shipment.order_id)
            .filter(m.Order.customer_id == user.customer_id, m.Shipment.is_historical.is_(False),
                    m.Shipment.disposition == "ACTIVE").order_by(m.Shipment.id).all())
    return [views.customer_shipment(db, sh, now, a) for sh in rows]


@router.get("/customer/me/shipments/{shipment_id}", response_model=s.CustomerShipmentOut, tags=["customer"])
def my_shipment(shipment_id: str, user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    sh = own_shipment(db, user, shipment_id)
    a, _ = get_assumptions(db)
    return views.customer_shipment(db, sh, sim_now(db), a)


@router.get("/customer/me/alerts", response_model=list[s.CustomerAlertOut], tags=["customer"])
def my_alerts(user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    rows = (db.query(m.Alert).filter(m.Alert.audience_role == "CUSTOMER", m.Alert.customer_id == user.customer_id)
            .order_by(m.Alert.id.desc()).limit(50).all())
    return [views.customer_alert(al) for al in rows]


@router.get("/customer/me/history", response_model=list[s.CustomerHistoryItem], tags=["customer"])
def my_history(user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    """The customer's completed deliveries (own orders only)."""
    a, _ = get_assumptions(db)
    return views.customer_history(db, user.customer_id, a)


@router.post("/customer/me/alerts/{alert_id}/acknowledge", response_model=s.CustomerAlertOut, tags=["customer"])
def ack_my_alert(alert_id: int, user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    al = db.get(m.Alert, alert_id)
    if al is None or al.audience_role != "CUSTOMER" or al.customer_id != user.customer_id:
        raise HTTPException(404, "Alert not found")
    if not al.acknowledged:
        al.acknowledged, al.read, al.acknowledged_by = True, True, user.id
        audit(db, user, "ALERT_ACKNOWLEDGED", "alert", al.id)
        db.commit()
    return views.customer_alert(al)


# ---------- TRANSPORTER ----------
def _driver_rows(db: Session, user: m.User):
    return (db.query(m.Shipment).filter(m.Shipment.driver_user_id == user.id, m.Shipment.is_historical.is_(False),
                                        m.Shipment.disposition == "ACTIVE").order_by(m.Shipment.id).all())


@router.get("/transporter/me/shipments", response_model=list[s.DriverShipmentOut], tags=["transporter"])
def driver_shipments(user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    return [views.driver_shipment(db, sh) for sh in _driver_rows(db, user)]


@router.post("/transporter/shipments/{shipment_id}/milestones", response_model=s.DriverShipmentOut, tags=["transporter"])
def post_milestone(shipment_id: str, body: s.MilestoneIn, user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """Assigned shipment only, next state only, not later than sim_now, idempotent."""
    sh = own_shipment(db, user, shipment_id)
    if sh.disposition != "ACTIVE":
        raise HTTPException(409, "This shipment was split; update the child lots instead")
    if sh.state == body.to_state:
        return views.driver_shipment(db, sh)                # idempotent repeat
    if NEXT.get(sh.state) != body.to_state:
        raise HTTPException(409, f"Only the next milestone is allowed: {NEXT.get(sh.state)}")
    now = sim_now(db)
    at = now
    if body.occurred_at is not None:                        # API boundary: normalise to naive UTC
        at = body.occurred_at
        if at.tzinfo is not None:
            at = at.astimezone(timezone.utc).replace(tzinfo=None)
    if at > now:
        raise HTTPException(422, "A milestone cannot be later than the current simulation time")
    if at < sh.state_entered_at:
        raise HTTPException(422, "A milestone cannot be earlier than the previous milestone")
    before = {"state": sh.state, "state_version": sh.state_version}
    advance_state(db, sh, body.to_state, at, "DRIVER", user)
    audit(db, user, "MILESTONE_POSTED", "shipment", sh.id, before=before,
          after={"state": sh.state, "state_version": sh.state_version})
    db.flush()
    pred_svc.recompute(db, trigger="MILESTONE", trigger_label=f"milestone {body.to_state} on {sh.id}",
                       trigger_event_id=f"{sh.id}:{body.to_state}")
    db.commit()
    return views.driver_shipment(db, sh)


@router.post("/transporter/shipments/{shipment_id}/pod", response_model=s.DriverShipmentOut, tags=["transporter"])
def post_pod(shipment_id: str, body: s.PodIn, user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """Complete the delivery without a document (status + recipient name). On-time is decided at gate arrival."""
    sh = own_shipment(db, user, shipment_id)
    if sh.state == "DELIVERED":
        return views.driver_shipment(db, sh)                # idempotent repeat
    record_delivery(db, user, sh, body.recipient_name)
    db.commit()
    return views.driver_shipment(db, sh)


@router.get("/transporter/me/history", response_model=list[s.DriverHistoryItem], tags=["transporter"])
def driver_history(user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """The driver's own completed runs."""
    a, _ = get_assumptions(db)
    return views.driver_history(db, user.id, a)


@router.post("/transporter/shipments/{shipment_id}/report", response_model=s.ReportOut, tags=["transporter"])
def post_report(shipment_id: str, body: s.ReportIn, user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """Report a breakdown or a road hazard. It becomes a real disruption: predictions recalculate, alerts fire."""
    sh = own_shipment(db, user, shipment_id)
    d = report_svc.report(db, user, sh, body.kind, body.note)
    db.commit()
    return s.ReportOut(disruption_id=d.id, shipment=views.driver_shipment(db, sh),
                       message="Reported. The control tower has been alerted and the arrival time is being recalculated.")
