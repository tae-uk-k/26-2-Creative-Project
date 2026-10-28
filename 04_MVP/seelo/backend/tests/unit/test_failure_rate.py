"""W-04-4 실패율 경계(08 2.4): 30% 초과면 실패, 정확히 30%는 통과."""

import pytest

from seelo.domain.metrics import failure_rate, is_run_failed
from seelo.integrations.llm import LlmError, reason_for_status


@pytest.mark.parametrize(("failed", "total", "result"), [(29, 100, False), (30, 100, False), (31, 100, True)])
def test_boundary(failed: int, total: int, result: bool) -> None:
    assert is_run_failed(failed, total) is result


def test_sixty_calls_and_empty() -> None:
    assert not is_run_failed(18, 60)  # 0.30
    assert is_run_failed(19, 60)
    assert is_run_failed(0, 0)
    assert failure_rate(3, 10) == 0.3


@pytest.mark.parametrize(
    ("status", "reason", "retryable"),
    [
        (429, "rate_limited", True),
        (500, "server_error", True),
        (503, "server_error", True),
        (400, "bad_request", False),
        (401, "auth_error", False),
        (403, "auth_error", False),
        (404, "bad_request", False),
    ],
)
def test_error_classification(status: int, reason: str, retryable: bool) -> None:
    assert reason_for_status(status) == reason
    assert LlmError("openai", reason).retryable is retryable
    assert LlmError("openai", "timeout").retryable and LlmError("openai", "empty_answer").retryable
    assert not LlmError("openai", "refused").retryable
