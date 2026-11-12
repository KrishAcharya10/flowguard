"""Plant X gate slot booking (bonus feature).

Hourly appointment slots with a configurable capacity. A booking has its OWN lifecycle, separate from the
shipment lifecycle:  BOOKED -> CHECKED_IN -> COMPLETED, plus CANCELLED and MISSED.

Time: everything here uses the SIMULATION clock (simulation_state.sim_now), never the wall clock. Slots are
whole IST hours stored as UTC. Capacity-changing operations run under one lock and commit inside it, so two
simultaneous requests can never both take the last place (one worker process; SQLite has a single writer).
"""
from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from .core import add_event, audit, get_assumptions, sim_now
from .core import hours as _hours

IST = timedelta(hours=5, minutes=30)           # Asia/Kolkata has no daylight saving
CHECK_IN_EARLY_MIN = 60                        # the gate opens for check-in 60 simulated minutes before the slot
GATE_NAME = "Plant X Main Gate, Gate 2 (weighbridge lane B)"
GATE_INSTRUCTIONS = ("Report to the gate office with your delivery note. Lane B is for bulk polymer tankers. "
                     "Keep the engine off while you wait to be called.")
PRE_DEPARTURE = ("PLANNED", "LOADING", "AT_PLANT_GATE")
ACTIVE = ("BOOKED", "CHECKED_IN")
COUNTED = ("BOOKED", "CHECKED_IN", "COMPLETED")        # statuses that use up a place in the slot
DAYS_BEFORE, DAYS_AFTER = 1, 3
_lock = threading.Lock()


def ist_label(t: datetime) -> str:
    return (t + IST).strftime("%d %b, %H:%M IST")


def slot_start_utc(local_day: date, hour: int) -> datetime:
    return datetime.combine(local_day, time(hour)) - IST


def ensure_slots(db: Session, commit: bool = True) -> None:
    """Create the missing hourly slots for the window around the simulated 'today'. Idempotent."""
    now = sim_now(db)
    today = (now + IST).date()
    first = slot_start_utc(today - timedelta(days=DAYS_BEFORE), 0)
    count = (DAYS_BEFORE + 1 + DAYS_AFTER) * 24
    last = first + timedelta(hours=count)
    have = {r[0] for r in db.query(m.GateSlot.slot_start).filter(m.GateSlot.slot_start >= first,
                                                                 m.GateSlot.slot_start < last)}
    if len(have) == count:
        return
    cap = get_assumptions(db)[0].gate_slot_capacity
    for i in range(count):
        st = first + timedelta(hours=i)
        if st not in have:
            db.add(m.GateSlot(slot_start=st, slot_end=st + timedelta(hours=1), capacity=cap, closed=False, note=""))
    db.flush()
    if commit:
        db.commit()


def booked_count(db: Session, slot_id: int, exclude_booking: Optional[int] = None) -> int:
    q = db.query(m.GateBooking).filter(m.GateBooking.slot_id == slot_id, m.GateBooking.status.in_(COUNTED))
    if exclude_booking is not None:
        q = q.filter(m.GateBooking.id != exclude_booking)
    return q.count()


def slot_state(slot: m.GateSlot, booked: int, now: datetime) -> str:
    if slot.slot_end <= now:
        return "PAST"
    if slot.closed:
        return "UNAVAILABLE"
    if booked > slot.capacity:
        return "OVERBOOKED"
    if booked >= slot.capacity:
        return "FULL"
    return "OPEN"


