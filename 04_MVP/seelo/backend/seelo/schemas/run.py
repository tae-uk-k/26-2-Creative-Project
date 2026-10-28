"""측정 진행·모은 정보(04 5.3, 14 1.3)."""

from typing import Literal

from seelo.schemas.common import CamelModel


class RunProgress(CamelModel):
    run_id: int
    kind: Literal["diagnosis", "remeasure"]
    status: Literal["queued", "running", "parsing", "completed", "failed", "canceled"]
    stage: Literal["collecting", "generating_questions", "calling_ai", "finalizing", "done"]
    progress_done: int
    progress_total: int
    waiting_reason: Literal["cost_limit"] | None
    failure_reason: Literal["failure_rate", "collect_insufficient", "enqueue_failed", "stuck"] | None
    can_cancel: bool
    next: str | None


class RunIdResponse(CamelModel):
    run_id: int


class CollectedValues(CamelModel):
    google: str | None = None
    kakao: str | None = None
    naver: str | None = None
    website: str | None = None
    instagram: str | None = None


class CollectedRow(CamelModel):
    key: str
    label: str
    values: CollectedValues


class CollectedInfo(CamelModel):
    rows: list[CollectedRow]
