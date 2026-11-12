"""Invoice and proof-of-delivery documents (bonus feature).

Security model
- Files live in PRIVATE storage (config.DOC_DIR) under generated names; nothing is served as a static file.
- The only way to read a file is GET /api/documents/{id}/download, which checks the caller's role and ownership.
- The file type is decided from the file CONTENT (magic bytes), never from the client's filename or MIME type.
- Display filenames are sanitised; stored names are random hex, so a path can never be influenced by the user.
- Every upload, replacement, verification and download is written to the append-only audit log.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import threading
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from .. import schemas as s
from . import alerts as alert_svc
from .core import audit, sim_now

ALLOWED = {
    "pdf": ("application/pdf", (b"%PDF-",)),
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
}
_lock = threading.Lock()


def detect_type(data: bytes) -> Optional[str]:
    """Return 'pdf' | 'png' | 'jpg' from the file's first bytes, or None if it is not an allowed type."""
    for ext, (_ctype, magics) in ALLOWED.items():
        if ext != "jpeg" and any(data.startswith(mg) for mg in magics):
            return ext
    return None


def safe_filename(name: str) -> str:
    """Display name only: no directories, no control characters, no odd symbols, bounded length."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^A-Za-z0-9._() -]", "_", base).strip(" .") or "document"
    return base[:80]


def validate_upload(data: bytes, filename: str) -> tuple[str, str, str]:
    """Return (extension, content_type, safe_display_name). Raises 4xx with a clear reason."""
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"The file is larger than the {config.MAX_UPLOAD_MB:g} MB limit.")
    detected = detect_type(data)
    if detected is None:
        raise HTTPException(415, "Unsupported or damaged file. Upload a PDF, JPG, JPEG or PNG.")
    name = safe_filename(filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise HTTPException(415, "The filename must end in .pdf, .jpg, .jpeg or .png.")
    if ALLOWED[ext][0] != ALLOWED[detected][0]:
        raise HTTPException(415, f"The file content is {detected.upper()} but the name says .{ext}. Rename it or upload the right file.")
    return detected, ALLOWED[detected][0], name


def _path_for(stored_name: str) -> Path:
    root = config.DOC_DIR.resolve()
    p = (root / stored_name).resolve()
    if p.parent != root:                                         # defence in depth: no path can escape the folder
        raise HTTPException(404, "Document not found")
    return p


def _store(data: bytes, ext: str) -> str:
    config.DOC_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{ext}"
    tmp = _path_for(name + ".part")
    tmp.write_bytes(data)
    tmp.replace(_path_for(name))
    return name


def purge_storage() -> None:
    """Remove every stored file (used when the demo data is reset)."""
    if config.DOC_DIR.exists():
        shutil.rmtree(config.DOC_DIR, ignore_errors=True)


# ------------------------------------------------------------------------------------------- views
def _names(db: Session, ids) -> dict[int, tuple[str, str]]:
    return {u.id: (u.display_name, u.role) for u in db.query(m.User).filter(m.User.id.in_([i for i in ids if i]))}


def doc_out(db: Session, d: m.Document, names: Optional[dict] = None) -> s.DocumentOut:
    names = names or _names(db, [d.uploaded_by, d.verified_by])
    return s.DocumentOut(
        id=d.id, kind=d.kind, order_id=d.order_id, shipment_id=d.shipment_id, version=d.version,
        is_current=d.is_current, status=d.status, original_filename=d.original_filename,
        content_type=d.content_type, size_bytes=d.size_bytes, sha256=d.sha256, invoice_number=d.invoice_number,
        recipient_name=d.recipient_name, uploaded_by_name=names.get(d.uploaded_by, ("System", "SYSTEM"))[0],
        uploaded_by_role=names.get(d.uploaded_by, ("System", "SYSTEM"))[1], uploaded_sim_at=d.uploaded_sim_at,
        delivered_sim_at=d.delivered_sim_at, replace_reason=d.replace_reason,
        verified_by_name=names.get(d.verified_by, (None, None))[0] if d.verified_by else None,
        verified_sim_at=d.verified_sim_at)


def order_documents(db: Session, order_id: str) -> s.OrderDocumentsOut:
    from .shipments import LABEL
    order = db.get(m.Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    docs = db.query(m.Document).filter(m.Document.order_id == order_id).order_by(m.Document.id.desc()).all()
    names = _names(db, [d.uploaded_by for d in docs] + [d.verified_by for d in docs])
    ships = (db.query(m.Shipment).filter(m.Shipment.order_id == order_id, m.Shipment.disposition == "ACTIVE")
             .order_by(m.Shipment.id).all())
    rows = []
    for sh in ships:
        mine = [d for d in docs if d.kind == "POD" and d.shipment_id == sh.id]
        cur = next((d for d in mine if d.is_current), None)
        if sh.state != "DELIVERED" and cur is None:
            status = "NOT_DELIVERED" if sh.state != "ARRIVED_AT_CUSTOMER_GATE" else "AWAITING_POD"
        elif cur is None:
            status = "NO_DOCUMENT"
        else:
            status = "VERIFIED" if cur.status == "VERIFIED" else "UPLOADED"
        rows.append(s.ShipmentDocsOut(shipment_id=sh.id, state=sh.state, state_label=LABEL[sh.state],
                                      lot_type=sh.lot_type, quantity_tonnes=sh.quantity_tonnes, pod_status=status,
                                      recipient_name=sh.pod_recipient, delivered_at=sh.delivered_at,
                                      documents=[doc_out(db, d, names) for d in mine]))
    return s.OrderDocumentsOut(order_id=order_id, customer_name=db.get(m.Customer, order.customer_id).name,
                               invoices=[doc_out(db, d, names) for d in docs if d.kind == "INVOICE"], shipments=rows)


def overview(db: Session) -> list[s.DocumentsOverviewRow]:
    orders = (db.query(m.Order).join(m.Shipment, m.Shipment.order_id == m.Order.id)
              .filter(m.Shipment.is_historical.is_(False)).order_by(m.Order.id).distinct().all())
    out = []
    for o in orders:
        inv = db.query(m.Document).filter(m.Document.order_id == o.id, m.Document.kind == "INVOICE",
                                          m.Document.is_current.is_(True)).first()
        pods = db.query(m.Document).filter(m.Document.order_id == o.id, m.Document.kind == "POD",
                                           m.Document.is_current.is_(True)).all()
        ships = db.query(m.Shipment).filter(m.Shipment.order_id == o.id, m.Shipment.disposition == "ACTIVE").all()
        delivered = [x for x in ships if x.state == "DELIVERED"]
        out.append(s.DocumentsOverviewRow(
            order_id=o.id, customer_name=db.get(m.Customer, o.customer_id).name, product_code=o.product_code,
            quantity_tonnes=o.quantity_tonnes, shipment_ids=[x.id for x in ships],
            shipment_states=sorted({x.state for x in ships}), invoice=doc_out(db, inv) if inv else None,
            pods_expected=len(ships), pods_delivered=len(delivered), pods_uploaded=len(pods),
            pods_verified=sum(1 for p in pods if p.status == "VERIFIED")))
    return out


def customer_documents(db: Session, customer_id: str) -> list[s.CustomerDocumentOut]:
    """Only CURRENT documents of the customer's own orders, with an allow-list of fields."""
    rows = (db.query(m.Document).join(m.Order, m.Order.id == m.Document.order_id)
            .filter(m.Order.customer_id == customer_id, m.Document.is_current.is_(True))
            .order_by(m.Document.uploaded_sim_at.desc(), m.Document.id.desc()).all())
    return [s.CustomerDocumentOut(
        id=d.id, kind=d.kind, order_id=d.order_id, shipment_id=d.shipment_id, filename=d.original_filename,
        content_type=d.content_type, size_bytes=d.size_bytes, uploaded_at=d.uploaded_sim_at,
        status="Available", invoice_number=d.invoice_number,
        recipient_name=d.recipient_name, delivered_at=d.delivered_sim_at) for d in rows]


