"""Operational activity feed: every line comes from a real stored record.

Sources (each row appears once, under a stable id so the UI can de-duplicate):
  ev:<id>  shipment_events   milestones, positions, disruptions, assignments, driver reports, decisions
  al:<id>  alerts            coordinator alerts and customer notifications
  pr:<id>  predictions       risk-category changes and ETA recalculations
  au:<id>  audit_events      rejections, overrides, assumption changes, new orders
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from .. import models as m
from .core import hours

STATE_TEXT = {
    "LOADING": "Driver started loading {s}",
    "AT_PLANT_GATE": "{s} loaded and waiting at the plant gate",
    "IN_TRANSIT": "{s} departed Plant X",
    "ARRIVED_AT_CUSTOMER_GATE": "{s} arrived at the customer gate",
    "DELIVERED": "Proof of delivery completed for {s}",
}
AUDIT_TEXT = {
    "INTERVENTION_REJECTED": ("Intervention rejected", "warn"),
    "CONSTRAINT OVERRIDE": ("Constraint override approved", "alert"),
    "ASSUMPTIONS_UPDATED": ("Assumptions updated and predictions recalculated", "info"),
    "SIMULATION_AUTO_PAUSED": ("Simulation paused automatically", "warn"),
}
RISK_ORDER = ("LOW", "MEDIUM", "HIGH")
RANK = {"ev": 0, "pr": 1, "al": 2, "au": 3}


def _item(key, at, kind, severity, title, detail="", shipment_id=None, source="SYSTEM"):
    return {"id": key, "at": at, "kind": kind, "severity": severity, "title": title, "detail": detail,
            "shipment_id": shipment_id, "source": source}


def build(db: Session, limit: int = 60) -> list[dict]:
    items: list[dict] = []

    # --- shipment events (disruption starts are merged: one disruption touches many shipments) ---
    disruptions: dict[tuple, list] = defaultdict(list)
    live_events = (db.query(m.ShipmentEvent).join(m.Shipment, m.Shipment.id == m.ShipmentEvent.shipment_id)
                   .filter(m.Shipment.is_historical.is_(False)))       # history is for analytics, not operations
    for ev in live_events.order_by(m.ShipmentEvent.id.desc()).limit(300):
        key = f"ev:{ev.id}"
        s = ev.shipment_id
        if ev.type == "MILESTONE":
            if ev.state in STATE_TEXT:
                items.append(_item(key, ev.occurred_at, "MILESTONE", "info", STATE_TEXT[ev.state].format(s=s),
                                   "", s, ev.source))
        elif ev.type == "POSITION":
            items.append(_item(key, ev.occurred_at, "POSITION", "info", f"Vehicle position updated: {s}",
                               ev.note.replace("Latest position reported: ", ""), s, "SIMULATED"))
        elif ev.type == "GATE":
            missed = "missed" in ev.note
            items.append(_item(key, ev.occurred_at, "GATE", "warn" if missed else "info", ev.note, "", s, ev.source))
        elif ev.type == "ASSIGNED":
            items.append(_item(key, ev.occurred_at, "ASSIGNED", "info", f"Order assigned to transporter: {s}",
                               ev.note, s, ev.source))
        elif ev.type == "DRIVER_REPORT":
            items.append(_item(key, ev.occurred_at, "REPORT", "alert", f"Driver report on {s}", ev.note, s, "DRIVER"))
        elif ev.type in ("DISRUPTION_START", "DISRUPTION_END"):
            disruptions[(ev.type, ev.note, ev.occurred_at)].append(ev)
        elif ev.type == "REROUTED":
            items.append(_item(key, ev.occurred_at, "INTERVENTION", "ok", f"Reroute approved: {s}", ev.note, s,
                               "COORDINATOR"))
        elif ev.type == "SPLIT":
            items.append(_item(key, ev.occurred_at, "INTERVENTION", "ok", f"Split approved: {s}", ev.note, s,
                               "COORDINATOR"))
        elif ev.type == "DECISION":
            items.append(_item(key, ev.occurred_at, "INTERVENTION", "info", f"Continue approved: {s}", ev.note, s,
                               "COORDINATOR"))
    for (typ, note, at), evs in disruptions.items():
        ships = sorted({e.shipment_id for e in evs})
        start = typ == "DISRUPTION_START"
        items.append(_item(f"ev:{min(e.id for e in evs)}", at, "DISRUPTION", "alert" if start else "ok",
                           ("Road disruption detected: " if start else "Disruption ended: ") + note.split(" (DSR")[0],
                           f"Affects {', '.join(ships)}", ships[0], evs[0].source))

    # --- alerts (coordinator alerts, and the customer notifications generated alongside them) ---
    for al in db.query(m.Alert).order_by(m.Alert.id.desc()).limit(80):
        if al.audience_role == "COORDINATOR":
            sev = {"CRITICAL": "alert", "HIGH": "alert", "MEDIUM": "warn"}.get(al.severity, "info")
            items.append(_item(f"al:{al.id}", al.created_sim_at, "ALERT", sev, f"Coordinator alert: {al.title}",
                               al.message, al.shipment_id, "ENGINE"))
        else:
            items.append(_item(f"al:{al.id}", al.created_sim_at, "NOTIFICATION", "info",
                               f"Customer notification generated for {al.order_id}", al.message, al.shipment_id,
                               "SYSTEM"))

    # --- predictions: risk changes and ETA recalculations ---
    by_ship: dict[str, list[m.Prediction]] = defaultdict(list)
    for p in db.query(m.Prediction).order_by(m.Prediction.id.desc()).limit(500):
        by_ship[p.shipment_id].append(p)
    for sid, rows in by_ship.items():
        for i, p in enumerate(rows):
            older = rows[i + 1] if i + 1 < len(rows) else None
            if older is not None and older.risk_category != p.risk_category:
                up = RISK_ORDER.index(p.risk_category) > RISK_ORDER.index(older.risk_category)
                items.append(_item(f"pr:{p.id}", p.created_sim_at, "RISK", "alert" if up else "ok",
                                   f"Risk changed from {older.risk_category} to {p.risk_category}: {sid}",
                                   f"P(late) {p.p_late:.0%}, risk index {p.risk_index}", sid, "ENGINE"))
            elif (p.previous_p50_at is not None and abs(hours(p.p50_at - p.previous_p50_at)) >= 0.05
                  and not p.trigger.startswith(("clock advanced", "initial seed"))):
                d = hours(p.p50_at - p.previous_p50_at)
                items.append(_item(f"pr:{p.id}", p.created_sim_at, "ETA", "warn" if d > 0 else "ok",
                                   f"ETA recalculated for {sid}: {d:+.1f} h", p.trigger, sid, "ENGINE"))

    # --- audit: decisions that are not already a shipment event; new orders ---
    wanted = list(AUDIT_TEXT) + ["ORDER_CREATED", "DOCUMENT_UPLOADED", "DOCUMENT_REPLACED", "POD_DOCUMENT_UPLOADED", "POD_VERIFIED"]
    for au in (db.query(m.AuditEvent).filter(m.AuditEvent.action.in_(wanted))
               .order_by(m.AuditEvent.id.desc()).limit(40)):
        if au.action == "ORDER_CREATED":
            items.append(_item(f"au:{au.id}", au.sim_time, "ORDER", "info", f"New order created: {au.entity_id}",
                               "", (au.after_json or {}).get("shipment_id"), "COORDINATOR"))
            continue
        if au.action in ("DOCUMENT_UPLOADED", "DOCUMENT_REPLACED", "POD_DOCUMENT_UPLOADED", "POD_VERIFIED"):
            a = au.after_json or {}
            title = {"DOCUMENT_UPLOADED": f"Invoice uploaded for {a.get('order_id')}",
                     "DOCUMENT_REPLACED": f"Invoice replaced (version {a.get('version')}) for {a.get('order_id')}",
                     "POD_DOCUMENT_UPLOADED": f"Proof of delivery uploaded for {a.get('shipment_id')}",
                     "POD_VERIFIED": f"Proof of delivery verified for {a.get('shipment_id')}"}[au.action]
            items.append(_item(f"au:{au.id}", au.sim_time, "DOCUMENT", "ok", title,
                               (f"Received by {a['recipient']}" if a.get("recipient") else a.get("reason") or ""),
                               a.get("shipment_id"), au.actor_role))
            continue
        text, sev = AUDIT_TEXT[au.action]
        detail = (au.after_json or {}).get("reason", "") if au.action == "CONSTRAINT OVERRIDE" else ""
        items.append(_item(f"au:{au.id}", au.sim_time, "AUDIT", sev, text, detail,
                           au.entity_id if au.entity_type == "shipment" else None, au.actor_role))

    items.sort(key=lambda x: (x["at"], -RANK[x["id"][:2]], int(x["id"].split(":")[1])), reverse=True)
    return items[:limit]


def sync_stamp(db: Session) -> dict:
    """Opaque fingerprint of 'anything a screen could show has changed'. Clients poll this cheap endpoint and
    reload their data only when it changes. It is hashed, so it reveals no counts."""
    import hashlib

    from sqlalchemy import Integer, cast, func

    def mx(col):
        return db.query(func.coalesce(func.max(col), 0)).scalar()
    st = db.get(m.SimulationState, 1)
    acked = db.query(func.coalesce(func.sum(cast(m.Alert.acknowledged, Integer)), 0)).scalar()
    raw = "|".join(str(x) for x in (
        mx(m.ShipmentEvent.id), mx(m.Alert.id), acked, mx(m.Prediction.id), mx(m.AuditEvent.id), mx(m.Intervention.id),
        st.clock_version, st.paused, st.speed, st.created_at, mx(m.BusinessAssumptions.assumptions_version)))
    return {"stamp": hashlib.sha1(raw.encode()).hexdigest()[:12], "sim_now": st.sim_now, "paused": st.paused,
            "speed": st.speed}
