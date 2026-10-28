"""비밀번호(05 1장, 13 8장). Argon2id 해시만 저장한다."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from seelo.security.tokens import new_token

_ph = PasswordHasher()  # 기본값이 Argon2id
PASSWORD_RE = re.compile(r"(?=.*[A-Za-z])(?=.*\d).{8,128}", re.DOTALL)
# 없는 이메일로 로그인할 때도 verify를 한 번 돌려 응답 시간을 맞추기 위한 값
DUMMY_HASH = _ph.hash(new_token())


def is_valid_password(password: str) -> bool:
    """8~128자, 영문 1자 이상, 숫자 1자 이상."""
    return PASSWORD_RE.fullmatch(password) is not None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """해시가 없으면(소셜 가입·없는 계정) 가짜 해시로 같은 시간을 쓰고 False."""
    try:
        ok = _ph.verify(password_hash or DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return bool(ok) and password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)
