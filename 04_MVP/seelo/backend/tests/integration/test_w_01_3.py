"""W-01-3 구글·카카오 로그인(05 5장, 11 4장). 제공자는 가짜(FakeOAuth)로 바꾼다."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations import OAuthProfile
from seelo.models.user import AuthIdentity, PendingSignup, User
from seelo.timeutil import now_utc
from tests.support import capture_all_logs, location, mail_secret, make_user, signup

GOOGLE_OK = OAuthProfile("google", "g-1", "Same@Seelo.test", True)
GOOGLE_UNVERIFIED = OAuthProfile("google", "g-2", "u@seelo.test", False)
KAKAO_NO_EMAIL = OAuthProfile("kakao", "k-1", None, False)
KAKAO_OK = OAuthProfile("kakao", "k-3", "same@seelo.test", True)


async def oauth_login(
    c: httpx.AsyncClient, fake_oauth: Any, provider: str, profile: OAuthProfile | None, intent: str = "signup"
) -> httpx.Response:
    """start → (제공자 동의) → callback. profile이 code로 연결된다."""
    r = await c.get(f"/api/oauth/{provider}/start", params={"intent": intent})
    path, q = location(r)
    assert path == f"/api/oauth/{provider}/callback"  # 가짜는 동의 화면 없이 바로 돌아온다
    code = f"code-{provider}-{profile.provider_user_id}" if profile else q["code"]
    if profile is not None:
        fake_oauth.profiles[code] = profile
    return await c.get(path, params={"code": code, "state": q["state"]})


async def test_start_redirects_with_state(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    r = await client.get("/api/oauth/google/start", params={"intent": "login"})
    path, q = location(r)
    assert r.headers["location"].startswith("http://seelo.test/api/oauth/google/callback")
    assert len(q["state"]) >= 40 and "seelo_oauth" in client.cookies
    assert (await client.get("/api/oauth/naver/start")).status_code == 404


async def test_state_mismatch_is_oauth_failed(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    r = await client.get("/api/oauth/google/start", params={"intent": "signup"})
    _, q = location(r)
    r = await client.get("/api/oauth/google/callback", params={"code": q["code"], "state": "forged-state"})
    assert location(r) == ("/signup", {"error": "oauth_failed"})
    # 세션 쿠키 없이 바로 콜백(다른 브라우저에서 온 요청)
    other_browser = httpx.ASGITransport(app=client._transport.app)  # type: ignore[attr-defined]
    async with httpx.AsyncClient(transport=other_browser, base_url="http://test") as other:
        r = await other.get("/api/oauth/google/callback", params={"code": "x", "state": q["state"]})
    assert location(r) == ("/login", {"error": "oauth_failed"})
    assert fake_oauth.calls == []  # 토큰 교환까지 가지 않았다


async def test_state_is_single_use(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    r = await client.get("/api/oauth/google/start", params={"intent": "login"})
    _, q = location(r)
    first = await client.get("/api/oauth/google/callback", params=q)
    assert location(first)[0] == "/signup/terms"
    again = await client.get("/api/oauth/google/callback", params=q)
    assert location(again) == ("/login", {"error": "oauth_failed"})


async def test_user_cancel_is_oauth_canceled(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    r = await client.get("/api/oauth/kakao/start", params={"intent": "login"})
    _, q = location(r)
    r = await client.get(
        "/api/oauth/kakao/callback",
        params={"error": "access_denied", "error_description": "User denied access", "state": q["state"]},
    )
    assert location(r) == ("/login", {"error": "oauth_canceled"})


async def test_token_exchange_failure_is_oauth_failed(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    r = await client.get("/api/oauth/google/start", params={"intent": "signup"})
    _, q = location(r)
    r = await client.get("/api/oauth/google/callback", params={"code": "unknown-code", "state": q["state"]})
    assert location(r) == ("/signup", {"error": "oauth_failed"})


async def test_google_unverified_email_does_not_sign_up(
    client: httpx.AsyncClient, fake_oauth: Any, db: AsyncSession
) -> None:
    r = await oauth_login(client, fake_oauth, "google", GOOGLE_UNVERIFIED)
    assert location(r) == ("/signup", {"error": "oauth_failed"})
    assert await db.scalar(select(func.count()).select_from(PendingSignup)) == 0
    assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_google_signup_with_terms_then_login(
    make_client: Any, fake_oauth: Any, db: AsyncSession
) -> None:
    c = await make_client()
    r = await oauth_login(c, fake_oauth, "google", GOOGLE_OK)
    assert location(r) == ("/signup/terms", {})
    assert "seelo_pending" in c.cookies
    assert await db.scalar(select(func.count()).select_from(User)) == 0  # 약관 동의 전에는 계정 없음

    r = await c.get("/api/auth/pending-signup")
    assert r.json() == {"provider": "google", "email": "same@seelo.test", "needsEmail": False}
    r = await c.post("/api/auth/pending-signup/complete", json={"agreeTerms": True, "agreePrivacy": False})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"] == {"agreeTerms": "terms_required"}

    r = await c.post(
        "/api/auth/pending-signup/complete",
        json={"agreeTerms": True, "agreePrivacy": True, "email": "ignored@seelo.test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["next"] == "/home" and "mailTicket" not in body
    assert body["user"]["email"] == "same@seelo.test" and body["user"]["provider"] == "google"
    assert (await c.get("/api/auth/me")).status_code == 200
    assert (await c.get("/api/auth/pending-signup")).status_code == 404  # 대기 행·쿠키 삭제
    user = await db.scalar(select(User).where(User.email == "same@seelo.test"))
    assert user.password_hash is None and user.email_verified_at is not None and user.terms_agreed_at

    # 다른 브라우저에서 다시 구글 로그인 → 바로 홈
    c2 = await make_client()
    r = await oauth_login(c2, fake_oauth, "google", GOOGLE_OK, intent="login")
    assert location(r) == ("/home", {})
    assert (await c2.get("/api/auth/me")).json()["email"] == "same@seelo.test"


async def test_kakao_without_email_enters_email_then_verifies(
    make_client: Any, fake_oauth: Any, db: AsyncSession
) -> None:
    c = await make_client()
    r = await oauth_login(c, fake_oauth, "kakao", KAKAO_NO_EMAIL)
    assert location(r) == ("/signup/kakao-email", {})
    assert (await c.get("/api/auth/pending-signup")).json() == {
        "provider": "kakao",
        "email": None,
        "needsEmail": True,
    }
    r = await c.post("/api/auth/pending-signup/complete", json={"agreeTerms": True, "agreePrivacy": True})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"] == {"email": "required"}

    r = await c.post(
        "/api/auth/pending-signup/complete",
        json={"agreeTerms": True, "agreePrivacy": True, "email": "Kakao@Seelo.test"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["next"] == "/signup/sent" and body["mailTicket"] and "user" not in body
    assert (await c.get("/api/auth/me")).status_code == 401  # 메일 인증 전

    # 인증을 마치기 전 카카오로 다시 오면 안내 화면으로
    c2 = await make_client()
    r = await oauth_login(c2, fake_oauth, "kakao", KAKAO_NO_EMAIL, intent="login")
    assert location(r) == ("/signup/sent", {})

    token = (await mail_secret(db, "verify_email", "kakao@seelo.test"))["token"]
    r = await c.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["user"]["provider"] == "kakao"
    r = await oauth_login(c2, fake_oauth, "kakao", KAKAO_NO_EMAIL, intent="login")
    assert location(r) == ("/home", {})


async def test_kakao_email_not_verified_is_treated_as_no_email(
    client: httpx.AsyncClient, fake_oauth: Any
) -> None:
    profile = OAuthProfile("kakao", "k-2", "k2@seelo.test", False)
    r = await oauth_login(client, fake_oauth, "kakao", profile)
    assert location(r) == ("/signup/kakao-email", {})


async def test_pending_signup_expires_after_30_minutes(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    await oauth_login(client, fake_oauth, "google", GOOGLE_OK)
    with time_machine.travel(now_utc() + timedelta(minutes=31), tick=True):
        assert (await client.get("/api/auth/pending-signup")).status_code == 404
        r = await client.post(
            "/api/auth/pending-signup/complete", json={"agreeTerms": True, "agreePrivacy": True}
        )
        assert r.status_code == 404


# --- 중복 차단 3가지(05 5.5) -------------------------------------------------------


async def test_email_account_blocks_google_and_kakao(
    client: httpx.AsyncClient, fake_oauth: Any, db: AsyncSession
) -> None:
    await make_user(db, "same@seelo.test", provider="email")
    r = await oauth_login(client, fake_oauth, "google", GOOGLE_OK)
    assert location(r) == ("/signup", {"error": "email_taken", "provider": "email"})
    r = await oauth_login(client, fake_oauth, "kakao", KAKAO_OK)
    assert location(r) == ("/signup", {"error": "email_taken", "provider": "email"})


@pytest.mark.parametrize(
    ("existing", "other"),
    [("google", "kakao"), ("kakao", "google")],
)
async def test_social_account_blocks_email_and_other_social(
    client: httpx.AsyncClient, fake_oauth: Any, db: AsyncSession, existing: str, other: str
) -> None:
    await make_user(db, "same@seelo.test", password=None, provider=existing, provider_user_id="old-1")
    r = await signup(client, "same@seelo.test")
    assert r.status_code == 409
    assert r.json()["error"]["details"] == {"provider": existing}
    assert (
        r.json()["error"]["message"]
        == f"이 이메일은 {'구글' if existing == 'google' else '카카오'}로 가입되어 있어요"
    )
    profile = GOOGLE_OK if other == "google" else KAKAO_OK
    r = await oauth_login(client, fake_oauth, other, profile)
    assert location(r) == ("/signup", {"error": "email_taken", "provider": existing})


async def test_kakao_entered_email_taken_by_verified_user_is_409(
    client: httpx.AsyncClient, fake_oauth: Any, db: AsyncSession
) -> None:
    await make_user(db, "owner@seelo.test", provider="google", password=None, provider_user_id="g-9")
    await oauth_login(client, fake_oauth, "kakao", KAKAO_NO_EMAIL)
    r = await client.post(
        "/api/auth/pending-signup/complete",
        json={"agreeTerms": True, "agreePrivacy": True, "email": "owner@seelo.test"},
    )
    assert r.status_code == 409 and r.json()["error"]["details"] == {"provider": "google"}
    assert (
        await db.scalar(
            select(func.count()).select_from(AuthIdentity).where(AuthIdentity.provider == "kakao")
        )
        == 0
    )


async def test_social_signup_replaces_unverified_email_account(
    client: httpx.AsyncClient, fake_oauth: Any, db: AsyncSession
) -> None:
    await make_user(db, "same@seelo.test", verified=False)
    r = await oauth_login(client, fake_oauth, "google", GOOGLE_OK)
    assert location(r) == ("/signup/terms", {})
    r = await client.post(
        "/api/auth/pending-signup/complete", json={"agreeTerms": True, "agreePrivacy": True}
    )
    assert r.status_code == 200
    db.expire_all()
    providers = (await db.scalars(select(AuthIdentity.provider))).all()
    assert providers == ["google"]


async def test_callback_code_and_state_not_logged(client: httpx.AsyncClient, fake_oauth: Any) -> None:
    """OAuth code·state는 로그에 남기지 않는다(05 12장). 접근 로그는 경로만 남긴다."""
    import json

    with capture_all_logs() as logs:
        r = await client.get("/api/oauth/google/start", params={"intent": "signup"})
        _, q = location(r)
        await client.get("/api/oauth/google/callback", params=q)
    text = "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in logs)
    assert any(e.get("event") == "http_request" for e in logs)
    assert q["code"] not in text and q["state"] not in text
