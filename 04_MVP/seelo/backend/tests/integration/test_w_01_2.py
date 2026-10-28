"""W-01-2 이메일 가입·인증(05 4장, 11 4장)."""

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.user import AuthToken, User
from seelo.services import email_service
from seelo.services.maintenance import cleanup_unverified
from seelo.timeutil import now_utc
from tests.support import PW, capture_all_logs, dump_db_text, login, mail_secret, signup, signup_verified

pytestmark = pytest.mark.usefixtures("fake_mailer")


async def _log_id_of(db: AsyncSession, email: str) -> int:
    from seelo.models.ops import EmailLog

    db.expire_all()
    return await db.scalar(
        select(EmailLog.id).where(EmailLog.to_email == email).order_by(EmailLog.id.desc()).limit(1)
    )


async def test_signup_then_verify_logs_in(client: httpx.AsyncClient, db: AsyncSession) -> None:
    r = await signup(client, " Owner@Example.COM ")
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "owner@example.com" and body["mailTicket"]

    r = await client.get("/api/auth/signup/mail-status", params={"ticket": body["mailTicket"]})
    assert r.json() == {"status": "queued"}
    assert (await client.get("/api/auth/me")).status_code == 401  # 인증 전에는 로그인 상태가 아니다

    token = (await mail_secret(db, "verify_email"))["token"]
    r = await client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["email"] == "owner@example.com" and user["provider"] == "email"
    assert user["role"] == "owner" and user["hasStore"] is False
    r = await client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["id"] == user["id"]


async def test_mail_status_follows_send(
    client: httpx.AsyncClient, db: AsyncSession, fake_mailer: Any
) -> None:
    ticket = (await signup(client, "a@seelo.test")).json()["mailTicket"]
    assert await email_service.send(await _log_id_of(db, "a@seelo.test")) == "sent"
    r = await client.get("/api/auth/signup/mail-status", params={"ticket": ticket})
    assert r.json() == {"status": "sent"}
    assert "/verify-email/" in fake_mailer.sent[0]["text"]


async def test_mail_fails_three_retries_then_status_failed(
    client: httpx.AsyncClient, db: AsyncSession, fake_mailer: Any
) -> None:
    fake_mailer.fail_times = 99
    ticket = (await signup(client, "a@seelo.test")).json()["mailTicket"]
    log_id = await _log_id_of(db, "a@seelo.test")
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await email_service.send(log_id)
    assert await email_service.send(log_id) == "failed"
    r = await client.get("/api/auth/signup/mail-status", params={"ticket": ticket})
    assert r.json() == {"status": "failed"}


