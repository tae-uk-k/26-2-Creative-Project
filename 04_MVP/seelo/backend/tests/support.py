"""통합 테스트 도우미(11 2장).

CSRF를 자동으로 붙이는 클라이언트, 메일 토큰 읽기, 로그 수집, DB 텍스트 덤프.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import LogCapture

from seelo.models.ops import EmailLog
from seelo.models.user import AuthIdentity, User
from seelo.security.crypto import decrypt_json
from seelo.security.csrf import CSRF_COOKIE, CSRF_HEADER
from seelo.security.passwords import hash_password
from seelo.timeutil import now_utc

PW = "testpass123"  # 테스트 전용 값
NEW_PW = "newpass4567"

_PW_HASH: dict[str, str] = {}


def build_client(app: Any) -> httpx.AsyncClient:
    """화면처럼 동작하는 클라이언트: 상태를 바꾸는 요청에 seelo_csrf 쿠키 값을 헤더로 붙인다."""
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def add_csrf(request: httpx.Request) -> None:
        if request.method not in ("GET", "HEAD", "OPTIONS") and CSRF_HEADER not in request.headers:
            value = client.cookies.get(CSRF_COOKIE)
            if value:
                request.headers[CSRF_HEADER] = value

    client.event_hooks["request"] = [add_csrf]
    return client


async def raw_request(
    app: Any, method: str, path: str, *, cookies: dict[str, str], headers: dict[str, str] | None = None
) -> httpx.Response:
    """쿠키 저장소 없이 정한 쿠키만 실어 보낸다(훔친·만료된 쿠키 재사용 시험용)."""
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, path, headers={**(headers or {}), "Cookie": cookie_header})


async def mail_secret(db: AsyncSession, type_: str, to: str | None = None) -> dict[str, Any]:
    """가장 최근 메일의 비밀 값(링크 토큰). 발송 전이라 아직 암호문이 남아 있다."""
    stmt = select(EmailLog).where(EmailLog.type == type_)
    if to is not None:
        stmt = stmt.where(EmailLog.to_email == to)
    db.expire_all()
    row = await db.scalar(stmt.order_by(EmailLog.id.desc()).limit(1))
    assert row is not None and row.secret_payload is not None, f"{type_} 메일이 없다"
    return decrypt_json(row.secret_payload)


async def signup(c: httpx.AsyncClient, email: str, pw: str = PW) -> httpx.Response:
    return await c.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": pw,
            "passwordConfirm": pw,
            "agreeTerms": True,
            "agreePrivacy": True,
        },
    )


async def signup_verified(c: httpx.AsyncClient, db: AsyncSession, email: str, pw: str = PW) -> dict[str, Any]:
    """API로 가입하고 메일 링크로 인증까지 마친다(로그인 상태가 된다)."""
    r = await signup(c, email, pw)
    assert r.status_code == 201, r.text
    token = (await mail_secret(db, "verify_email", email))["token"]
    r = await c.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    return r.json()["user"]


async def make_user(
    db: AsyncSession,
    email: str,
    *,
    password: str | None = PW,
    verified: bool = True,
    provider: str = "email",
    provider_user_id: str | None = None,
) -> User:
    """DB에 바로 사용자를 만든다(API 흐름이 필요 없는 테스트용). 커밋한다."""
    pw_hash = None
    if password is not None:
        pw_hash = _PW_HASH.get(password) or _PW_HASH.setdefault(password, hash_password(password))
    now = now_utc()
    user = User(
        email=email,
        password_hash=pw_hash,
        email_verified_at=now if verified else None,
        terms_agreed_at=now,
    )
    db.add(user)
    await db.flush()
    db.add(AuthIdentity(user_id=user.id, provider=provider, provider_user_id=provider_user_id))
    await db.commit()
    return user


async def login(c: httpx.AsyncClient, email: str, pw: str = PW) -> httpx.Response:
    return await c.post("/api/auth/login", json={"email": email, "password": pw})


def location(r: httpx.Response) -> tuple[str, dict[str, str]]:
    """리디렉션 경로와 쿼리."""
    assert r.status_code == 302, r.text
    parts = urlsplit(r.headers["location"])
    return parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}


async def dump_db_text(db: AsyncSession) -> str:
    """모든 테이블(작업 큐 포함)의 모든 행을 JSON 텍스트로(pg_dump --data-only 대신)."""
    tables = [
        r[0] for r in await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    ]
    out = []
    for t in tables:
        rows = await db.execute(text(f"SELECT row_to_json(x)::text FROM {t} x"))
        out.extend(r[0] for r in rows)
    return "\n".join(out)


@contextmanager
def capture_all_logs() -> Iterator[list[dict[str, Any]]]:
    """DEBUG까지 모든 구조화 로그를 가림 처리 전 원본으로 모은다(가림 처리기에 기대지 않는 검사)."""
    old = structlog.get_config()
    cap = LogCapture()
    structlog.configure(
        processors=[cap],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        cache_logger_on_first_use=False,
    )
    try:
        yield cap.entries
    finally:
        structlog.configure(**old)
