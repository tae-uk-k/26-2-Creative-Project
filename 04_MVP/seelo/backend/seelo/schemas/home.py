"""홈(S07, 04 5.1, 14 1.3)."""

from typing import Any, Literal

from seelo.schemas.common import CamelModel, Provider, StoreSummary

CardKey = Literal[
    "no_store",
    "fix_requested",
    "fix_rejected",
    "measuring",
    "measure_failed",
    "diagnosed",
    "free_used_store_changed",
    "plan_needs_approval",
    "plan_preparing",
    "connect_needed",
    "fixing",
    "remeasure_waiting",
    "remeasuring",
    "remeasure_failed",
    "report_ready",
    "unknown",
]


class HomeResponse(CamelModel):
    card: CardKey
    store: StoreSummary | None
    store_change_blocked: bool
    revoked_providers: list[Provider]
    manual_in_progress: bool
    retries_left_today: int
    has_history: bool
    data: dict[str, Any]  # 카드별 형태는 04 5.1 표. 키는 camelCase로 넣는다
