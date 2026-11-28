"""S12 정비 신청 진행 단계(04 7.1 `steps` 판정). IO 없음."""

from dataclasses import dataclass

STEP_KEYS = ("received", "approved", "connect", "review", "fixing", "remeasure_waiting", "report")
AFTER_APPROVED = {
    "approved",
    "connecting",
    "fixing",
    "remeasure_scheduled",
    "remeasuring",
    "remeasure_failed",
    "report_ready",
}
AFTER_FIXING = {"remeasure_scheduled", "remeasuring", "remeasure_failed", "report_ready"}
AFTER_WAITING = {"remeasuring", "remeasure_failed", "report_ready"}


@dataclass
class Step:
    key: str
    state: str  # done|current|todo
    action_path: str | None = None


def fix_steps(
    status: str,
    *,
    connected: bool,
    plan_statuses: dict[int, str],  # 정비안 id → 상태(지도별 최신)
) -> list[Step]:
    """received 항상 done. 거절이면 received만 done이고 나머지 todo."""
    if status == "rejected":
        return [Step("received", "done")] + [Step(k, "todo") for k in STEP_KEYS[1:]]

    def st(done: bool, current: bool) -> str:
        return "done" if done else ("current" if current else "todo")

    awaiting = sorted(pid for pid, s in plan_statuses.items() if s == "awaiting_approval")
    approved = sorted(pid for pid, s in plan_statuses.items() if s == "approved")
    review_plan = (awaiting or approved or [None])[0]
    return [
        Step("received", "done"),
        Step("approved", st(status in AFTER_APPROVED, status == "requested")),
        Step(
            "connect",
            st(connected, status == "connecting"),
            "/fix/connect" if status != "requested" else None,
        ),
        Step(
            "review",
            st(bool(approved), bool(awaiting)),
            f"/fix/plans/{review_plan}" if review_plan is not None else None,
        ),
        Step("fixing", st(status in AFTER_FIXING, status == "fixing")),
        Step("remeasure_waiting", st(status in AFTER_WAITING, status == "remeasure_scheduled")),
        Step("report", st(status == "report_ready", status in ("remeasuring", "remeasure_failed"))),
    ]