# -------------------------------------------------------------------------------------- operations
def upload_invoice(db: Session, user: m.User, order_id: str, data: bytes, filename: str,
                   invoice_number: Optional[str], reason: Optional[str]) -> m.Document:
    ext, ctype, name = validate_upload(data, filename)
    order = db.get(m.Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    now = sim_now(db)
    with _lock:
        cur = db.query(m.Document).filter(m.Document.order_id == order_id, m.Document.kind == "INVOICE",
                                          m.Document.is_current.is_(True)).first()
        why = (reason or "").strip()
        if cur is not None and len(why) < 5:
            raise HTTPException(409, "This order already has an invoice. To replace it, give a reason (at least 5 characters).")
        stored = _store(data, ext)
        try:
            number = (invoice_number or "").strip()[:40] or (cur.invoice_number if cur else None) or f"INV-{order_id[4:]}"
            d = m.Document(kind="INVOICE", order_id=order_id, version=(cur.version + 1) if cur else 1, is_current=True,
                           status="ISSUED", original_filename=name, stored_name=stored, content_type=ctype,
                           size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), invoice_number=number,
                           uploaded_by=user.id, uploaded_sim_at=now, replaces_document_id=cur.id if cur else None,
                           replace_reason=why or None)
            if cur is not None:
                cur.is_current, cur.status = False, "SUPERSEDED"
                db.flush()
            db.add(d)
            db.flush()
            audit(db, user, "DOCUMENT_REPLACED" if cur else "DOCUMENT_UPLOADED", "document", d.id,
                  before={"replaces": cur.id, "version": cur.version} if cur else None,
                  after={"kind": "INVOICE", "order_id": order_id, "version": d.version, "filename": name,
                         "size_bytes": len(data), "sha256": d.sha256, "reason": why or None})
            alert_svc.create(
                db, audience_role="CUSTOMER", customer_id=order.customer_id, shipment=None, order=order, kind="DOCUMENT",
                severity="INFO", title=f"Invoice {'updated' if cur else 'available'} for order {order_id}",
                message=("A corrected invoice is now available." if cur else "Your invoice is now available.")
                + " You can download it from the Documents tab.", suggested_action="",
                data={}, dedupe_key=f"DOC|{d.id}|CUSTOMER", now=now)
            db.commit()
        except Exception:
            _path_for(stored).unlink(missing_ok=True)
            raise
        return d


