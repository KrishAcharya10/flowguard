"""Small shared helpers: injected time, assumptions, audit, events."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions

ACTIVE_STATES = ("PLANNED", "LOADING", "AT_PLANT_GATE", "IN_TRANSIT")


def hours(td: timedelta) -> float:
    return td.total_seconds() / 3600.0


def plus_hours(t: datetime, h: float) -> datetime:
    return t + timedelta(seconds=round(h * 3600))


def iso(t: Optional[datetime]) -> Optional[str]:
    return None if t is None else t.replace(microsecond=0).isoformat() + "Z"


def sim_state(db: Session) -> m.SimulationState:
    return db.get(m.SimulationState, 1)


def sim_now(db: Session) -> datetime:
    """The only source of 'now' for business logic."""
    return sim_state(db).sim_now


def get_assumptions(db: Session) -> tuple[Assumptions, int]:
    row = db.get(m.BusinessAssumptions, 1)
    return Assumptions(**row.values_json), row.assumptions_version


def next_id(db: Session, prefix: str) -> str:
    st = sim_state(db)
    n = st.next_seq
    st.next_seq = n + 1
    return f"{prefix}-{n:03d}"


def audit(db: Session, user: Optional[m.User], action: str, entity_type: str, entity_id,
          before=None, after=None) -> None:
    db.add(m.AuditEvent(
        actor_user_id=user.id if user else None, actor_role=user.role if user else "SYSTEM",
        action=action, entity_type=entity_type, entity_id=str(entity_id),
        before_json=before, after_json=after, sim_time=sim_now(db)))


def add_event(db: Session, shipment_id: str, type_: str, at: datetime, note: str = "",
              state: Optional[str] = None, user: Optional[m.User] = None, source: str = "SYSTEM") -> m.ShipmentEvent:
    ev = m.ShipmentEvent(shipment_id=shipment_id, type=type_, state=state, occurred_at=at, note=note,
                         actor_user_id=user.id if user else None, source=source)
    db.add(ev)
    return ev


def leaf_shipments(db: Session, order_id: str) -> list[m.Shipment]:
    """Non-parent lots of an order (a SPLIT_PARENT is never a delivery lot)."""
    return (db.query(m.Shipment).filter(m.Shipment.order_id == order_id, m.Shipment.disposition == "ACTIVE")
            .order_by(m.Shipment.id).all())


def latest_prediction(db: Session, shipment_id: str) -> Optional[m.Prediction]:
    cache = db.info.get("latest_pred")
    if cache is not None:                      # read-only request that preloaded everything
        return cache.get(shipment_id)
    return (db.query(m.Prediction).filter(m.Prediction.shipment_id == shipment_id)
            .order_by(m.Prediction.id.desc()).first())


def preload_latest_predictions(db: Session) -> None:
    """For read-only list endpoints: fetch every shipment's latest prediction in ONE query.
    Never call this in a request that writes predictions."""
    from sqlalchemy import func
    newest = db.query(func.max(m.Prediction.id)).group_by(m.Prediction.shipment_id).subquery()
    rows = db.query(m.Prediction).filter(m.Prediction.id.in_(db.query(newest))).all()
    db.info["latest_pred"] = {p.shipment_id: p for p in rows}