# ------------------------------------------------------------------------------------------ views
def booking_out(db: Session, b: m.GateBooking) -> s.BookingOut:
    slot = db.get(m.GateSlot, b.slot_id)
    sh = db.get(m.Shipment, b.shipment_id)
    order = db.get(m.Order, sh.order_id)
    driver = db.get(m.User, b.driver_user_id) if b.driver_user_id else None
    old = db.get(m.GateSlot, b.rescheduled_from_slot_id) if b.rescheduled_from_slot_id else None
    return s.BookingOut(
        id=b.id, shipment_id=b.shipment_id, order_id=order.id, product_code=order.product_code,
        quantity_tonnes=sh.quantity_tonnes, customer_name=db.get(m.Customer, order.customer_id).name,
        transporter_id=b.transporter_id, transporter_name=db.get(m.Transporter, b.transporter_id).name,
        driver_id=driver.id if driver else None, driver_name=driver.display_name if driver else None,
        driver_username=driver.username if driver else None, vehicle_label=b.vehicle_label, slot_id=slot.id,
        slot_start=slot.slot_start, slot_end=slot.slot_end, status=b.status, created_sim_at=b.created_sim_at,
        checked_in_at=b.checked_in_at, completed_at=b.completed_at, cancelled_at=b.cancelled_at,
        cancel_reason=b.cancel_reason, rescheduled_from=old.slot_start if old else None,
        shipment_state=sh.state, check_in_opens_at=slot.slot_start - timedelta(minutes=CHECK_IN_EARLY_MIN))


def overview(db: Session) -> s.GateOverviewOut:
    ensure_slots(db)
    now = sim_now(db)
    slots = db.query(m.GateSlot).order_by(m.GateSlot.slot_start).all()
    by_slot: dict[int, list[m.GateBooking]] = {}
    for b in (db.query(m.GateBooking).filter(m.GateBooking.status.in_(COUNTED))
              .order_by(m.GateBooking.id)):
        by_slot.setdefault(b.slot_id, []).append(b)
    out = []
    for sl in slots:
        bs = by_slot.get(sl.id, [])
        out.append(s.SlotOut(
            id=sl.id, slot_start=sl.slot_start, slot_end=sl.slot_end, capacity=sl.capacity, booked=len(bs),
            available=0 if sl.closed else max(0, sl.capacity - len(bs)), state=slot_state(sl, len(bs), now),
            note=sl.note, bookings=[booking_out(db, b) for b in bs]))
    return s.GateOverviewOut(sim_now=now, default_capacity=get_assumptions(db)[0].gate_slot_capacity,
                             check_in_early_minutes=CHECK_IN_EARLY_MIN, gate_name=GATE_NAME, slots=out)


def list_bookings(db: Session, scope: str, shipment_id: Optional[str] = None) -> list[s.BookingOut]:
    q = db.query(m.GateBooking).join(m.GateSlot, m.GateSlot.id == m.GateBooking.slot_id)
    if shipment_id:
        q = q.filter(m.GateBooking.shipment_id == shipment_id)
    if scope == "upcoming":
        q = q.filter(m.GateBooking.status.in_(ACTIVE)).order_by(m.GateSlot.slot_start, m.GateBooking.id)
    elif scope == "history":
        q = q.filter(m.GateBooking.status.notin_(ACTIVE)).order_by(m.GateSlot.slot_start.desc(), m.GateBooking.id)
    else:
        q = q.order_by(m.GateSlot.slot_start, m.GateBooking.id)
    return [booking_out(db, b) for b in q.limit(200)]


def driver_bookings(db: Session, user: m.User) -> list[s.DriverBookingOut]:
    now = sim_now(db)
    rows = (db.query(m.GateBooking).join(m.GateSlot, m.GateSlot.id == m.GateBooking.slot_id)
            .filter(m.GateBooking.driver_user_id == user.id).order_by(m.GateSlot.slot_start.desc()).limit(12).all())
    out = []
    for b in sorted(rows, key=lambda x: (x.status not in ACTIVE, db.get(m.GateSlot, x.slot_id).slot_start)):
        slot = db.get(m.GateSlot, b.slot_id)
        sh = db.get(m.Shipment, b.shipment_id)
        order = db.get(m.Order, sh.order_id)
        opens = slot.slot_start - timedelta(minutes=CHECK_IN_EARLY_MIN)
        can = b.status == "BOOKED" and opens <= now < slot.slot_end and sh.state in PRE_DEPARTURE
        hint = None
        if b.status == "BOOKED" and not can:
            hint = (f"Check-in opens at {ist_label(opens)} (simulated time)." if now < opens
                    else "This slot has ended.")
        out.append(s.DriverBookingOut(
            id=b.id, shipment_id=b.shipment_id, order_id=order.id, product_code=order.product_code,
            quantity_tonnes=sh.quantity_tonnes, vehicle_label=b.vehicle_label, slot_start=slot.slot_start,
            slot_end=slot.slot_end, status=b.status, gate_name=GATE_NAME, gate_instructions=GATE_INSTRUCTIONS,
            can_check_in=can, check_in_hint=hint, check_in_opens_at=opens, checked_in_at=b.checked_in_at,
            completed_at=b.completed_at, cancel_reason=b.cancel_reason))
    return out