def upload_pod(db: Session, user: m.User, sh: m.Shipment, data: bytes, filename: str, recipient: str) -> m.Document:
    """Proof of delivery (by the driver, or by the coordinator on the driver's behalf). Allowed once the vehicle is at the customer gate (this completes the delivery) or
    after it (replace the document). The delivery timestamp comes from the simulation clock."""
    ext, ctype, name = validate_upload(data, filename)
    recipient = (recipient or "").strip()
    if len(recipient) < 2 or len(recipient) > 80:
        raise HTTPException(422, "Enter the name of the person who received the delivery.")
    if sh.disposition != "ACTIVE" or sh.state not in ("ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"):
        raise HTTPException(409, "Proof of delivery can only be uploaded after the vehicle has reached the customer gate.")
    now = sim_now(db)
    order = db.get(m.Order, sh.order_id)
    with _lock:
        cur = db.query(m.Document).filter(m.Document.shipment_id == sh.id, m.Document.kind == "POD",
                                          m.Document.is_current.is_(True)).first()
        stored = _store(data, ext)
        try:
            if sh.state == "ARRIVED_AT_CUSTOMER_GATE":
                from .shipments import advance_state
                sh.pod_recipient = recipient
                advance_state(db, sh, "DELIVERED", now, "DRIVER" if user.role == "TRANSPORTER" else "COORDINATOR", user,
                              note=f"Proof of delivery signed by {recipient}" + ("" if user.role == "TRANSPORTER" else " (uploaded by the control tower)"))
            else:
                sh.pod_recipient = recipient
            d = m.Document(kind="POD", order_id=order.id, shipment_id=sh.id, version=(cur.version + 1) if cur else 1,
                           is_current=True, status="UPLOADED", original_filename=name, stored_name=stored,
                           content_type=ctype, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                           recipient_name=recipient, uploaded_by=user.id, uploaded_sim_at=now,
                           delivered_sim_at=sh.delivered_at or now, replaces_document_id=cur.id if cur else None,
                           replace_reason=("Replaced by the driver" if user.role == "TRANSPORTER" else "Replaced by the control tower") if cur else None)
            if cur is not None:
                cur.is_current, cur.status = False, "SUPERSEDED"
                db.flush()
            db.add(d)
            db.flush()
            audit(db, user, "POD_DOCUMENT_UPLOADED", "document", d.id,
                  before={"replaces": cur.id} if cur else None,
                  after={"kind": "POD", "order_id": order.id, "shipment_id": sh.id, "version": d.version, "filename": name,
                         "recipient": recipient, "delivered_sim_at": d.delivered_sim_at.isoformat(), "size_bytes": len(data)})
            alert_svc.create(
                db, audience_role="CUSTOMER", customer_id=order.customer_id, shipment=sh, order=order, kind="DOCUMENT",
                severity="INFO", title=f"Proof of delivery available for order {order.id}",
                message="The signed proof of delivery is now available. You can download it from the Documents tab.",
                suggested_action="", data={}, dedupe_key=f"DOC|{d.id}|CUSTOMER", now=now)
            db.commit()
        except Exception:
            _path_for(stored).unlink(missing_ok=True)
            raise
        return d


