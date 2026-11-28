"""공통 의존성(05 2·3·11장, 13 7장). 순서: load_session → verify_csrf → require_user."""

import hmac
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import get_db
from seelo.errors import AppError
from seelo.models.user import Session as SessionRow
from seelo.models.user import User
from seelo.security.csrf import CSRF_COOKIE, CSRF_HEADER, verify_signature
from seelo.security.sessions import SESSION_COOKIE
from seelo.security.tokens import hash_token
from seelo.timeutil import now_utc

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LAST_SEEN_REFRESH = timedelta(minutes=5)


async def load_session(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """모든 /api 요청의 첫 의존성. request.state.user·session_row를 채운다(없으면 None)."""
    request.state.user = None
    request.state.session_row = None
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return
    row = await db.scalar(select(SessionRow).where(SessionRow.token_hash == hash_token(token)))
    if row is None:
        return
    now = now_utc()
    if row.expires_at <= now:
        await db.delete(row)
        await db.commit()
        return
    user = await db.get(User, row.user_id)
    if user is None or user.email_verified_at is None:
        return
    if row.last_seen_at < now - LAST_SEEN_REFRESH:
        row.last_seen_at = now
        await db.commit()
    request.state.user = user
    request.state.session_row = row


async def verify_csrf(request: Request) -> None:
    """상태를 바꾸는 요청은 X-CSRF-Token == seelo_csrf 쿠키, 서명 일치, 세션 묶임을 확인한다."""
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER)
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or not hmac.compare_digest(header, cookie) or not verify_signature(cookie):
        raise AppError("CSRF_FAILED")
    row: SessionRow | None = getattr(request.state, "session_row", None)
    if row is not None and not hmac.compare_digest(hash_token(cookie), row.csrf_token_hash):
        raise AppError("CSRF_FAILED")


def require_user(request: Request) -> User:
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        raise AppError("AUTH_REQUIRED")
    if user.terms_agreed_at is None:
        raise AppError("TERMS_REQUIRED")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise AppError("FORBIDDEN")
    return user
