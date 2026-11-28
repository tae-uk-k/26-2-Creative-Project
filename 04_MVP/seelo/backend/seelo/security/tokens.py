"""난수 토큰과 해시(05 1장, 13 8장). DB에는 해시만 저장한다."""

import hashlib
import hmac
import secrets

from seelo.config import get_settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_hmac(email: str) -> str:
    key = get_settings().email_hmac_key.get_secret_value().encode()
    return hmac.new(key, normalize_email(email).encode(), "sha256").hexdigest()