def verify_pod(db: Session, user: m.User, doc_id: int) -> m.Document:
    d = db.get(m.Document, doc_id)
    if d is None or d.kind != "POD":
        raise HTTPException(404, "Document not found")
    if not d.is_current:
        raise HTTPException(409, "Only the current proof of delivery can be verified.")
    sh = db.get(m.Shipment, d.shipment_id)
    if sh is None or sh.order_id != d.order_id:
        raise HTTPException(409, "This document is not associated with its shipment's order.")
    if d.status != "VERIFIED":
        d.status, d.verified_by, d.verified_sim_at = "VERIFIED", user.id, sim_now(db)
        audit(db, user, "POD_VERIFIED", "document", d.id,
              after={"shipment_id": d.shipment_id, "order_id": d.order_id, "recipient": d.recipient_name})
        db.commit()
    return d


def open_for_download(db: Session, user: m.User, doc_id: int) -> tuple[m.Document, Path]:
    """Ownership check on EVERY download. Wrong role or someone else's document -> 404 (never 403, so nothing leaks)."""
    d = db.get(m.Document, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    if user.role == "CUSTOMER":
        order = db.get(m.Order, d.order_id)
        if order is None or order.customer_id != user.customer_id or not d.is_current:
            raise HTTPException(404, "Document not found")
    elif user.role == "TRANSPORTER":
        sh = db.get(m.Shipment, d.shipment_id) if d.shipment_id else None
        if d.kind != "POD" or sh is None or sh.driver_user_id != user.id:
            raise HTTPException(404, "Document not found")
    path = _path_for(d.stored_name)
    if not path.is_file():
        raise HTTPException(404, "The stored file is missing")
    audit(db, user, "DOCUMENT_DOWNLOADED", "document", d.id,
          after={"kind": d.kind, "order_id": d.order_id, "shipment_id": d.shipment_id, "version": d.version})
    db.commit()
    return d, path