# ------------------------------------------------------------------------------------- operations
def _slot_for_booking(db: Session, slot_id: int, now: datetime, exclude_booking: Optional[int] = None) -> m.GateSlot:
    slot = db.get(m.GateSlot, slot_id)
    if slot is None:
        raise HTTPException(404, "Slot not found")
    if slot.slot_end <= now:
        raise HTTPException(409, f"That slot ({ist_label(slot.slot_start)}) is already in the past (simulated time).")
    if slot.closed:
        raise HTTPException(409, f"That slot is unavailable{': ' + slot.note if slot.note else ''}.")
    n = booked_count(db, slot.id, exclude_booking)
    if n >= slot.capacity:
        raise HTTPException(409, f"That slot is full ({n} of {slot.capacity} places taken). Choose another slot.")
    return slot


def _active_booking(db: Session, shipment_id: str) -> Optional[m.GateBooking]:
    return db.query(m.GateBooking).filter(m.GateBooking.shipment_id == shipment_id,
                                          m.GateBooking.status.in_(ACTIVE)).first()


def book(db: Session, user: m.User, shipment_id: str, slot_id: int, transporter_id: Optional[str],
         driver_user_id: Optional[int]) -> m.GateBooking:
    with _lock:
        now = sim_now(db)
        sh = db.get(m.Shipment, shipment_id)
        if sh is None or sh.is_historical:
            raise HTTPException(404, "Shipment not found")
        if sh.disposition != "ACTIVE" or sh.state not in PRE_DEPARTURE:
            raise HTTPException(409, "A gate slot can only be booked for a shipment that has not left Plant X yet.")
        existing = _active_booking(db, shipment_id)
        if existing is not None:
            raise HTTPException(409, f"{shipment_id} already has an active booking ({ist_label(db.get(m.GateSlot, existing.slot_id).slot_start)}). "
                                     "Reschedule or cancel it instead.")
        tid = transporter_id or sh.transporter_id
        if tid != sh.transporter_id:
            raise HTTPException(422, "The booking's transporter must be the shipment's transporter.")
        driver_id = driver_user_id if driver_user_id is not None else sh.driver_user_id
        if driver_id is not None:
            drv = db.get(m.User, driver_id)
            if drv is None or drv.role != "TRANSPORTER" or not drv.is_active or drv.transporter_id != tid:
                raise HTTPException(422, "The driver must be an active driver of the selected transporter.")
        slot = _slot_for_booking(db, slot_id, now)
        b = m.GateBooking(shipment_id=shipment_id, slot_id=slot.id, transporter_id=tid, driver_user_id=driver_id,
                          vehicle_label=sh.vehicle_label, status="BOOKED", created_sim_at=now)
        db.add(b)
        db.flush()
        add_event(db, sh.id, "GATE", now, f"Gate slot booked for {sh.id}: {ist_label(slot.slot_start)}",
                  state=sh.state, user=user, source="COORDINATOR")
        audit(db, user, "GATE_BOOKING_CREATED", "gate_booking", b.id,
              after={"shipment_id": sh.id, "slot": slot.slot_start.isoformat(), "driver_user_id": driver_id,
                     "vehicle": sh.vehicle_label})
        db.commit()
        return b


