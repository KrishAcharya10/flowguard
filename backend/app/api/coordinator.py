"""Coordinator endpoints: control tower, shipments, simulation, War Room,
alerts, analytics, assumptions, audit, admin. All require the COORDINATOR role."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from .. import schemas as s
from ..assumptions import Assumptions
from ..db import get_db
from ..security import ANY, COORD
from ..services import (activity, analytics, disruptions as dis_svc, orders as order_svc, predictions as pred_svc,
                        runtime, settings, views, warroom as wr)
from ..services.core import audit, get_assumptions, hours, preload_latest_predictions, sim_now, sim_state
from ..services.mapping import data_confidence
from ..services.paths import get_path
from ..services.shipments import LABEL
from ..seed.network import PRODUCTS, ROUTE_CUSTOMER
from ..simulator import clock

router = APIRouter(prefix="/api")


def _shipment(db: Session, shipment_id: str) -> m.Shipment:
    sh = db.get(m.Shipment, shipment_id)
    if sh is None:
        raise HTTPException(404, "Shipment not found")
    return sh


def _live(db: Session):
    return db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False))


# ---------- CONTROL TOWER ----------
@router.get("/control-tower/overview", response_model=s.ControlTowerOut, tags=["control-tower"])
def overview(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    st = sim_state(db)
    preload_latest_predictions(db)
    ships = [views.shipment_out(db, sh, st.sim_now, a) for sh in _live(db).order_by(m.Shipment.id)]
    open_alerts = (db.query(m.Alert).filter(m.Alert.audience_role == "COORDINATOR", m.Alert.acknowledged.is_(False)).count())
    return s.ControlTowerOut(clock=views.clock_out(st), kpis=analytics.overview(db, st.sim_now, a),
                             shipments=ships, open_alerts=open_alerts)


@router.get("/control-tower/map-data", response_model=s.MapDataOut, tags=["control-tower"])
def map_data(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    now = sim_now(db)
    preload_latest_predictions(db)
    routes = []
    for r in db.query(m.Route).order_by(m.Route.id):
        wps = db.query(m.RouteWaypoint).filter(m.RouteWaypoint.route_id == r.id).order_by(m.RouteWaypoint.sequence)
        routes.append(s.MapRoute(id=r.id, name=r.name, alternative_of=r.alternative_of_route_id,
                                 points=[s.MapPoint(id=w.id, name=w.name, lat=w.lat, lon=w.lon,
                                                    is_decision_node=w.is_decision_node) for w in wps]))
    vehicles = []
    for sh in _live(db).filter(m.Shipment.disposition == "ACTIVE", m.Shipment.state != "DELIVERED").order_by(m.Shipment.id):
        pts, _ = get_path(db, sh.route_id, sh.active_alternative_route_id)
        lat, lon = (sh.last_lat, sh.last_lon) if sh.last_lat is not None else (pts[0].lat, pts[0].lon)
        conf, _, age = data_confidence(sh, now, a)
        f = views.shipment_fields(db, sh, now, a)
        vehicles.append(s.MapVehicle(shipment_id=sh.id, lat=lat, lon=lon, reported_at=sh.last_telemetry_at,
                                     age_min=age, data_confidence=conf, state=sh.state,
                                     risk_category=f["prediction"].risk_category if f["prediction"] else None,
                                     bucket=f["bucket"], route_id=sh.route_id,
                                     on_alternative=sh.active_alternative_route_id is not None))
    dis = []
    for d in db.query(m.Disruption).filter(m.Disruption.status == "ACTIVE", m.Disruption.segment_waypoint_id.isnot(None)):
        w = db.get(m.RouteWaypoint, d.segment_waypoint_id)
        nxt = (db.query(m.RouteWaypoint).filter(m.RouteWaypoint.route_id == w.route_id,
                                                m.RouteWaypoint.sequence == w.sequence + 1).first())
        if nxt:
            dis.append(s.MapDisruption(id=d.id, label=d.label, kind=d.kind, lat1=w.lat, lon1=w.lon, lat2=nxt.lat, lon2=nxt.lon))
    return s.MapDataOut(caption=views.MAP_CAPTION, routes=routes, vehicles=vehicles, disruptions=dis)


# ---------- ORDERS / SHIPMENTS ----------
@router.post("/orders", response_model=s.OrderCreatedOut, status_code=201, tags=["orders"])
def create_order(body: s.OrderCreateIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Create an order and assign it to a transporter, a free driver and a vehicle."""
    order, sh, driver = order_svc.create_order(
        db, user, route_id=body.route_id, transporter_id=body.transporter_id, product_code=body.product_code,
        quantity_tonnes=body.quantity_tonnes, priority=body.priority,
        sla_penalty_per_late_hour=body.sla_penalty_per_late_hour, loading_in_h=body.loading_in_h,
        promised_in_h=body.promised_in_h)
    db.commit()
    cust = db.get(m.Customer, order.customer_id)
    tr = db.get(m.Transporter, sh.transporter_id)
    return s.OrderCreatedOut(
        order_id=order.id, shipment_id=sh.id, customer_name=cust.name, transporter_name=tr.name,
        driver_name=driver.display_name, driver_username=driver.username, vehicle_label=sh.vehicle_label,
        promised_at=order.promised_at, planned_loading_at=sh.planned_loading_at,
        message=f"Order {order.id} created and assigned to {driver.display_name} ({tr.name}).")


