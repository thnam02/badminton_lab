"""Sign in / out for the coach workspace."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth import COOKIE_NAME, create_token, current_session, role_for_password
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# Slows down password guessing a little.
FAILED_LOGIN_DELAY_S = 0.5


class LoginIn(BaseModel):
    password: str


def _who(role: str) -> dict:
    return {"role": role, "name": settings.coach_name if role == "coach" else "Admin"}


@router.post("/login")
async def login(body: LoginIn, response: Response) -> dict:
    role = role_for_password(body.password)
    if role is None:
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)
        raise HTTPException(status_code=401, detail="That password isn't right.")
    response.set_cookie(
        COOKIE_NAME,
        create_token(role),
        max_age=settings.session_max_age_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return _who(role)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    session = current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return _who(session.role)