def reschedule(db: Session, user: m.User, booking_id: int, slot_id: int) -> m.GateBooking:
    with _lock:
        now = sim_now(db)
        b = db.get(m.GateBooking, booking_id)
        if b is None:
            raise HTTPException(404, "Booking not found")
        if b.status != "BOOKED":
            raise HTTPException(409, f"Only a BOOKED appointment can be rescheduled (this one is {b.status}).")
        if b.slot_id == slot_id:
            raise HTTPException(422, "Choose a different slot.")
        new = _slot_for_booking(db, slot_id, now, exclude_booking=b.id)
        old = db.get(m.GateSlot, b.slot_id)
        b.rescheduled_from_slot_id, b.slot_id = old.id, new.id          # old place is released, new one taken, atomically
        add_event(db, b.shipment_id, "GATE", now,
                  f"Gate slot rescheduled for {b.shipment_id}: {ist_label(old.slot_start)} -> {ist_label(new.slot_start)}",
                  user=user, source="COORDINATOR")
        audit(db, user, "GATE_BOOKING_RESCHEDULED", "gate_booking", b.id,
              before={"slot": old.slot_start.isoformat()}, after={"slot": new.slot_start.isoformat()})
        db.commit()
        return b


def cancel(db: Session, user: m.User, booking_id: int, reason: Optional[str]) -> m.GateBooking:
    with _lock:
        now = sim_now(db)
        b = db.get(m.GateBooking, booking_id)
        if b is None:
            raise HTTPException(404, "Booking not found")
        if b.status == "CANCELLED":
            return b                                                    # idempotent
        if b.status != "BOOKED":
            raise HTTPException(409, f"Only a BOOKED appointment can be cancelled (this one is {b.status}).")
        slot = db.get(m.GateSlot, b.slot_id)
        b.status, b.cancelled_at, b.cancel_reason = "CANCELLED", now, (reason or "").strip() or None
        add_event(db, b.shipment_id, "GATE", now, f"Gate slot cancelled for {b.shipment_id}: {ist_label(slot.slot_start)}",
                  user=user, source="COORDINATOR")
        audit(db, user, "GATE_BOOKING_CANCELLED", "gate_booking", b.id,
              before={"status": "BOOKED", "slot": slot.slot_start.isoformat()}, after={"status": "CANCELLED", "reason": b.cancel_reason})
        db.commit()
        return b


def check_in(db: Session, user: m.User, booking_id: int) -> m.GateBooking:
    with _lock:
        now = sim_now(db)
        b = db.get(m.GateBooking, booking_id)
        if b is None or b.driver_user_id != user.id:
            raise HTTPException(404, "Booking not found")             # someone else's booking looks the same as none
        if b.status == "CHECKED_IN":
            return b                                                    # idempotent
        if b.status != "BOOKED":
            raise HTTPException(409, f"This appointment is {b.status} and cannot be checked in.")
        slot = db.get(m.GateSlot, b.slot_id)
        opens = slot.slot_start - timedelta(minutes=CHECK_IN_EARLY_MIN)
        if now < opens:
            raise HTTPException(409, f"Too early to check in. Check-in opens at {ist_label(opens)} (simulated time).")
        if now >= slot.slot_end:
            raise HTTPException(409, "This slot has ended; ask the control tower to rebook you.")
        b.status, b.checked_in_at = "CHECKED_IN", now
        add_event(db, b.shipment_id, "GATE", now, f"{b.vehicle_label} checked in at the plant gate for {b.shipment_id}",
                  user=user, source="DRIVER")
        audit(db, user, "GATE_BOOKING_CHECKED_IN", "gate_booking", b.id, before={"status": "BOOKED"},
              after={"status": "CHECKED_IN", "sim_time": now.isoformat()})
        db.commit()
        return b


