"""3단계: 제공자 응답 해석(05 5.3)·메일 티켓(05 4.1)·인가 주소."""

from urllib.parse import parse_qs, urlsplit

import pytest

from seelo.errors import AppError
from seelo.integrations.oauth import GOOGLE, KAKAO, AuthlibOAuth, parse_google, parse_kakao
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


@pytest.mark.parametrize(
    ("provider", "endpoint", "scope"),
    [("google", GOOGLE, "openid email profile"), ("kakao", KAKAO, None)],
)
def test_authorize_url_uses_only_supported_scopes(monkeypatch, provider, endpoint, scope) -> None:
    from seelo.config import get_settings

    monkeypatch.setenv(f"{provider.upper()}_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv(f"{provider.upper()}_OAUTH_CLIENT_SECRET", "secret")
    get_settings.cache_clear()
    redirect_uri = f"https://x.kr/api/oauth/{provider}/callback"
    try:
        url = AuthlibOAuth().authorize_url(provider, redirect_uri=redirect_uri, state="S +&=")
    finally:
        get_settings.cache_clear()
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == endpoint.authorize
    q = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
    expected = {
        "response_type": "code",
        "client_id": "client-id",
        "redirect_uri": redirect_uri,
        "state": "S +&=",
    }
    if scope is not None:
        expected["scope"] = scope
    assert q == expected
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
