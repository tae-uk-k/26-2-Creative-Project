"""메일 링크 토큰 임시 암호화(05 12장, 10 4장). Fernet(대칭키 + 무결성)."""

import json
from typing import Any

from cryptography.fernet import Fernet

from seelo.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().mail_token_fernet_key.get_secret_value()
    if not key:
        raise RuntimeError("MAIL_TOKEN_FERNET_KEY가 비어 있다(16 4장 만드는 방법 참고)")
    return Fernet(key.encode())


def encrypt_json(data: dict[str, Any]) -> bytes:
    return _fernet().encrypt(json.dumps(data, ensure_ascii=False).encode())


def decrypt_json(blob: bytes) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(bytes(blob)))
