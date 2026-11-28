"""웹훅 인증·반복 수신·보존 범위를 별도 테스트 DB에서 검증한다."""

import hashlib
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from seelo.config import get_settings
from seelo.models.user import AuthIdentity, AuthToken, PendingSignup, Session, User
from seelo.security.tokens import hash_token
from seelo.timeutil import now_utc
from tests.support import make_user

KEY = "unit-test-admin-key"
PATH = "/api/webhooks/kakao/unlink"
PARAMS = {"app_id": "1630584", "user_id": "1001", "referrer_type": "UNLINK_FROM_APPS"}


@pytest.fixture
def configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kakao_app_id", "1630584")
    monkeypatch.setattr(
        settings, "kakao_unlink_admin_key_sha256", SecretStr(hashlib.sha256(KEY.encode()).hexdigest())
    )


async def test_unconfigured_hidden(api):
    assert (await api.get(PATH, params=PARAMS)).status_code == 404


async def test_requires_header_not_cookie(api, configured):
    assert (await api.get(PATH, params=PARAMS)).status_code == 401
    assert (await api.get(PATH, params=PARAMS, headers={"Authorization": "KakaoAK wrong"})).status_code == 401


async def test_unlink_is_idempotent_and_preserves_account(api, db, configured):
    target = await make_user(db, "unlink@seelo.test", provider="kakao", provider_user_id="1001")
    other = await make_user(db, "other@seelo.test", provider="google", provider_user_id="1001")
    pending = PendingSignup(
        provider="kakao",
        provider_user_id="1001",
        token_hash=hash_token("pending"),
        expires_at=now_utc() + timedelta(minutes=30),
    )
    db.add(pending)
    db.add(
        AuthToken(
            user_id=target.id,
            type="verify",
            token_hash=hash_token("old-mail-token"),
            expires_at=now_utc() + timedelta(hours=1),
        )
    )
    for user in (target, other):
        db.add(
            Session(
                user_id=user.id,
                token_hash=hash_token(str(user.id)),
                csrf_token_hash="csrf",
                expires_at=now_utc() + timedelta(days=1),
            )
        )
    await db.commit()
    for _ in range(2):
        response = await api.get(PATH, params=PARAMS, headers={"Authorization": "KakaoAK " + KEY})
        assert response.status_code == 200
    assert await db.get(User, target.id) is not None
    assert await db.scalar(select(AuthToken.used_at).where(AuthToken.user_id == target.id)) is not None
    assert list((await db.scalars(select(AuthIdentity.provider))).all()) == ["google"]
    assert list((await db.scalars(select(Session.user_id))).all()) == [other.id]
    assert not list((await db.scalars(select(PendingSignup.id))).all())


@pytest.mark.parametrize(
    "params",
    [
        {**PARAMS, "app_id": "different"},
        {**PARAMS, "user_id": "../wrong"},
        {**PARAMS, "referrer_type": "UNKNOWN"},
        {},
        list(PARAMS.items()) + [("user_id", "2002")],
    ],
)
async def test_invalid_payload_does_not_touch_identities(api, db, configured, params):
    user = await make_user(db, "keep@seelo.test", provider="kakao", provider_user_id="1001")
    response = await api.get(PATH, params=params, headers={"Authorization": "KakaoAK " + KEY})
    assert response.status_code == 200
    assert await db.scalar(select(AuthIdentity.id).where(AuthIdentity.user_id == user.id))


async def test_missing_user_acknowledged(api, configured):
    assert (
        await api.get(PATH, params=PARAMS, headers={"Authorization": "KakaoAK " + KEY})
    ).status_code == 200


async def test_database_error_acknowledged_without_leaking(api, configured, monkeypatch):
    from seelo.services import kakao_unlink

    async def broken(*args):
        raise RuntimeError("sensitive detail")

    monkeypatch.setattr(kakao_unlink, "disconnect", broken)
    result = await api.get(PATH, params=PARAMS, headers={"Authorization": "KakaoAK " + KEY})
    assert result.status_code == 200 and "sensitive" not in result.text
