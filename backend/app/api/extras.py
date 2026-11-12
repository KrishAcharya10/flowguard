"""Bonus features: gate slot booking, invoice / proof-of-delivery documents, and the customer chat assistant.

Uploads are sent as the raw request body (Content-Type: the file's type) with metadata in the query string, so no
multipart parser is needed. The size limit is enforced while the body streams in.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from .. import schemas as s
from ..db import get_db
from ..security import ANY, COORD, CUST, TRANS, own_shipment
from ..services import chat as chat_svc
from ..services import documents as doc_svc
from ..services import gate as gate_svc
from ..services import views

router = APIRouter(prefix="/api")


async def _read_body(request: Request) -> bytes:
    limit = config.MAX_UPLOAD_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + 4096:
        raise HTTPException(413, f"The file is larger than the {config.MAX_UPLOAD_MB:g} MB limit.")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, f"The file is larger than the {config.MAX_UPLOAD_MB:g} MB limit.")
    return bytes(buf)


# ======================================================================== GATE SLOT BOOKING
@router.get("/gate/overview", response_model=s.GateOverviewOut, tags=["gate"])
def gate_overview(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Every hourly slot around the simulated 'today': capacity, bookings, and OPEN / FULL / OVERBOOKED / UNAVAILABLE."""
    return gate_svc.overview(db)


@router.get("/gate/summary", response_model=s.GateSummaryOut, tags=["gate"])
def gate_summary(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return s.GateSummaryOut(**gate_svc.day_summary(db))


@router.get("/gate/bookings", response_model=list[s.BookingOut], tags=["gate"])
def gate_bookings(scope: str = Query("all", pattern="^(all|upcoming|history)$"), shipment_id: Optional[str] = Query(None, max_length=40),
                  user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return gate_svc.list_bookings(db, scope, shipment_id)


@router.post("/gate/bookings", response_model=s.BookingOut, status_code=201, tags=["gate"])
def gate_book(body: s.BookIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    b = gate_svc.book(db, user, body.shipment_id, body.slot_id, body.transporter_id, body.driver_user_id)
    return gate_svc.booking_out(db, b)


@router.post("/gate/bookings/{booking_id}/reschedule", response_model=s.BookingOut, tags=["gate"])
def gate_reschedule(booking_id: int, body: s.RescheduleIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return gate_svc.booking_out(db, gate_svc.reschedule(db, user, booking_id, body.slot_id))


@router.post("/gate/bookings/{booking_id}/cancel", response_model=s.BookingOut, tags=["gate"])
def gate_cancel(booking_id: int, body: s.CancelIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return gate_svc.booking_out(db, gate_svc.cancel(db, user, booking_id, body.reason))


@router.post("/gate/bookings/{booking_id}/complete", response_model=s.BookingOut, tags=["gate"])
def gate_complete(booking_id: int, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return gate_svc.booking_out(db, gate_svc.complete(db, user, booking_id))


@router.put("/gate/slots/{slot_id}", response_model=s.SlotOut, tags=["gate"])
def gate_update_slot(slot_id: int, body: s.SlotUpdateIn, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Change a slot's capacity or mark it unavailable. Lowering capacity below the bookings already made shows OVERBOOKED."""
    gate_svc.update_slot(db, user, slot_id, body.capacity, body.closed, body.note)
    return next(x for x in gate_svc.overview(db).slots if x.id == slot_id)


@router.get("/transporter/me/gate", response_model=list[s.DriverBookingOut], tags=["gate"])
def driver_gate(user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """The driver's own gate appointments."""
    gate_svc.ensure_slots(db)
    return gate_svc.driver_bookings(db, user)


@router.post("/transporter/gate/bookings/{booking_id}/check-in", response_model=s.DriverBookingOut, tags=["gate"])
def driver_check_in(booking_id: int, user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """Driver arrives at the plant gate. Uses the simulation clock; allowed from 60 simulated minutes before the slot."""
    gate_svc.check_in(db, user, booking_id)
    return next(x for x in gate_svc.driver_bookings(db, user) if x.id == booking_id)


# ========================================================================= DOCUMENTS
@router.get("/documents/overview", response_model=list[s.DocumentsOverviewRow], tags=["documents"])
def documents_overview(user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return doc_svc.overview(db)


@router.get("/orders/{order_id}/documents", response_model=s.OrderDocumentsOut, tags=["documents"])
def order_documents(order_id: str, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    return doc_svc.order_documents(db, order_id)


@router.post("/orders/{order_id}/invoice", response_model=s.UploadResultOut, status_code=201, tags=["documents"])
async def upload_invoice(order_id: str, request: Request, filename: str = Query(..., min_length=1, max_length=200),
                         invoice_number: Optional[str] = Query(None, max_length=40),
                         reason: Optional[str] = Query(None, max_length=200),
                         user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Upload an invoice (raw file body). If one exists, `reason` is required and a new audited version replaces it."""
    data = await _read_body(request)
    d = doc_svc.upload_invoice(db, user, order_id, data, filename, invoice_number, reason)
    return s.UploadResultOut(document=doc_svc.doc_out(db, d),
                             message=f"Invoice version {d.version} uploaded for {order_id}.")


@router.post("/documents/{document_id}/verify", response_model=s.DocumentOut, tags=["documents"])
def verify_document(document_id: int, user: m.User = Depends(COORD), db: Session = Depends(get_db)):
    """Coordinator confirms a proof-of-delivery document belongs to the right shipment."""
    return doc_svc.doc_out(db, doc_svc.verify_pod(db, user, document_id))


@router.get("/documents/{document_id}/download", tags=["documents"])
def download_document(document_id: int, user: m.User = Depends(ANY), db: Session = Depends(get_db)):
    """The ONLY way to read a stored file. Ownership is checked every time and every download is audited."""
    d, path = doc_svc.open_for_download(db, user, document_id)
    return FileResponse(path, media_type=d.content_type, filename=d.original_filename,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/transporter/shipments/{shipment_id}/pod-document", response_model=s.PodUploadOut, status_code=201, tags=["documents"])
async def upload_pod_document(shipment_id: str, request: Request, filename: str = Query(..., min_length=1, max_length=200),
                              recipient_name: str = Query(..., min_length=2, max_length=80),
                              user: m.User = Depends(TRANS), db: Session = Depends(get_db)):
    """Driver uploads the signed delivery document or photograph after reaching the customer gate.
    This completes the delivery (delivered time = simulation clock) and records the recipient."""
    sh = own_shipment(db, user, shipment_id)
    data = await _read_body(request)
    d = doc_svc.upload_pod(db, user, sh, data, filename, recipient_name)
    return s.PodUploadOut(document=doc_svc.doc_out(db, d), shipment=views.driver_shipment(db, sh),
                          message="Proof of delivery uploaded. The delivery is complete.")


@router.get("/customer/me/documents", response_model=list[s.CustomerDocumentOut], tags=["documents"])
def customer_documents(user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    """The customer's own current invoices and proof-of-delivery documents."""
    return doc_svc.customer_documents(db, user.customer_id)


# ============================================================================== CHAT
@router.post("/customer/me/chat", response_model=s.ChatReplyOut, tags=["chat"])
def customer_chat(body: s.ChatIn, user: m.User = Depends(CUST), db: Session = Depends(get_db)):
    """'Where is my order?' assistant. Read-only, deterministic, customer-safe data only."""
    return chat_svc.reply(db, user, body.message, body.order_id)
