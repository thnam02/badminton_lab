"""Simple sign-in for the coach workspace: one admin and one coach.

A session is a signed cookie, ``base64url(json payload).base64url(hmac)``,
HMAC-SHA256 with settings.session_secret. The frontend proxy verifies the same
format to guard /admin/* and /coach/* pages; the API checks it on every call.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "bl_session"
ROLE_ADMIN = "admin"
ROLE_COACH = "coach"
ROLES = (ROLE_ADMIN, ROLE_COACH)

_fallback_secret: str | None = None


@dataclass(frozen=True, slots=True)
class Session:
    role: str
    expires_at: int

    @property
    def name(self) -> str:
        return settings.coach_name if self.role == ROLE_COACH else "Admin"


def _secret() -> bytes:
    global _fallback_secret
    if settings.session_secret:
        return settings.session_secret.encode()
    if _fallback_secret is None:
        _fallback_secret = secrets.token_urlsafe(32)
        logger.warning(
            "SESSION_SECRET is not set; using a temporary secret. Sessions end when the "
            "server restarts and the frontend proxy cannot verify them."
        )
    return _fallback_secret.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(role: str, *, now: float | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}")
    exp = int((now if now is not None else time.time()) + settings.session_max_age_hours * 3600)
    payload = _b64(json.dumps({"role": role, "exp": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str | None, *, now: float | None = None) -> Session | None:
    if not token or token.count(".") != 1:
        return None
    payload, sig = token.split(".")
    expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    role, exp = data.get("role"), data.get("exp")
    if role not in ROLES or not isinstance(exp, int):
        return None
    if exp < (now if now is not None else time.time()):
        return None
    return Session(role=role, expires_at=exp)


def role_for_password(password: str) -> str | None:
    """Admin wins if both passwords are the same; empty passwords never match."""
    given = password.encode()
    for role, configured in ((ROLE_ADMIN, settings.admin_password), (ROLE_COACH, settings.coach_password)):
        if configured and hmac.compare_digest(given, configured.encode()):
            return role
    return None


def current_session(request: Request) -> Session | None:
    return read_token(request.cookies.get(COOKIE_NAME))


def require_signed_in(request: Request) -> Session:
    session = current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return session


def require_admin(request: Request) -> Session:
    session = require_signed_in(request)
    if session.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Only the admin can do this.")
    return session


def require_coach(request: Request) -> Session:
    session = require_signed_in(request)
    if session.role != ROLE_COACH:
        raise HTTPException(status_code=403, detail="Only the coach can label clips.")
    return session