@router.get("/activity", response_model=list[s.ActivityOut], tags=["activity"])
def activity_feed(limit: int = Query(60, ge=1, le=200), user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Operational feed. Every line is a stored record (events, alerts, predictions, audit)."""
    return activity.build(db, limit)


@router.get("/sync/state", response_model=s.SyncOut, tags=["activity"])
def sync_state(user: m.User = Depends(ANY), db: Session = Depends(get_db)):
    """Cheap change fingerprint every open screen polls; data is reloaded only when it changes."""
    return activity.sync_stamp(db)


@router.get("/orders/{order_id}", response_model=s.OrderOut, tags=["orders"])
def get_order(order_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    o = db.get(m.Order, order_id)
    if o is None:
        raise HTTPException(404, "Order not found")
    ids = [x.id for x in db.query(m.Shipment).filter(m.Shipment.order_id == o.id).order_by(m.Shipment.id)]
    return s.OrderOut(id=o.id, customer_id=o.customer_id, customer_name=db.get(m.Customer, o.customer_id).name,
                      product_code=o.product_code, quantity_tonnes=o.quantity_tonnes, promised_at=o.promised_at,
                      sla_penalty_per_late_hour=o.sla_penalty_per_late_hour, priority=o.priority,
                      revised_eta_communicated=o.revised_eta_communicated,
                      revised_eta_communicated_at=o.revised_eta_communicated_at, shipment_ids=ids)


@router.get("/shipments", response_model=list[s.ShipmentOut], tags=["shipments"])
def list_shipments(state: Optional[s.State] = None, route_id: Optional[str] = Query(None, max_length=20),
                   transporter_id: Optional[str] = Query(None, max_length=20),
                   customer_id: Optional[str] = Query(None, max_length=20),
                   user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    q = _live(db)
    if state:
        q = q.filter(m.Shipment.state == state)
    if route_id:
        q = q.filter(m.Shipment.route_id == route_id)
    if transporter_id:
        q = q.filter(m.Shipment.transporter_id == transporter_id)
    if customer_id:
        q = q.join(m.Order, m.Order.id == m.Shipment.order_id).filter(m.Order.customer_id == customer_id)
    now = sim_now(db)
    preload_latest_predictions(db)
    return [views.shipment_out(db, sh, now, a) for sh in q.order_by(m.Shipment.id)]


@router.get("/shipments/{shipment_id}", response_model=s.ShipmentDetailOut, tags=["shipments"])
def get_shipment(shipment_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    return views.shipment_detail(db, _shipment(db, shipment_id), sim_now(db), a)


@router.get("/shipments/{shipment_id}/events", response_model=list[s.EventOut], tags=["shipments"])
def shipment_events(shipment_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    _shipment(db, shipment_id)
    return (db.query(m.ShipmentEvent).filter(m.ShipmentEvent.shipment_id == shipment_id)
            .order_by(m.ShipmentEvent.occurred_at, m.ShipmentEvent.id).all())


@router.get("/shipments/{shipment_id}/prediction", response_model=list[s.PredictionOut], tags=["shipments"])
def shipment_prediction(shipment_id: str, history: bool = False, user: m.User = Depends(COORD),
                        db: Session = Depends(get_db)):
    """Reads stored predictions. Never runs Monte Carlo."""
    _shipment(db, shipment_id)
    q = db.query(m.Prediction).filter(m.Prediction.shipment_id == shipment_id).order_by(m.Prediction.id.desc())
    rows = q.limit(40).all() if history else q.limit(1).all()
    return [views.prediction_out(p) for p in rows]


@router.post("/shipments/{shipment_id}/recalculate", response_model=list[s.PredictionOut], tags=["shipments"])
def recalculate(shipment_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    sh = _shipment(db, shipment_id)
    pred_svc.recompute(db, trigger="MANUAL_RECALCULATE", trigger_label="manual recalculation", order_ids=[sh.order_id])
    audit(db, user, "PREDICTION_RECALCULATED", "shipment", sh.id)
    db.commit()
    p = pred_svc.latest(db, sh.id)
    return [views.prediction_out(p)] if p else []


# ---------- SIMULATION ----------
@router.get("/simulation/clock", response_model=s.ClockOut, tags=["simulation"])
def get_clock(user: m.User = Depends(ANY), db: Session = Depends(get_db)):
    return views.clock_out(sim_state(db))


@router.post("/simulation/clock/advance", response_model=s.AdvanceOut, tags=["simulation"])
def advance_clock(body: s.AdvanceIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    out = clock.advance(db, body.minutes, user)
    db.commit()
    return s.AdvanceOut(clock=views.clock_out(sim_state(db)), predictions_recomputed=out["predictions_recomputed"])


@router.post("/simulation/clock/control", response_model=s.ControlOut, tags=["simulation"])
def control_clock(body: s.ClockControlIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Start / pause the simulation and choose its speed (simulated minutes per real second).
    Paused by default. While running, a background task advances the same clock as the manual buttons."""
    st = sim_state(db)
    before = {"paused": st.paused, "speed": st.speed, "pause_on_alert": runtime.RUNNER["pause_on_alert"]}
    if body.speed is not None:
        if body.speed not in runtime.SPEEDS:
            raise HTTPException(422, f"Speed must be one of {list(runtime.SPEEDS)} simulated minutes per second")
        st.speed = body.speed
    if body.paused is not None:
        st.paused = body.paused
    if body.pause_on_alert is not None:
        runtime.RUNNER["pause_on_alert"] = body.pause_on_alert
    after = {"paused": st.paused, "speed": st.speed, "pause_on_alert": runtime.RUNNER["pause_on_alert"]}
    if after != before:
        audit(db, user, "SIMULATION_CONTROL", "simulation_state", 1, before=before, after=after)
    db.commit()
    return s.ControlOut(clock=views.clock_out(st), runner_error=runtime.RUNNER["last_error"])


@router.get("/simulations/disruptions", response_model=list[s.DisruptionOut], tags=["simulation"])
def list_disruptions(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return db.query(m.Disruption).order_by(m.Disruption.status, m.Disruption.start_at.desc(), m.Disruption.id).all()


@router.post("/simulations/disruptions", response_model=s.DisruptionOut, status_code=201, tags=["simulation"])
def create_disruption(body: s.DisruptionIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    dur = None
    given = [body.dur_min_h, body.dur_mode_h, body.dur_max_h]
    if any(x is not None for x in given):
        if any(x is None for x in given):
            raise HTTPException(422, "Give all three of dur_min_h, dur_mode_h, dur_max_h or none")
        dur = tuple(given)
    d = dis_svc.create(db, user, body.preset, body.shipment_id, body.start_offset_h, dur, body.multiplier)
    db.flush()
    pred_svc.recompute(db, trigger="DISRUPTION_START", trigger_event_id=d.id,
                       trigger_label=f"{(d.cause or d.kind).replace('_', ' ').lower()} event {d.id}")
    db.commit()
    return d


@router.post("/simulations/disruptions/{disruption_id}/end", response_model=s.DisruptionOut, tags=["simulation"])
def end_disruption(disruption_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    d = db.get(m.Disruption, disruption_id)
    if d is None:
        raise HTTPException(404, "Disruption not found")
    if d.status == "ACTIVE":
        dis_svc.end(db, d, sim_now(db), user, "COORDINATOR")
        db.flush()
        pred_svc.recompute(db, trigger="DISRUPTION_END", trigger_event_id=d.id, trigger_label=f"end of event {d.id}")
        db.commit()
    return d


# ---------- WAR ROOM ----------
@router.post("/shipments/{shipment_id}/scenarios", response_model=s.CaseOut, status_code=201, tags=["war-room"])
def create_scenarios(shipment_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    iv = wr.create_case(db, _shipment(db, shipment_id), user)
    db.commit()
    return views.case_out(db, iv)


@router.get("/shipments/{shipment_id}/scenarios", response_model=Optional[s.CaseOut], tags=["war-room"])
def get_scenarios(shipment_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    _shipment(db, shipment_id)
    iv = wr.latest_case(db, shipment_id)
    return views.case_out(db, iv) if iv else None


@router.get("/interventions", response_model=list[s.CaseOut], tags=["war-room"])
def list_interventions(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    rows = db.query(m.Intervention).order_by(m.Intervention.id.desc()).limit(50).all()
    return [views.case_out(db, iv) for iv in rows]


def _case(db: Session, intervention_id: int) -> m.Intervention:
    iv = db.get(m.Intervention, intervention_id)
    if iv is None:
        raise HTTPException(404, "Intervention not found")
    return iv


@router.post("/interventions/{intervention_id}/approve", response_model=s.CaseOut, tags=["war-room"])
def approve(intervention_id: int, body: s.ApproveIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """One transaction: shipment change, event, new prediction, alerts, audit. 409 if any version is stale."""
    iv = _case(db, intervention_id)
    try:
        wr.approve(db, iv, body.selected_scenario_id, body.override_reason, user)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return views.case_out(db, db.get(m.Intervention, intervention_id))


@router.post("/interventions/{intervention_id}/reject", response_model=s.CaseOut, tags=["war-room"])
def reject(intervention_id: int, body: s.RejectIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    iv = wr.reject(db, _case(db, intervention_id), body.reason, user)
    db.commit()
    return views.case_out(db, iv)


# ---------- ALERTS / AUDIT ----------
@router.get("/alerts", response_model=list[s.AlertOut], tags=["alerts"])
def list_alerts(only_open: bool = False, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    q = db.query(m.Alert).filter(m.Alert.audience_role == "COORDINATOR")
    if only_open:
        q = q.filter(m.Alert.acknowledged.is_(False))
    return [_alert(al) for al in q.order_by(m.Alert.id.desc()).limit(100)]


def _alert(al: m.Alert) -> s.AlertOut:
    return s.AlertOut(id=al.id, audience_role=al.audience_role, shipment_id=al.shipment_id, order_id=al.order_id,
                      kind=al.kind, severity=al.severity, title=al.title, message=al.message,
                      suggested_action=al.suggested_action, data=al.data_json or {}, acknowledged=al.acknowledged,
                      escalation_level=al.escalation_level, created_sim_at=al.created_sim_at)


@router.post("/alerts/{alert_id}/acknowledge", response_model=s.AlertOut, tags=["alerts"])
def acknowledge(alert_id: int, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    al = db.get(m.Alert, alert_id)
    if al is None or al.audience_role != "COORDINATOR":
        raise HTTPException(404, "Alert not found")
    if not al.acknowledged:
        al.acknowledged, al.read, al.acknowledged_by = True, True, user.id
        audit(db, user, "ALERT_ACKNOWLEDGED", "alert", al.id)
        db.commit()
    return _alert(al)


@router.get("/audit-events", response_model=list[s.AuditOut], tags=["audit"])
def audit_events(limit: int = Query(100, ge=1, le=500), user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    names = {u.id: u.display_name for u in db.query(m.User)}
    rows = db.query(m.AuditEvent).order_by(m.AuditEvent.id.desc()).limit(limit).all()
    return [s.AuditOut(id=r.id, actor=names.get(r.actor_user_id, "System"), actor_role=r.actor_role, action=r.action,
                       entity_type=r.entity_type, entity_id=r.entity_id, before=r.before_json, after=r.after_json,
                       sim_time=r.sim_time, wall_time=r.wall_time) for r in rows]


# ---------- ANALYTICS ----------
@router.get("/analytics/overview", response_model=s.AnalyticsOverviewOut, tags=["analytics"])
def analytics_overview(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    return analytics.overview(db, sim_now(db), a)


@router.get("/analytics/delay-causes", response_model=s.DelayCausesOut, tags=["analytics"])
def analytics_causes(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    return analytics.delay_causes(db, sim_now(db), a)


@router.get("/analytics/routes", response_model=list[s.DimensionRow], tags=["analytics"])
def analytics_routes(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    return analytics.by_dimension(db, sim_now(db), a, "route_id")


@router.get("/analytics/transporters", response_model=list[s.DimensionRow], tags=["analytics"])
def analytics_transporters(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """By transporter COMPANY, never by individual driver."""
    a, _ = get_assumptions(db)
    return analytics.by_dimension(db, sim_now(db), a, "transporter_id")


@router.get("/analytics/business-impact", response_model=s.BusinessImpactOut, tags=["analytics"])
def analytics_impact(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, _ = get_assumptions(db)
    return analytics.business_impact(db, a)


# ---------- ASSUMPTIONS ----------
@router.get("/assumptions", response_model=s.AssumptionsOut, tags=["assumptions"])
def get_assump(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    a, v = get_assumptions(db)
    return s.AssumptionsOut(values=a, assumptions_version=v)


@router.put("/assumptions", response_model=s.AssumptionsPutOut, tags=["assumptions"])
def put_assump(body: Assumptions, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Bumps assumptions_version, recalculates active predictions, supersedes open cases, writes an audit event."""
    version, n, superseded = settings.update_assumptions(db, body, user)
    db.commit()
    return s.AssumptionsPutOut(values=body, assumptions_version=version,
                               predictions_recomputed=n, cases_superseded=superseded)


# ---------- REFERENCE DATA / ADMIN / HEALTH ----------
@router.get("/reference-data", response_model=s.ReferenceDataOut, tags=["reference"])
def reference_data(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    presets = [s.PresetOut(code=k, label=p["label"], cause=p["cause"], kind=p["kind"],
                           needs_shipment="requires_state" in p, requires_state=list(p.get("requires_state", ())),
                           duration=list(p["duration"]), multiplier=p.get("multiplier"))
               for k, p in dis_svc.ALL_PRESETS.items()]
    return s.ReferenceDataOut(
        customers=[s.RefItem(id=c.id, name=c.name) for c in db.query(m.Customer).order_by(m.Customer.id)],
        transporters=[s.RefItem(id=t.id, name=t.name) for t in db.query(m.Transporter).order_by(m.Transporter.id)],
        routes=[s.RefItem(id=r.id, name=r.name) for r in db.query(m.Route).order_by(m.Route.id)],
        states=[s.RefItem(id=k, name=v) for k, v in LABEL.items()], risk_categories=["LOW", "MEDIUM", "HIGH"],
        presets=presets, demo_mode=config.DEMO_MODE, products=PRODUCTS,
        order_routes=[s.OrderRoute(route_id=rid, route_name=db.get(m.Route, rid).name,
                                   customer_name=db.get(m.Customer, cid).name,
                                   destination_name=db.get(m.Route, rid).destination_name)
                      for rid, cid in ROUTE_CUSTOMER.items()],
        free_drivers={t.id: len(order_svc.free_drivers(db, t.id)) for t in db.query(m.Transporter)},
        drivers=[s.DriverRef(id=u.id, name=u.display_name, username=u.username, transporter_id=u.transporter_id)
                 for u in db.query(m.User).filter(m.User.role == "TRANSPORTER", m.User.is_active.is_(True)).order_by(m.User.id)])


@router.post("/admin/reset", response_model=s.ResetOut, tags=["admin"])
def admin_reset(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Rebuild the deterministic demo dataset. Only when DEMO_MODE=true."""
    if not config.DEMO_MODE:
        raise HTTPException(403, "Reset is only available when DEMO_MODE=true")
    from ..db import SessionLocal
    from ..seed.reset import reset
    db.close()
    reset()
    with SessionLocal() as fresh:
        return s.ResetOut(status="reset",
                          active_shipments=fresh.query(m.Shipment).filter(m.Shipment.is_historical.is_(False)).count(),
                          historical_shipments=fresh.query(m.Shipment).filter(m.Shipment.is_historical.is_(True)).count())




# ---------- DEMO GUIDE ----------
@router.get("/demo/use-cases", response_model=s.DemoGuideOut, tags=["demo"])
def demo_use_cases(user: m.User = Depends(COORD)):
    from ..services import demo
    return s.DemoGuideOut(demo_mode=config.DEMO_MODE,
                          password_hint="Every demo account uses the fictional password PlantX-demo-2026",
                          use_cases=demo.USE_CASES)


@router.post("/demo/use-cases/{code}/setup", response_model=s.DemoSetupOut, tags=["demo"])
def demo_setup(code: str, body: s.DemoSetupIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Reset the demo data and (mode=jump) perform the setup steps with the real services. DEMO_MODE only."""
    from ..services import demo
    username = user.username
    db.close()
    return demo.setup(code, body.mode, username)
