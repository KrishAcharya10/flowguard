"""Authentication and central authorisation (spec 4.16).

Argon2 (argon2-cffi) password hashes; JWT HS256, 60-minute expiry, secret from the
environment. Role and active flag are re-read from the database on EVERY request.
Wrong role -> 403. Someone else's resource -> 404 (never reveal that it exists).

Note: token expiry and the login throttle use the wall clock. They are security
plumbing, not business logic; all business time comes from simulation_state.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from . import models as m
from .db import get_db

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
_failures: dict[tuple[str, str], deque] = defaultdict(deque)
THROTTLE_MAX, THROTTLE_WINDOW_S = 5, 60.0


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def make_token(user: m.User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": exp}, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def throttle_check(username: str, ip: str) -> None:
    q = _failures[(username.lower(), ip)]
    cutoff = time.monotonic() - THROTTLE_WINDOW_S
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= THROTTLE_MAX:
        raise HTTPException(429, "Too many failed logins. Try again in a minute.")


def throttle_fail(username: str, ip: str) -> None:
    _failures[(username.lower(), ip)].append(time.monotonic())


def throttle_clear() -> None:
    _failures.clear()


def current_user(request: Request, cred: HTTPAuthorizationCredentials = Depends(_bearer),
                 db: Session = Depends(get_db)) -> m.User:
    if cred is None:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        uid = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(m.User, uid)                 # role + active flag re-read on every request
    if user is None or not user.is_active:
        raise HTTPException(401, "User is not active")
    return user


def roles(*allowed: str):
    """The one central role check. Usage: user = Depends(roles('COORDINATOR'))."""
    def dep(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in allowed:
            raise HTTPException(403, "Your role cannot use this endpoint")
        return user
    dep.allowed_roles = allowed
    return dep


COORD = roles("COORDINATOR")
CUST = roles("CUSTOMER")
TRANS = roles("TRANSPORTER")
ANY = roles("COORDINATOR", "CUSTOMER", "TRANSPORTER")


def own_shipment(db: Session, user: m.User, shipment_id: str) -> m.Shipment:
    """Central ownership check: another user's shipment returns 404, not 403."""
    sh = db.get(m.Shipment, shipment_id)
    if sh is None:
        raise HTTPException(404, "Shipment not found")
    if user.role == "COORDINATOR":
        return sh
    if user.role == "CUSTOMER":
        order = db.get(m.Order, sh.order_id)
        if order.customer_id != user.customer_id or sh.is_historical:
            raise HTTPException(404, "Shipment not found")
        return sh
    if sh.driver_user_id != user.id or sh.is_historical:
        raise HTTPException(404, "Shipment not found")
    return sh
