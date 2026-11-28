"""2단계: 세션(05 2장)·CSRF 세션 묶기(05 3장)·요청 제한(05 10장)."""

import httpx
import pytest
from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from seelo.api.deps import load_session, require_user, verify_csrf
from seelo.errors import AppError
from seelo.main import create_app
from seelo.models.user import Session as SessionRow
from seelo.models.user import User
from seelo.security import ratelimit
from seelo.security.csrf import CSRF_COOKIE, CSRF_HEADER, new_csrf_value
from seelo.security.sessions import SESSION_COOKIE, create_session, delete_sessions
from seelo.timeutil import now_utc


async def _user(db: AsyncSession, email: str = "s@seelo.test") -> User:
    u = User(email=email, email_verified_at=now_utc(), terms_agreed_at=now_utc())
    db.add(u)
    await db.flush()
    return u


def _cookies(resp: Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in resp.raw_headers:
        if k == b"set-cookie":
            name, _, rest = v.decode().partition("=")
            out[name] = rest.split(";", 1)[0]
    return out


def _app() -> object:
    app = create_app(with_queue=False)
    deps = [Depends(load_session), Depends(verify_csrf)]

    @app.get("/api/_me", dependencies=deps)
    async def me(request: Request) -> dict[str, int]:
        return {"id": require_user(request).id}

    @app.post("/api/_write", dependencies=deps)
    async def write() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_create_session_sets_cookies_and_stores_hash_only(db: AsyncSession) -> None:
    user = await _user(db)
    resp = Response()
    row = await create_session(db, user, resp)
    await db.commit()

    headers = [v.decode() for k, v in resp.raw_headers if k == b"set-cookie"]
    session_header = next(h for h in headers if h.startswith(SESSION_COOKIE + "="))
    csrf_header = next(h for h in headers if h.startswith(CSRF_COOKIE + "="))
    assert "HttpOnly" in session_header and "samesite=lax" in session_header.lower()
    assert "HttpOnly" not in csrf_header  # 화면 코드가 읽어 헤더에 넣는다

    cookies = _cookies(resp)
    assert row.token_hash != cookies[SESSION_COOKIE]
    stored = (await db.execute(select(SessionRow.token_hash, SessionRow.csrf_token_hash))).all()
    for token_hash, csrf_hash in stored:
        assert cookies[SESSION_COOKIE] not in (token_hash, csrf_hash)
        assert cookies[CSRF_COOKIE] not in (token_hash, csrf_hash)


async def test_session_cookie_authenticates_and_csrf_is_bound(db: AsyncSession) -> None:
    user = await _user(db)
    resp = Response()
    await create_session(db, user, resp)
    await db.commit()
    cookies = _cookies(resp)
    transport = httpx.ASGITransport(app=_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as c:
        r = await c.get("/api/_me")
        assert r.status_code == 200 and r.json() == {"id": user.id}
        # 세션에 묶인 CSRF 값이면 통과
        r = await c.post("/api/_write", headers={CSRF_HEADER: cookies[CSRF_COOKIE]})
        assert r.status_code == 200, r.text

    # 서명은 맞지만 이 세션의 값이 아닌 CSRF → 403
    other = new_csrf_value()
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies={**cookies, CSRF_COOKIE: other}
    ) as c:
        r = await c.post("/api/_write", headers={CSRF_HEADER: other})
        assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"


async def test_no_session_is_401_and_expired_session_is_removed(db: AsyncSession) -> None:
    user = await _user(db)
    resp = Response()
    row = await create_session(db, user, resp)
    row.expires_at = now_utc()
    await db.commit()
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/_me")
        assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies=_cookies(resp)) as c:
        r = await c.get("/api/_me")
        assert r.status_code == 401
    db.expire_all()
    assert await db.scalar(select(func.count()).select_from(SessionRow)) == 0


async def test_unverified_user_session_is_ignored(db: AsyncSession) -> None:
    user = User(email="u@seelo.test", terms_agreed_at=now_utc())
    db.add(user)
    await db.flush()
    resp = Response()
    await create_session(db, user, resp)
    await db.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test", cookies=_cookies(resp)
    ) as c:
        assert (await c.get("/api/_me")).status_code == 401


async def test_delete_sessions_except_current(db: AsyncSession) -> None:
    user = await _user(db)
    rows = [await create_session(db, user, Response()) for _ in range(3)]
    await db.flush()
    keep_id = rows[0].id
    await delete_sessions(db, user.id, except_id=keep_id)
    await db.commit()
    remaining = (await db.scalars(select(SessionRow.id))).all()
    assert remaining == [keep_id]


@pytest.mark.usefixtures("frozen_time")
async def test_rate_limit_allows_five_then_429(db: AsyncSession) -> None:
    for _ in range(5):
        await ratelimit.hit(db, "signup", "203.0.113.5")
    with pytest.raises(AppError) as e:
        await ratelimit.hit(db, "signup", "203.0.113.5")
    assert e.value.code == "RATE_LIMITED"
    assert e.value.details["retryAfterSeconds"] == 50  # 10초에 멈춘 시계 → 다음 분까지 50초
    # 다른 IP·다른 종류는 따로 센다
    await ratelimit.hit(db, "signup", "198.51.100.7")
    await ratelimit.hit(db, "pwreset", "203.0.113.5")
    await db.commit()
