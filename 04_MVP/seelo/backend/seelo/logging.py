"""구조화 로그와 민감 정보 가림(01 7.5, 13 5장)."""

import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = ("password", "token", "secret", "authorization", "cookie", "email", "api_key", "code")
EMAIL_RE = re.compile(r"([^@\s\"'<>]+)@([^@\s\"'<>]+)")
_NEVER_MASK = {"event", "level", "timestamp", "logger"}


def _sensitive(key: Any, value: Any) -> bool:
    k = str(key).lower()
    if k.endswith("_id") and isinstance(value, int) and not isinstance(value, bool):
        return False  # email_log_id=3 같은 행 번호는 민감 정보가 아니다
    return any(s in k for s in SENSITIVE_KEYS)


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return EMAIL_RE.sub(lambda m: "***@" + m.group(2), value)
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _sensitive(k, v) else _mask(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask(v) for v in value]
    return value


def mask_text(value: str) -> str:
    """문자열 안의 이메일 주소를 ***@도메인으로 바꾼다(오류 메시지를 DB·로그에 남길 때)."""
    return EMAIL_RE.sub(lambda m: "***@" + m.group(2), value)


def redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in event_dict.items():
        if k in _NEVER_MASK:
            out[k] = v
        elif _sensitive(k, v):
            out[k] = "[REDACTED]"
        else:
            out[k] = _mask(v)
    return out


def setup_logging(level: str = "INFO", *, cache: bool = True) -> None:
    """cache=False는 테스트용: 로거를 캐시하지 않아 테스트가 설정을 바꿔 로그를 모을 수 있다."""
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s", force=True)
    for noisy in ("httpx", "httpcore"):  # 요청 주소(쿼리의 토큰 포함)를 INFO로 남기지 않게
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            redact,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level.upper()]),
        cache_logger_on_first_use=cache,
    )
