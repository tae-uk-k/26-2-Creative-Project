"""0단계: /api/health와 공통 의존성(세션·CSRF) 확인."""

import httpx
from fastapi import Depends

from seelo.api.deps import load_session, verify_csrf
from seelo.main import create_app
from seelo.security.csrf import CSRF_COOKIE, CSRF_HEADER, new_csrf_value


async def test_health_ok(api: httpx.AsyncClient) -> None:
    r = await api.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}
    assert r.headers.get("X-Request-Id")


def _app_with_echo():
    app = create_app(with_queue=False)

    @app.post("/api/_echo", dependencies=[Depends(load_session), Depends(verify_csrf)])
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_post_without_csrf_is_rejected(db) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app_with_echo()), base_url="http://test"
    ) as c:
        r = await c.post("/api/_echo")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


async def test_post_with_matching_signed_csrf_passes(db) -> None:
    value = new_csrf_value()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app_with_echo()),
        base_url="http://test",
        cookies={CSRF_COOKIE: value},
    ) as c:
        r = await c.post("/api/_echo", headers={CSRF_HEADER: value})
    assert r.status_code == 200, r.text


async def test_post_with_forged_csrf_is_rejected(db) -> None:
    forged = "abc.0123456789abcdef0123456789abcdef"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app_with_echo()),
        base_url="http://test",
        cookies={CSRF_COOKIE: forged},
    ) as c:
        r = await c.post("/api/_echo", headers={CSRF_HEADER: forged})
    assert r.status_code == 403
