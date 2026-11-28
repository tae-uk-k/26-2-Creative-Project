"""W-01-4 로그인·잠금·세션·CSRF(05 2·3·6장, 11 4장)."""

from datetime import timedelta
from typing import Any

import httpx
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.models.user import Session as SessionRow
from seelo.models.user import User
from seelo.timeutil import now_utc
from tests.support import PW, build_client, login, make_user, raw_request


def _app(c: httpx.AsyncClient) -> Any:
    return c._transport.app  # type: ignore[attr-defined]


async def _user(db: AsyncSession, email: str) -> User:
    db.expire_all()
    return await db.scalar(select(User).where(User.email == email))


async def test_five_failures_lock_for_ten_minutes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "lock@seelo.test")
    for i in range(4):
        r = await login(client, "lock@seelo.test", "wrongpass1")
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS", i
    r = await login(client, "lock@seelo.test", "wrongpass1")
    assert r.status_code == 423
    err = r.json()["error"]
    assert err["code"] == "ACCOUNT_LOCKED" and err["details"]["lockedUntil"].endswith("Z")
    user = await _user(db, "lock@seelo.test")
    assert user.failed_login_count == 0 and user.locked_until is not None

    r = await login(client, "lock@seelo.test", PW)  # 잠긴 동안은 맞는 비밀번호도 423
    assert r.status_code == 423
    with time_machine.travel(now_utc() + timedelta(minutes=9, seconds=50), tick=True):
        assert (await login(client, "lock@seelo.test", PW)).status_code == 423
    with time_machine.travel(now_utc() + timedelta(minutes=10, seconds=1), tick=True):
        r = await login(client, "lock@seelo.test", PW)
        assert r.status_code == 200
    user = await _user(db, "lock@seelo.test")
    assert user.failed_login_count == 0 and user.locked_until is None


async def test_success_resets_failure_count(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "a@seelo.test")
    for _ in range(3):
        await login(client, "a@seelo.test", "wrongpass1")
    assert (await _user(db, "a@seelo.test")).failed_login_count == 3
    r = await login(client, "a@seelo.test", PW)
    assert r.status_code == 200
    assert r.json()["user"] == {
        "id": r.json()["user"]["id"],
        "email": "a@seelo.test",
        "role": "owner",
        "provider": "email",
        "hasStore": False,
    }
    assert (await _user(db, "a@seelo.test")).failed_login_count == 0


async def test_login_errors(client: httpx.AsyncClient, db: AsyncSession) -> None:
    r = await login(client, "nobody@seelo.test")
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"

    await make_user(db, "g@seelo.test", password=None, provider="google", provider_user_id="g-1")
    r = await login(client, "g@seelo.test")
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "SOCIAL_ACCOUNT",
        "message": "이 이메일은 구글로 가입되어 있어요",
        "details": {"provider": "google"},
    }

    await make_user(db, "u@seelo.test", verified=False)
    r = await login(client, "u@seelo.test")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert r.json()["error"]["details"] == {"email": "u@seelo.test"}
    r = await login(client, "u@seelo.test", "wrongpass1")  # 틀린 비밀번호면 인증 여부를 알리지 않는다
    assert r.status_code == 401


async def test_session_cookie_attributes_and_hash_only(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "c@seelo.test")
    r = await login(client, "c@seelo.test")
    cookies = r.headers.get_list("set-cookie")
    session = next(h for h in cookies if h.startswith("seelo_session="))
    csrf = next(h for h in cookies if h.startswith("seelo_csrf="))
    assert "HttpOnly" in session and "samesite=lax" in session.lower() and "Path=/" in session
    assert f"Max-Age={14 * 86400}" in session
    assert "Secure" not in session  # COOKIE_SECURE=false(개발·테스트)
    assert "HttpOnly" not in csrf
    raw = client.cookies["seelo_session"]
    hashes = (await db.scalars(select(SessionRow.token_hash))).all()
    assert len(hashes) == 1 and raw not in hashes[0] and len(hashes[0]) == 64


async def test_secure_cookie_when_configured(make_client: Any, db: AsyncSession, monkeypatch: Any) -> None:
    from seelo.main import create_app

    await make_user(db, "s@seelo.test")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        c = build_client(create_app(with_queue=False))
        await c.get("/api/auth/csrf")
        # Secure 쿠키는 http 클라이언트가 저장하지 않으므로 헤더로 직접 넣는다
        csrf = c.cookies.get("seelo_csrf") or ""
        r = await c.post(
            "/api/auth/login",
            json={"email": "s@seelo.test", "password": PW},
            headers={"X-CSRF-Token": csrf},
        )
        set_cookies = r.headers.get_list("set-cookie")
        assert all("Secure" in h for h in set_cookies if h.startswith(("seelo_session=", "seelo_csrf=")))
        await c.aclose()
    finally:
        monkeypatch.delenv("COOKIE_SECURE")
        get_settings.cache_clear()


async def test_logout_removes_session_and_blocks_api(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "o@seelo.test")
    await login(client, "o@seelo.test")
    assert (await client.get("/api/auth/me")).status_code == 200
    stolen = client.cookies["seelo_session"]
    r = await client.post("/api/auth/logout")
    assert r.status_code == 204
    assert await db.scalar(select(func.count()).select_from(SessionRow)) == 0
    assert (await client.get("/api/auth/me")).status_code == 401
    # 지운 세션 값을 다시 써도 안 된다
    r = await raw_request(_app(client), "GET", "/api/auth/me", cookies={"seelo_session": stolen})
    assert r.status_code == 401


async def test_csrf_missing_or_different_is_403(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "x@seelo.test")
    await login(client, "x@seelo.test")
    r = await client.post("/api/auth/logout", headers={"X-CSRF-Token": ""})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    r = await client.post("/api/auth/logout", headers={"X-CSRF-Token": "abc.def"})
    assert r.status_code == 403
    # 로그인 전에 받은(세션에 묶이지 않은) 서명 값은 로그인 뒤에 쓸 수 없다
    anon = build_client(_app(client))
    await anon.get("/api/auth/csrf")
    old = anon.cookies["seelo_csrf"]
    await anon.aclose()
    r = await raw_request(
        _app(client),
        "POST",
        "/api/auth/logout",
        cookies={"seelo_session": client.cookies["seelo_session"], "seelo_csrf": old},
        headers={"X-CSRF-Token": old},
    )
    assert r.status_code == 403
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_csrf_endpoint_keeps_session_bound_value(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "k@seelo.test")
    await login(client, "k@seelo.test")
    bound = client.cookies["seelo_csrf"]
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 204 and "set-cookie" not in r.headers
    assert client.cookies["seelo_csrf"] == bound
    # 쿠키를 잃었으면 새 값을 세션에 다시 묶는다
    client.cookies.delete("seelo_csrf")
    r = await client.get("/api/auth/csrf")
    assert client.cookies["seelo_csrf"] != bound
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_expired_session_is_401(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "e@seelo.test")
    await login(client, "e@seelo.test")
    raw = client.cookies["seelo_session"]
    with time_machine.travel(now_utc() + timedelta(days=14, seconds=1), tick=True):
        # 브라우저는 Max-Age가 지나면 쿠키를 버린다. 서버도 만료 세션을 거부하고 지우는지
        # 쿠키를 직접 실어 본다
        r = await raw_request(_app(client), "GET", "/api/auth/me", cookies={"seelo_session": raw})
    assert r.status_code == 401
    assert await db.scalar(select(func.count()).select_from(SessionRow)) == 0
