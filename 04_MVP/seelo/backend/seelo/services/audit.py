"""감사 기록(03 6장). detail에 개인정보·비밀 값을 넣지 않는다. 커밋은 부르는 쪽."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import AuditLog

ACTIONS = frozenset(
    {
        "fix_request.approve",
        "fix_request.reject",
        "connection.verify",
        "fix_log.manual_done",
        "fix_plan.regenerate",
        "report.regenerate",
        "remeasure.now",
        "fix_plan.approve",
        "store.change",
        "account.delete",
    }
)


def record(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action {action}")
    row = AuditLog(
        actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, detail=detail or {}
    )
    session.add(row)
    return row
