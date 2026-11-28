"""CSRF 토큰(05 3장, 13 8장): 서명된 double-submit 쿠키 + 세션 묶기."""

import hmac
import secrets

from starlette.responses import Response

from seelo.config import get_settings

CSRF_COOKIE = "seelo_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _sign(raw: str) -> str:
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, raw.encode(), "sha256").hexdigest()[:32]


def new_csrf_value() -> str:
    raw = secrets.token_urlsafe(24)
    return f"{raw}.{_sign(raw)}"


def verify_signature(value: str) -> bool:
    raw, sep, sig = value.rpartition(".")
    return bool(sep) and bool(raw) and hmac.compare_digest(sig, _sign(raw))


def set_csrf_cookie(response: Response, value: str) -> None:
    s = get_settings()
    response.set_cookie(
        CSRF_COOKIE,
        value,
        max_age=s.session_ttl_days * 86400,
        httponly=False,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
