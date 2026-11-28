"""S07 홈 카드 판정(03 4장). IO 없음.

위에서부터 처음 맞는 카드 하나를 고른다(명세서 7장 표와 같은 순서). 입력은 status 속성이 있는 객체면 된다.
`unknown`은 나오면 안 된다(부르는 쪽이 오류 로그를 남기고 버튼 없는 카드로 응답).
"""

from collections.abc import Iterable
from typing import Any, Protocol

CARDS = (
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
)
_AFTER_CONNECT = {
    "fixing": "fixing",
    "remeasure_scheduled": "remeasure_waiting",
    "remeasuring": "remeasuring",
    "remeasure_failed": "remeasure_failed",
    "report_ready": "report_ready",
}


class HasStatus(Protocol):
    status: str


def pick_card(
    store: HasStatus | None,
    req: HasStatus | None,
    plans: Iterable[HasStatus],
    connections: Iterable[Any] = (),
    has_manual: bool = False,
) -> str:
    """connections·has_manual은 카드 선택에 쓰지 않는다(공통 표시 revokedProviders·manualInProgress용)."""
    if store is None:
        return "no_store"
    if req is not None and req.status == "requested":
        return "fix_requested"
    if req is not None and req.status == "rejected":
        return "fix_rejected"
    pre = req is None or req.status == "approved"
    if pre and store.status in ("collecting", "measuring"):
        return "measuring"
    if pre and store.status == "measure_failed":
        return "measure_failed"
    if req is None and store.status == "diagnosed":
        return "diagnosed"
    if req is None and store.status == "collected":
        return "free_used_store_changed"
    if req is None:
        return "unknown"
    statuses = {p.status for p in plans}
    if req.status in ("connecting", "fixing") and "awaiting_approval" in statuses:
        return "plan_needs_approval"
    if req.status == "connecting" and statuses & {"generating", "generation_failed"}:
        return "plan_preparing"
    if req.status == "connecting" and not statuses:
        return "connect_needed"
    return _AFTER_CONNECT.get(req.status, "unknown")
