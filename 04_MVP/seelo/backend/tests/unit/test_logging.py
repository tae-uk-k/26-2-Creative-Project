"""0단계: 로그 가림 처리기(01 7.5, 13 5장)."""

from seelo.logging import redact


def test_redact_masks_sensitive_keys_and_email_in_text() -> None:
    out = redact(None, "info", {"event": "x", "email": "a@b.com", "note": "user a@b.com", "token": "abc"})
    assert out == {"event": "x", "email": "[REDACTED]", "note": "user ***@b.com", "token": "[REDACTED]"}


def test_redact_nested_and_lists() -> None:
    out = redact(
        None,
        "info",
        {"event": "login", "body": {"password": "pw1", "who": ["c@d.kr", 3]}, "Authorization": "Bearer t"},
    )
    assert out["body"] == {"password": "[REDACTED]", "who": ["***@d.kr", 3]}
    assert out["Authorization"] == "[REDACTED]"
    assert out["event"] == "login"


def test_redact_keeps_plain_values() -> None:
    out = redact(None, "info", {"event": "ok", "store_id": 12, "duration_ms": 5.2})
    assert out == {"event": "ok", "store_id": 12, "duration_ms": 5.2}


def test_redact_keeps_integer_row_ids() -> None:
    out = redact(
        None, "info", {"event": "email_sent", "email_log_id": 3, "email_id": "a@b.com", "token_id": "x"}
    )
    assert out == {
        "event": "email_sent",
        "email_log_id": 3,
        "email_id": "[REDACTED]",
        "token_id": "[REDACTED]",
    }