async def test_bad_ticket_is_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/auth/signup/mail-status", params={"ticket": "forged.ticket"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_unverified_duplicate_signup_replaces_old_account(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    await signup(client, "dup@seelo.test")
    old_token = (await mail_secret(db, "verify_email"))["token"]
    old_id = await db.scalar(select(User.id).where(User.email == "dup@seelo.test"))

    r = await signup(client, "dup@seelo.test", "another123")
    assert r.status_code == 201
    db.expire_all()
    ids = (await db.scalars(select(User.id).where(User.email == "dup@seelo.test"))).all()
    assert len(ids) == 1 and ids[0] != old_id
    # 이전 계정의 링크는 계정과 함께 지워졌다
    r = await client.post("/api/auth/verify-email", json={"token": old_token})
    assert r.status_code == 410 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_verified_duplicate_signup_is_409(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup_verified(client, db, "taken@seelo.test")
    r = await signup(client, "taken@seelo.test")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err == {
        "code": "EMAIL_TAKEN",
        "message": "이 이메일은 이메일로 가입되어 있어요",
        "details": {"provider": "email"},
    }


async def test_token_reuse_and_expiry_are_410(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup(client, "a@seelo.test")
    token = (await mail_secret(db, "verify_email"))["token"]
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
    r = await client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 410  # 재사용

    await signup(client, "b@seelo.test")
    token_b = (await mail_secret(db, "verify_email", "b@seelo.test"))["token"]
    with time_machine.travel(now_utc() + timedelta(hours=24, seconds=1), tick=True):
        r = await client.post("/api/auth/verify-email", json={"token": token_b})
    assert r.status_code == 410  # 24시간+1초

    r = await client.post("/api/auth/verify-email", json={"token": "x" * 43})
    assert r.status_code == 410  # 없는 토큰


async def test_unverified_account_cleaned_after_24h(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup(client, "late@seelo.test")
    counts = await cleanup_unverified(db, now_utc() + timedelta(hours=23))
    await db.commit()
    assert counts["users"] == 0
    counts = await cleanup_unverified(db, now_utc() + timedelta(hours=24, seconds=1))
    await db.commit()
    assert counts["users"] == 1
    assert await db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    ("override", "field", "code"),
    [
        ({"email": "not-an-email"}, "email", "invalid_email"),
        ({"password": "short1", "passwordConfirm": "short1"}, "password", "weak_password"),
        ({"password": "onlyletters", "passwordConfirm": "onlyletters"}, "password", "weak_password"),
        ({"passwordConfirm": "different123"}, "passwordConfirm", "password_mismatch"),
        ({"agreePrivacy": False}, "agreeTerms", "terms_required"),
    ],
)
async def test_signup_validation_fields(
    client: httpx.AsyncClient, override: dict[str, Any], field: str, code: str
) -> None:
    body = {
        "email": "v@seelo.test",
        "password": PW,
        "passwordConfirm": PW,
        "agreeTerms": True,
        "agreePrivacy": True,
    }
    r = await client.post("/api/auth/signup", json={**body, **override})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"] == {field: code}


@pytest.mark.usefixtures("frozen_time")
async def test_signup_rate_limit_sixth_is_429(client: httpx.AsyncClient) -> None:
    for i in range(5):
        assert (await signup(client, f"r{i}@seelo.test")).status_code == 201
    r = await signup(client, "r5@seelo.test")
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


async def test_resend_cooldown_and_old_link_blocked(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await signup(client, "re@seelo.test")
    old_token = (await mail_secret(db, "verify_email"))["token"]
    r = await client.post("/api/auth/verify-email/resend", json={"email": "re@seelo.test"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RESEND_COOLDOWN"
    assert 1 <= r.json()["error"]["details"]["retryAfterSeconds"] <= 60

    with time_machine.travel(now_utc() + timedelta(seconds=61), tick=True):
        r = await client.post("/api/auth/verify-email/resend", json={"email": "re@seelo.test"})
        assert r.status_code == 202 and r.json()["mailTicket"]
        new_token = (await mail_secret(db, "verify_email"))["token"]
        assert new_token != old_token
        assert (await client.post("/api/auth/verify-email", json={"token": old_token})).status_code == 410
        assert (await client.post("/api/auth/verify-email", json={"token": new_token})).status_code == 200


async def test_resend_unknown_or_verified_email_looks_the_same(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    await signup_verified(client, db, "done@seelo.test")
    before = await db.scalar(select(func.count()).select_from(AuthToken))
    for email in ("nobody@seelo.test", "done@seelo.test"):
        r = await client.post("/api/auth/verify-email/resend", json={"email": email})
        assert r.status_code == 202 and set(r.json()) == {"mailTicket"}
        r = await client.get("/api/auth/signup/mail-status", params={"ticket": r.json()["mailTicket"]})
        assert r.json() == {"status": "sent"}
    db.expire_all()
    assert await db.scalar(select(func.count()).select_from(AuthToken)) == before


async def test_no_plaintext_token_or_password_in_db_or_logs(
    make_client: Any, db: AsyncSession, fake_mailer: Any
) -> None:
    """가입·인증·재설정 시나리오 뒤 DB 전체 텍스트와 로그에 토큰·비밀번호 원문이 없다(W-01-2, W-11-1)."""
    c = await make_client()
    secrets: list[str] = [PW, "brandnew789"]
    with capture_all_logs() as logs:
        await signup(c, "s@seelo.test")
        log_id = await _log_id_of(db, "s@seelo.test")
        secrets.append((await mail_secret(db, "verify_email"))["token"])
        assert await email_service.send(log_id) == "sent"
        assert (await c.post("/api/auth/verify-email", json={"token": secrets[-1]})).status_code == 200
        secrets.extend([c.cookies["seelo_session"], c.cookies["seelo_csrf"]])

        assert (await c.post("/api/auth/password/forgot", json={"email": "s@seelo.test"})).status_code == 202
        reset_token = (await mail_secret(db, "password_reset"))["token"]
        secrets.append(reset_token)
        assert await email_service.send(await _log_id_of(db, "s@seelo.test")) == "sent"
        r = await c.post(
            "/api/auth/password/reset",
            json={"token": reset_token, "password": "brandnew789", "passwordConfirm": "brandnew789"},
        )
        assert r.status_code == 204
        assert (await login(c, "s@seelo.test", "brandnew789")).status_code == 200
        secrets.append(c.cookies["seelo_session"])

    dump = await dump_db_text(db)
    log_text = "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in logs)
    assert len(logs) > 0 and "email_sent" in log_text  # 로그를 실제로 모았다
    for s in secrets:
        assert s not in dump, "DB에 원문이 있다"
        assert s not in log_text, "로그에 원문이 있다"
    # 메일은 실제로 링크를 담고 있었다(가짜 메일함에만 원문이 있다)
    assert any(secrets[2] in m["text"] for m in fake_mailer.sent)
