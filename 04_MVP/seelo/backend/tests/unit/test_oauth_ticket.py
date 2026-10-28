"""3단계: 제공자 응답 해석(05 5.3)·메일 티켓(05 4.1)·인가 주소."""

from urllib.parse import parse_qs, urlsplit

import pytest

from seelo.errors import AppError
from seelo.integrations.oauth import KAKAO, AuthlibOAuth, parse_google, parse_kakao
from seelo.services.auth_service import make_mail_ticket, read_mail_ticket


def test_parse_google() -> None:
    p = parse_google({"sub": "1234", "email": "a@gmail.com", "email_verified": True})
    assert (p.provider, p.provider_user_id, p.email, p.email_verified) == (
        "google",
        "1234",
        "a@gmail.com",
        True,
    )
    assert parse_google({"sub": "1", "email": "a@gmail.com", "email_verified": "true"}).email_verified
    assert not parse_google({"sub": "1", "email": "a@gmail.com", "email_verified": False}).email_verified
    assert not parse_google({"sub": "1"}).email_verified


@pytest.mark.parametrize(
    ("account", "email", "verified"),
    [
        ({"email": "k@kakao.com", "is_email_valid": True, "is_email_verified": True}, "k@kakao.com", True),
        ({"email": "k@kakao.com", "is_email_valid": False, "is_email_verified": True}, "k@kakao.com", False),
        ({"email": "k@kakao.com", "is_email_valid": True, "is_email_verified": False}, "k@kakao.com", False),
        ({"email_needs_agreement": True}, None, False),  # 동의 안 함
        ({}, None, False),
    ],
)
def test_parse_kakao(account: dict, email: str | None, verified: bool) -> None:
    p = parse_kakao({"id": 4242, "kakao_account": account})
    assert p.provider_user_id == "4242"  # 숫자 → 문자열
    assert (p.email, p.email_verified) == (email, verified)


def test_kakao_authorize_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from seelo.config import get_settings

    monkeypatch.setenv("KAKAO_OAUTH_CLIENT_ID", "rest-key")
    monkeypatch.setenv("KAKAO_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()
    try:
        url = AuthlibOAuth().authorize_url(
            "kakao", redirect_uri="https://x.kr/api/oauth/kakao/callback", state="S"
        )
    finally:
        get_settings.cache_clear()
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == KAKAO.authorize
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q == {
        "response_type": "code",
        "client_id": "rest-key",
        "redirect_uri": "https://x.kr/api/oauth/kakao/callback",
        "scope": "account_email",
        "state": "S",
    }
    assert "secret" not in url


def test_unconfigured_provider_raises() -> None:
    with pytest.raises(RuntimeError):
        AuthlibOAuth().authorize_url("google", redirect_uri="https://x", state="s")


def test_mail_ticket_roundtrip_and_tamper() -> None:
    t = make_mail_ticket(42)
    assert read_mail_ticket(t) == 42
    assert read_mail_ticket(make_mail_ticket(None)) == 0
    with pytest.raises(AppError) as e:
        read_mail_ticket(t[:-2] + "xx")
    assert e.value.code == "NOT_FOUND"
