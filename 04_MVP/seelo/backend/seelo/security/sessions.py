"""서버 세션(05 2장, 13 8장). 세션 생성·삭제. 커밋은 부르는 쪽이 한다."""

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from seelo.config import get_settings
from seelo.models.user import Session as SessionRow
from seelo.models.user import User
from seelo.security.csrf import CSRF_COOKIE, new_csrf_value, set_csrf_cookie
from seelo.security.tokens import hash_token, new_token
from seelo.timeutil import now_utc

SESSION_COOKIE = "seelo_session"


async def create_session(db: AsyncSession, user: User, response: Response) -> SessionRow:
    """세션 행을 추가하고(커밋 안 함) 세션·CSRF 쿠키를 응답에 단다."""
    s = get_settings()
    token, csrf = new_token(), new_csrf_value()
    row = SessionRow(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf),
        expires_at=now_utc() + timedelta(days=s.session_ttl_days),
    )
    db.add(row)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=s.session_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    set_csrf_cookie(response, csrf)
    return row


async def delete_sessions(db: AsyncSession, user_id: int, *, except_id: int | None = None) -> None:
    stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
    if except_id is not None:
        stmt = stmt.where(SessionRow.id != except_id)
    await db.execute(stmt)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