def complete(db: Session, user: m.User, booking_id: int) -> m.GateBooking:
    with _lock:
        now = sim_now(db)
        b = db.get(m.GateBooking, booking_id)
        if b is None:
            raise HTTPException(404, "Booking not found")
        if b.status == "COMPLETED":
            return b
        if b.status != "CHECKED_IN":
            raise HTTPException(409, f"Only a CHECKED_IN appointment can be completed (this one is {b.status}).")
        b.status, b.completed_at = "COMPLETED", now
        add_event(db, b.shipment_id, "GATE", now, f"Gate appointment completed for {b.shipment_id}", user=user,
                  source="COORDINATOR")
        audit(db, user, "GATE_BOOKING_COMPLETED", "gate_booking", b.id, before={"status": "CHECKED_IN"}, after={"status": "COMPLETED"})
        db.commit()
        return b


def update_slot(db: Session, user: m.User, slot_id: int, capacity: Optional[int], closed: Optional[bool],
                note: Optional[str]) -> m.GateSlot:
    with _lock:
        slot = db.get(m.GateSlot, slot_id)
        if slot is None:
            raise HTTPException(404, "Slot not found")
        before = {"capacity": slot.capacity, "closed": slot.closed, "note": slot.note}
        if capacity is not None:
            slot.capacity = capacity               # may drop below the bookings already made: shown as OVERBOOKED
        if closed is not None:
            slot.closed = closed
        if note is not None:
            slot.note = note.strip()
        audit(db, user, "GATE_SLOT_UPDATED", "gate_slot", slot.id, before=before,
              after={"capacity": slot.capacity, "closed": slot.closed, "note": slot.note,
                     "slot": slot.slot_start.isoformat()})
        db.commit()
        return slot


# ------------------------------------------------------------------- hooks called by other services
def complete_on_departure(db: Session, sh: m.Shipment, at: datetime) -> None:
    """The vehicle left Plant X: its appointment is finished. Runs inside the caller's transaction."""
    b = _active_booking(db, sh.id)
    if b is None:
        return
    b.status, b.completed_at = "COMPLETED", at
    audit(db, None, "GATE_BOOKING_COMPLETED", "gate_booking", b.id,
          before={"status": "CHECKED_IN" if b.checked_in_at else "BOOKED"},
          after={"status": "COMPLETED", "reason": "vehicle departed Plant X", "checked_in": b.checked_in_at is not None})


def mark_missed(db: Session, now: datetime) -> int:
    """BOOKED appointments whose slot has ended and whose vehicle never left: MISSED (capacity is released)."""
    n = 0
    rows = (db.query(m.GateBooking).join(m.GateSlot, m.GateSlot.id == m.GateBooking.slot_id)
            .filter(m.GateBooking.status == "BOOKED", m.GateSlot.slot_end <= now).all())
    for b in rows:
        slot = db.get(m.GateSlot, b.slot_id)
        b.status = "MISSED"
        add_event(db, b.shipment_id, "GATE", now,
                  f"Gate appointment missed for {b.shipment_id}: {ist_label(slot.slot_start)} (no check-in)",
                  source="SIMULATED")
        audit(db, None, "GATE_BOOKING_MISSED", "gate_booking", b.id,
              before={"status": "BOOKED"}, after={"status": "MISSED", "slot": slot.slot_start.isoformat()})
        n += 1
    return n


def day_summary(db: Session) -> dict:
    """Headline numbers for the Control Tower card: today's (simulated) IST day."""
    ensure_slots(db)
    now = sim_now(db)
    today = (now + IST).date()
    start, end = slot_start_utc(today, 0), slot_start_utc(today + timedelta(days=1), 0)
    slots = db.query(m.GateSlot).filter(m.GateSlot.slot_start >= start, m.GateSlot.slot_start < end).all()
    booked = capacity = full = unavailable = 0
    for sl in slots:
        n = booked_count(db, sl.id)
        booked += n
        if sl.closed:
            unavailable += 1
            continue
        capacity += sl.capacity
        if n >= sl.capacity:
            full += 1
    upcoming = list_bookings(db, "upcoming")[:4]
    return {"capacity": capacity, "booked": booked, "full_slots": full, "unavailable_slots": unavailable, "upcoming": upcoming,
            "day_label": (now + IST).strftime("%a %d %b")}
