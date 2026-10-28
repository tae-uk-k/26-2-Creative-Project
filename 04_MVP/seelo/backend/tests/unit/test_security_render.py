"""2단계: 비밀번호·토큰·CSRF·암호화 단위 테스트, 메일 10종 렌더링(16 1장)."""

import pytest
from jinja2 import UndefinedError
from pydantic import SecretStr

from seelo.config import Settings
from seelo.security import crypto, csrf, passwords, tokens
from seelo.services.email_render import render_email


@pytest.mark.parametrize(
    ("pw", "ok"),
    [
        ("abcd1234", True),
        ("A1bcdefg", True),
        ("abcdefgh", False),  # 숫자 없음
        ("12345678", False),  # 영문 없음
        ("abc123", False),  # 8자 미만
        ("a1" * 65, False),  # 128자 초과
        ("비밀번호abc1", True),
    ],
)
def test_password_rule(pw: str, ok: bool) -> None:
    assert passwords.is_valid_password(pw) is ok


def test_password_hash_and_verify() -> None:
    h = passwords.hash_password("abcd1234")
    assert h.startswith("$argon2id$")
    assert "abcd1234" not in h
    assert passwords.verify_password(h, "abcd1234")
    assert not passwords.verify_password(h, "abcd12345")
    assert not passwords.verify_password(None, "abcd1234")  # 소셜·없는 계정
    assert not passwords.verify_password("not-a-hash", "abcd1234")


def test_tokens_hash_only() -> None:
    t = tokens.new_token()
    assert len(t) >= 40
    assert tokens.hash_token(t) != t and len(tokens.hash_token(t)) == 64
    assert tokens.normalize_email("  Owner@Example.COM ") == "owner@example.com"
    assert tokens.email_hmac("A@b.com") == tokens.email_hmac(" a@B.com ")


def test_csrf_signature() -> None:
    v = csrf.new_csrf_value()
    assert csrf.verify_signature(v)
    raw, _, sig = v.rpartition(".")
    assert not csrf.verify_signature(raw + "." + "0" * len(sig))
    assert not csrf.verify_signature("nodot")
    assert not csrf.verify_signature("." + sig)


def test_crypto_roundtrip_and_no_plaintext() -> None:
    blob = crypto.encrypt_json({"token": "secret-token-value"})
    assert b"secret-token-value" not in blob
    assert crypto.decrypt_json(blob) == {"token": "secret-token-value"}


SAMPLES = {
    "verify_email": ({}, {"token": "TOK123"}, "/verify-email/TOK123"),
    "password_reset": ({"social_provider": None}, {"token": "TOK456"}, "/password/reset/TOK456"),
    "diagnosis_result": (
        {"result": "completed", "run_id": 31, "openai_rate": 0.2, "gemini_rate": None},
        None,
        "/diagnosis/31",
    ),
    "fix_requested": ({"request_id": 7, "store_name": "데모식당"}, None, "/admin/fix-requests/7"),
    "fix_decided": ({"decision": "rejected", "reject_reason": "가게 확인 필요"}, None, "/fix"),
    "map_connection": ({"kind": "connected", "provider": "kakao"}, None, "/fix/connect"),
    "fix_plan_ready": ({"plan_id": 40, "provider": "google", "item_count": 3}, None, "/fix/plans/40"),
    "manual_required": (
        {
            "request_id": 7,
            "items": [{"provider": "google", "field_label": "영업시간", "reason": "automation_blocked"}],
        },
        None,
        "/admin/fix-requests/7",
    ),
    "fix_completed": (
        {"changed_fields": ["Google 지도 영업시간"], "remeasure_date": "2026-11-30"},
        None,
        "/fix",
    ),
    "report_ready": ({"report_id": 5}, None, "/fix/report"),
}


@pytest.mark.parametrize("type_", list(SAMPLES))
def test_render_all_types(type_: str) -> None:
    params, secret, path = SAMPLES[type_]
    r = render_email(type_, params, secret)
    assert r.subject.startswith("[seelo")
    assert r.link == "http://seelo.test" + path
    assert r.link in r.text
    assert r.text.endswith("이 메일은 발신 전용이에요.")
    assert "<html" in r.html and "seelo" in r.html
    if secret:  # 토큰은 링크에만, 제목에는 없다
        assert secret["token"] not in r.subject


def test_render_details() -> None:
    r = render_email("diagnosis_result", SAMPLES["diagnosis_result"][0])
    assert "ChatGPT 추천 등장률: 20.0%" in r.text
    assert "Gemini 추천 등장률: 측정하지 못함" in r.text
    r = render_email("fix_completed", SAMPLES["fix_completed"][0])
    assert "11월 30일" in r.text and "Google 지도 영업시간" in r.text
    r = render_email("password_reset", {"social_provider": "kakao"})
    assert r.subject == "[seelo] 로그인 방법 안내"
    assert "카카오로 가입되어 있어요" in r.text and r.link == "http://seelo.test/login"
    r = render_email("manual_required", SAMPLES["manual_required"][0])
    assert "Google 지도 영업시간 — 자동화 차단(로그인·보안 확인)" in r.text
    r = render_email("map_connection", {"kind": "reminder", "provider": "google"})
    assert r.subject == "[seelo] 초대가 아직 오지 않았어요"


def test_render_escapes_html() -> None:
    r = render_email("fix_requested", {"request_id": 1, "store_name": "<b>식당</b>"})
    assert "<b>식당</b>" in r.text
    assert "&lt;b&gt;식당&lt;/b&gt;" in r.html


def test_render_missing_value_fails() -> None:
    with pytest.raises((KeyError, UndefinedError)):
        render_email("fix_requested", {"request_id": 1})


def test_prod_requires_mail_token_key() -> None:
    prod = {
        "app_env": "prod",
        "cookie_secure": True,
        "fake_externals": False,
        "app_base_url": "https://seelo.kr",
    }
    with pytest.raises(ValueError, match="MAIL_TOKEN_FERNET_KEY"):
        Settings(**prod, mail_token_fernet_key=SecretStr(""))
