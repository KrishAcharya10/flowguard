""""Where is my order?" assistant: a deterministic, API-backed chat for customers (bonus feature).

It does not invent anything and it uses NO language model. Each message is classified by simple keyword rules
into an intent; the answer is then assembled only from the SAME customer-safe records the portal shows
(CustomerOrderOut / CustomerDocumentOut). Therefore it cannot reveal costs, penalty rates, stock assumptions,
transporter details or another customer's data, and it cannot change anything: it only reads.
When a fact is not available it says so.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..engine.geo import haversine_km
from . import documents as doc_svc
from . import views
from .core import get_assumptions, hours, sim_now

IST = timedelta(hours=5, minutes=30)
ORDER_RE = re.compile(r"\bORD-[A-Z0-9-]+\b", re.I)

# Order matters: the first matching rule wins.
RULES = [
    ("COMMERCIAL", r"\b(costs?|price|prices|pricing|freight|penalt\w*|margin|charges?|discounts?|other customers?|competitors?|"
                   r"transporters?|carriers?|assumptions?|stock-?outs?|inventory|contract\w*)\b"),
    ("POD", r"\b(pod|proof of delivery|signed|delivery note|delivery document|receipt)\b"),
    ("INVOICE", r"\b(invoices?|bills?|billing)\b"),
    ("DELAY", r"\b(delay\w*|late|why|behind|problem|issue|slow)\b"),
    ("PROMISE", r"\b(original|promised|promise|committed|agreed)\b"),
    ("UPDATED_ETA", r"\b(updated|revised|new eta|new date|latest eta|latest date)\b"),
    ("GATE", r"\b(customer gate|my gate|reached|arrived|at (the |my )?gate)\b"),
    ("DISPATCH", r"\b(dispatch\w*|shipped|left|leave|departed|sent|loaded|loading)\b"),
    ("ETA", r"\b(when|eta|arrive|arrival|expected|how long)\b"),
    ("WHERE", r"\b(where|location|position|track\w*|whereabouts)\b"),
    ("STATUS", r"\b(status|progress|update|how is|how's)\b"),
    ("HELLO", r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b"),
    ("HELP", r"\b(help|what can you|can you)\b"),
]
SUGGESTIONS = ["Where is my order?", "When will my delivery arrive?", "Has my order been dispatched?",
               "Why is my order delayed?", "What was the original promised delivery?", "Is my proof of delivery available?"]


def classify(message: str) -> str:
    text = message.lower().strip()
    for name, pattern in RULES:
        if re.search(pattern, text):
            return name
    return "UNKNOWN"


def _t(t: Optional[datetime], round_5: bool = False) -> str:
    if t is None:
        return "not available"
    if round_5:
        t = t.replace(second=0, microsecond=0)
        t = t - timedelta(minutes=t.minute % 5)
    return (t + IST).strftime("%d %b, %H:%M IST")


def _near(sh: s.CustomerShipmentOut) -> str:
    p = sh.last_reported_position
    best = min(sh.route_points, key=lambda r: haversine_km(p.lat, p.lon, r.lat, r.lon))
    return best.name


def _lot_name(o: s.CustomerOrderOut, sh: s.CustomerShipmentOut) -> str:
    if len(o.shipments) < 2:
        return ""
    return f"The {'urgent' if sh.lot_type == 'URGENT' else 'remaining'} delivery ({sh.quantity_tonnes:g} t): "


def _where(o, ans) -> None:
    for sh in o.shipments:
        pre = _lot_name(o, sh)
        if sh.state in ("PLANNED", "LOADING", "AT_PLANT_GATE"):
            ans["text"].append(f"{pre}It has not left Plant X yet (status: {sh.state_label}). There is no vehicle position to show until it departs.")
        elif sh.state == "IN_TRANSIT":
            p = sh.last_reported_position
            if p is None:
                ans["text"].append(f"{pre}It is on its way, but no position has been reported yet.")
                continue
            line = (f"{pre}Latest reported position: near {_near(sh)}, about {sh.progress_pct}% of the way to you "
                    f"(reported {_t(p.reported_at)}).")
            if sh.data_confidence == "STALE":
                line += " The vehicle has not reported for a while, so this position may be out of date."
            ans["text"].append(line)
            if ans["position"] is None:
                ans["position"] = s.ChatPosition(lat=p.lat, lon=p.lon, reported_at=p.reported_at, near=_near(sh),
                                                 progress_pct=sh.progress_pct)
        elif sh.state == "ARRIVED_AT_CUSTOMER_GATE":
            ans["text"].append(f"{pre}It has arrived at your receiving gate ({_t(sh.arrived_at)}).")
        else:
            ans["text"].append(f"{pre}It was delivered ({_t(sh.delivered_at or sh.arrived_at)}).")


def _status(o, ans) -> None:
    for sh in o.shipments:
        ans["text"].append(f"{_lot_name(o, sh)}Status: {sh.state_label}. Delivery progress {sh.progress_pct}%.")
    ans["text"].append(f"Original promise: {_t(o.promised_at)}. " + (
        f"Updated expected delivery: {_t(o.updated_expected_delivery, True)}." if o.updated_expected_delivery else ""))


def _eta(o, ans) -> None:
    for sh in o.shipments:
        pre = _lot_name(o, sh)
        if sh.state in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
            ans["text"].append(f"{pre}It has already arrived ({_t(sh.arrived_at)}).")
        elif sh.updated_expected_delivery:
            ans["text"].append(f"{pre}Expected around {_t(sh.updated_expected_delivery, True)}, most likely between "
                               f"{_t(sh.eta_from, True)} and {_t(sh.eta_to, True)}. This is an estimate, not a guarantee.")
        else:
            ans["text"].append(f"{pre}I do not have an arrival estimate for this delivery yet.")
    ans["text"].append(f"The original promise was {_t(o.promised_at)}.")


def _delay(o, ans) -> None:
    delayed = False
    for sh in o.shipments:
        if sh.state in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
            continue
        late = sh.updated_expected_delivery is not None and sh.updated_expected_delivery > o.promised_at
        if sh.delay_explanation:
            delayed = True
            extra = ""
            if late:
                extra = f" It is now expected about {hours(sh.updated_expected_delivery - o.promised_at):.1f} h after the original promise."
            ans["text"].append(f"{_lot_name(o, sh)}{sh.delay_explanation}{extra}")
        elif late:
            delayed = True
            ans["text"].append(f"{_lot_name(o, sh)}It is expected about {hours(sh.updated_expected_delivery - o.promised_at):.1f} h after the original promise, "
                               "but the risk of a larger delay is low.")
    if delayed:
        ans["text"].append(f"Next step: you do not need to do anything. This chat and your portal update automatically. If your plant is "
                           f"affected, contact your logistics contact at Plant X and quote order {o.id}.")
        ans["links"].append(s.ChatLink(kind="tab", label="See delivery updates", tab="updates"))
    else:
        ans["text"].append("No delay is expected. Your delivery is on track." if not all(
            x.state in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED") for x in o.shipments) else "The delivery has already arrived.")


def _dispatch(o, ans) -> None:
    for sh in o.shipments:
        pre = _lot_name(o, sh)
        left = next((mm.occurred_at for mm in sh.milestones if mm.state == "IN_TRANSIT" and mm.occurred_at), None)
        if sh.state in ("PLANNED", "LOADING", "AT_PLANT_GATE"):
            ans["text"].append(f"{pre}Not yet dispatched. Status: {sh.state_label}.")
        else:
            ans["text"].append(f"{pre}Yes, it left Plant X{' at ' + _t(left) if left else ''}.")


def _gate(o, ans) -> None:
    for sh in o.shipments:
        pre = _lot_name(o, sh)
        if sh.state in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
            ans["text"].append(f"{pre}Yes, it reached your gate at {_t(sh.arrived_at)}.")
        else:
            ans["text"].append(f"{pre}Not yet. Status: {sh.state_label}, about {sh.progress_pct}% of the way.")


def _promise(o, ans) -> None:
    ans["text"].append(f"The original promised delivery for {o.id} is {_t(o.promised_at)}. That promise does not change; "
                       "any newer estimate is shown separately as the updated expected delivery.")


def _updated(o, ans) -> None:
    if o.updated_expected_delivery is None:
        ans["text"].append("There is no updated estimate because the delivery has arrived or has not been planned yet.")
        return
    diff = hours(o.updated_expected_delivery - o.promised_at)
    rel = "later than" if diff > 0.05 else "earlier than" if diff < -0.05 else "in line with"
    ans["text"].append(f"The updated expected delivery is {_t(o.updated_expected_delivery, True)}"
                       + (f", about {abs(diff):.1f} h {rel} the original promise ({_t(o.promised_at)})." if rel != "in line with"
                          else f", in line with the original promise ({_t(o.promised_at)})."))


def _pod(o, docs, ans) -> None:
    for sh in o.shipments:
        pre = _lot_name(o, sh)
        d = next((x for x in docs if x.kind == "POD" and x.shipment_id == sh.id), None)
        if d is not None:
            ans["text"].append(f"{pre}Yes, the signed proof of delivery is available (received by {d.recipient_name or 'the receiving team'}, "
                               f"{_t(d.delivered_at)}).")
            ans["links"].append(s.ChatLink(kind="document", label=f"Download proof of delivery ({sh.id})", document_id=d.id, order_id=o.id))
        elif sh.state == "DELIVERED":
            ans["text"].append(f"{pre}It was delivered, but the signed document has not been uploaded yet.")
        elif sh.state == "ARRIVED_AT_CUSTOMER_GATE":
            ans["text"].append(f"{pre}Not yet. The vehicle has arrived and the proof of delivery is awaiting signature.")
        else:
            ans["text"].append(f"{pre}Not yet. It becomes available after the delivery is completed.")


def _invoice(o, docs, ans) -> None:
    d = next((x for x in docs if x.kind == "INVOICE" and x.order_id == o.id), None)
    if d is None:
        ans["text"].append(f"There is no invoice for {o.id} yet. You will be notified when it is available.")
    else:
        ans["text"].append(f"Yes, invoice {d.invoice_number or ''} is available (uploaded {_t(d.uploaded_at)}).".replace("invoice  ", "invoice "))
        ans["links"].append(s.ChatLink(kind="document", label="Download invoice", document_id=d.id, order_id=o.id))


HANDLERS = {"WHERE": _where, "STATUS": _status, "ETA": _eta, "DELAY": _delay, "DISPATCH": _dispatch, "GATE": _gate,
            "PROMISE": _promise, "UPDATED_ETA": _updated}


def reply(db: Session, user: m.User, message: str, order_id: Optional[str]) -> s.ChatReplyOut:
    now = sim_now(db)
    a, _ = get_assumptions(db)
    intent = classify(message)
    out = lambda text, **kw: s.ChatReplyOut(text=text, intent=intent, as_of=now,  # noqa: E731
                                            suggestions=kw.pop("suggestions", SUGGESTIONS[:4]), **kw)

    if intent == "COMMERCIAL":
        return out("I cannot share internal commercial information such as costs, penalty terms, transporter details or other customers' "
                   "data. I can tell you where your order is, when it should arrive and why it may be late.")
    if intent in ("HELLO", "HELP", "UNKNOWN"):
        lead = "Hello! " if intent == "HELLO" else ""
        return out(lead + "I can answer questions about your own orders: where they are, their status, when they will arrive, whether "
                   "they are delayed and why, and whether your invoice and proof of delivery are available. What would you like to know?"
                   if intent != "UNKNOWN" else
                   "I am not sure what you mean. I can only answer questions about your orders and their documents. Try one of the questions below.")

    # only this customer's orders are ever loaded
    order_ids = [r[0] for r in db.query(m.Shipment.order_id).join(m.Order, m.Order.id == m.Shipment.order_id)
                 .filter(m.Order.customer_id == user.customer_id, m.Shipment.is_historical.is_(False)).distinct()]
    orders = [views.customer_order(db, o, now, a) for o in db.query(m.Order).filter(m.Order.id.in_(order_ids))
              .order_by(m.Order.promised_at, m.Order.id)]
    docs = doc_svc.customer_documents(db, user.customer_id)
    wanted = order_id or (ORDER_RE.search(message).group(0).upper() if ORDER_RE.search(message) else None)
    if wanted:
        picked = [o for o in orders if o.id.upper() == wanted.upper()]
        if not picked:
            listing = ", ".join(o.id for o in orders) or "none right now"
            return out(f"I could not find an order {wanted} on your account. I can only look up your own orders: {listing}.",
                       links=[s.ChatLink(kind="order", label=f"Open {o.id}", order_id=o.id) for o in orders[:5]])
    else:
        picked = [o for o in orders if o.status != "Delivered"] or orders
    if not picked:
        return out("You have no orders to look up right now.")

    facts: list[s.ChatFact] = []
    links: list[s.ChatLink] = []
    position = None
    lines: list[str] = []
    focus = None
    if len(picked) == 1:
        o = picked[0]
        focus = o.id
        ans = {"text": [], "links": [], "position": None}
        if intent == "POD":
            _pod(o, docs, ans)
        elif intent == "INVOICE":
            _invoice(o, docs, ans)
        else:
            HANDLERS[intent](o, ans)
        lines += ans["text"]
        links += ans["links"]
        position = ans["position"]
        facts = [s.ChatFact(label="Order", value=f"{o.id} · {o.product_code} · {o.quantity_tonnes:g} t"),
                 s.ChatFact(label="Status", value=o.status),
                 s.ChatFact(label="Original promise", value=_t(o.promised_at)),
                 s.ChatFact(label="Updated expected delivery", value=_t(o.updated_expected_delivery, True) if o.updated_expected_delivery else "not available")]
        links.append(s.ChatLink(kind="order", label=f"Open {o.id}", order_id=o.id))
    else:
        lines.append(f"You have {len(picked)} open orders. Here is the answer for each:")
        for o in picked[:6]:
            ans = {"text": [], "links": [], "position": None}
            if intent == "POD":
                _pod(o, docs, ans)
            elif intent == "INVOICE":
                _invoice(o, docs, ans)
            else:
                HANDLERS[intent](o, ans)
            short = " ".join(ans["text"][:2])
            facts.append(s.ChatFact(label=o.id, value=short))
            links += [x for x in ans["links"] if x.kind == "document"]
            links.append(s.ChatLink(kind="order", label=f"Open {o.id}", order_id=o.id))
            position = position or ans["position"]
        lines.append("Ask about one order (for example “Where is ORD-PTH-1116-03?”) for more detail.")
    sugg = [q for q in SUGGESTIONS if q.lower() != message.strip().lower()][:4]
    return s.ChatReplyOut(text="\n".join(lines), intent=intent, order_id=focus, facts=facts, links=links[:8],
                          suggestions=sugg, position=position, as_of=now)
