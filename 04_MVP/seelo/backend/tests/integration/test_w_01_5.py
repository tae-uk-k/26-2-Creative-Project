"""W-01-5 비밀번호 재설정(05 7장, 11 4장)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import EmailLog
from seelo.models.user import Session as SessionRow
from seelo.services import email_service
from seelo.timeutil import now_utc
from tests.support import NEW_PW, PW, login, mail_secret, make_user


def _reset(token: str, pw: str = NEW_PW) -> dict[str, str]:
    return {"token": token, "password": pw, "passwordConfirm": pw}


async def _mail_count(db: AsyncSession) -> int:
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(EmailLog))


async def test_same_response_for_registered_and_unknown(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "known@seelo.test")
    known = await client.post("/api/auth/password/forgot", json={"email": "known@seelo.test"})
    assert await _mail_count(db) == 1
    unknown = await client.post("/api/auth/password/forgot", json={"email": "unknown@seelo.test"})
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content) == (202, b"{}")
    assert await _mail_count(db) == 1  # 없는 이메일에는 0통

    await make_user(db, "unverified@seelo.test", verified=False)
    await client.post("/api/auth/password/forgot", json={"email": "unverified@seelo.test"})
    assert await _mail_count(db) == 1  # 미인증도 0통


async def test_social_account_gets_guidance_mail(
    client: httpx.AsyncClient, db: AsyncSession, fake_mailer: Any
) -> None:
    await make_user(db, "k@seelo.test", password=None, provider="kakao", provider_user_id="k-1")
    r = await client.post("/api/auth/password/forgot", json={"email": "k@seelo.test"})
    assert r.status_code == 202
    row = await db.scalar(select(EmailLog))
    assert row.template_params == {"social_provider": "kakao"} and row.secret_payload is None
    assert await email_service.send(row.id) == "sent"
    mail = fake_mailer.sent[0]
    assert mail["subject"] == "[seelo] 로그인 방법 안내" and "카카오로 가입되어 있어요" in mail["text"]
    assert "/password/reset/" not in mail["text"]


async def test_reset_link_is_single_use_and_one_hour(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "r@seelo.test")
    await client.post("/api/auth/password/forgot", json={"email": "r@seelo.test"})
    token = (await mail_secret(db, "password_reset"))["token"]
    assert (await client.post("/api/auth/password/reset", json=_reset(token))).status_code == 204
    r = await client.post("/api/auth/password/reset", json=_reset(token, "another999"))
    assert r.status_code == 410 and r.json()["error"]["code"] == "TOKEN_EXPIRED"

    with time_machine.travel(now_utc() + timedelta(seconds=61), tick=True):
        await client.post("/api/auth/password/forgot", json={"email": "r@seelo.test"})
        token2 = (await mail_secret(db, "password_reset"))["token"]
    with time_machine.travel(now_utc() + timedelta(hours=1, seconds=62), tick=True):
        r = await client.post("/api/auth/password/reset", json=_reset(token2))
    assert r.status_code == 410


async def test_new_reset_mail_blocks_previous_link(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "two@seelo.test")
    await client.post("/api/auth/password/forgot", json={"email": "two@seelo.test"})
    first = (await mail_secret(db, "password_reset"))["token"]
    await client.post("/api/auth/password/forgot", json={"email": "two@seelo.test"})
    second = (await mail_secret(db, "password_reset"))["token"]
    assert (await client.post("/api/auth/password/reset", json=_reset(first))).status_code == 410
    assert (await client.post("/api/auth/password/reset", json=_reset(second))).status_code == 204


async def test_reset_changes_password_and_drops_all_sessions(make_client: Any, db: AsyncSession) -> None:
    await make_user(db, "p@seelo.test")
    phone, laptop = await make_client(), await make_client()
    assert (await login(phone, "p@seelo.test")).status_code == 200
    assert (await login(laptop, "p@seelo.test")).status_code == 200
    # 틀린 비밀번호로 쌓인 잠금 횟수도 0이 된다
    await login(laptop, "p@seelo.test", "wrongpass1")

    anon = await make_client()
    await anon.post("/api/auth/password/forgot", json={"email": "p@seelo.test"})
    token = (await mail_secret(db, "password_reset"))["token"]
    assert (await anon.post("/api/auth/password/reset", json=_reset(token))).status_code == 204

    assert await db.scalar(select(func.count()).select_from(SessionRow)) == 0
    assert (await phone.get("/api/auth/me")).status_code == 401
    assert (await login(anon, "p@seelo.test", PW)).status_code == 401
    assert (await login(anon, "p@seelo.test", NEW_PW)).status_code == 200


async def test_reset_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "v@seelo.test")
    await client.post("/api/auth/password/forgot", json={"email": "v@seelo.test"})
    token = (await mail_secret(db, "password_reset"))["token"]
    r = await client.post("/api/auth/password/reset", json=_reset(token, "weak"))
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"] == {"password": "weak_password"}
    r = await client.post(
        "/api/auth/password/reset", json={"token": token, "password": NEW_PW, "passwordConfirm": "other1234"}
    )
    assert r.json()["error"]["details"]["fields"] == {"passwordConfirm": "password_mismatch"}
    # 검증 실패는 토큰을 쓰지 않는다
    assert (await client.post("/api/auth/password/reset", json=_reset(token))).status_code == 204


@pytest.mark.usefixtures("frozen_time")
async def test_forgot_rate_limit_sixth_is_429(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        assert (
            await client.post("/api/auth/password/forgot", json={"email": "x@seelo.test"})
        ).status_code == 202
    r = await client.post("/api/auth/password/forgot", json={"email": "x@seelo.test"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
