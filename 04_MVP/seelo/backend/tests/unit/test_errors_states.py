"""0·1단계: 오류 형식(04 2장)과 상태 전이표(03 2장) 단위 테스트."""

import pytest

from seelo.domain import states
from seelo.errors import ERRORS, AppError, validation_fields


def test_app_error_formats_provider_label() -> None:
    e = AppError("EMAIL_TAKEN", {"provider": "google"})
    assert e.status == 409
    assert e.message == "이 이메일은 구글로 가입되어 있어요"


def test_app_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError):
        AppError("NOPE")


def test_every_error_has_status_and_message() -> None:
    for code, (status, message) in ERRORS.items():
        assert 400 <= status < 600, code
        assert message, code


def test_validation_fields_mapping() -> None:
    errors = [
        {"loc": ("body", "password"), "type": "weak_password"},
        {"loc": ("body",), "type": "password_mismatch"},
        {"loc": ("body",), "type": "terms_required"},
        {"loc": ("body", "email"), "type": "value_error"},
        {"loc": ("body", "name"), "type": "missing"},
        {"loc": ("body", "name"), "type": "string_too_long"},  # 같은 필드는 첫 오류만
    ]
    assert validation_fields(errors) == {
        "password": "weak_password",
        "passwordConfirm": "password_mismatch",
        "agreeTerms": "terms_required",
        "email": "invalid_email",
        "name": "required",
    }


def test_allowed_transitions_pass() -> None:
    states.check_allowed("stores", {"collecting"}, "measuring")
    states.check_allowed("fix_requests", {"remeasure_scheduled"}, "fixing")
    states.check_allowed("fix_logs", {"queued", "pending_reflection", "manual_required"}, "disconnected")


@pytest.mark.parametrize(
    ("table", "from_", "to"),
    [
        ("stores", {"diagnosed"}, "measuring"),
        ("measurement_runs", {"completed"}, "running"),
        ("fix_requests", {"report_ready"}, "requested"),
        ("fix_logs", {"applied"}, "queued"),
        ("fix_requests", {"requested", "rejected"}, "approved"),  # 하나라도 불허면 오류
        ("stores", set(), "archived"),
    ],
)
def test_illegal_transitions_raise(table: str, from_: set[str], to: str) -> None:
    with pytest.raises(ValueError):
        states.check_allowed(table, from_, to)


def test_allowed_table_values_are_enum_values() -> None:
    """ALLOWED에 쓴 상태 문자열이 모두 해당 Enum에 있다(오타 방지)."""
    status_enum = {
        "stores": states.StoreStatus,
        "measurement_runs": states.RunStatus,
        "fix_requests": states.FixRequestStatus,
        "map_connections": states.ConnectionStatus,
        "fix_plans": states.FixPlanStatus,
        "fix_logs": states.FixLogStatus,
        "remeasure_schedules": states.ScheduleStatus,
        "comparison_reports": states.ReportStatus,
        "email_logs": states.EmailStatus,
    }
    for table, rules in states.ALLOWED.items():
        values = {e.value for e in status_enum[table]}
        for src, dsts in rules.items():
            assert src in values, (table, src)
            assert dsts <= values, (table, dsts - values)
