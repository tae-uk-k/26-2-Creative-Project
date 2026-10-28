"""A01 정비 신청 목록의 상태 판정(03 5장). IO 없음.

한 신청이 여러 필터에 걸릴 수 있다(예: 정비 중이면서 수동 처리 필요). 대표 상태는 정한 순서로 처음 맞는 것.
"""

from dataclasses import dataclass, field

FILTERS = (
    "requested",
    "approved",
    "connect_waiting",
    "plan_waiting",
    "fixing",
    "manual_required",
    "remeasure_waiting",
    "report_ready",
    "rejected",
    "failed",
)
DISPLAY_ORDER = (
    "failed",
    "manual_required",
    "requested",
    "rejected",
    "approved",
    "connect_waiting",
    "plan_waiting",
    "fixing",
    "remeasure_waiting",
    "report_ready",
)
# 어느 필터에도 걸리지 않을 때(예: connecting인데 정비안이 생성 중) 신청 상태로 대표 상태를 정한다
FALLBACK = {
    "requested": "requested",
    "approved": "approved",
    "connecting": "connect_waiting",
    "fixing": "fixing",
    "remeasure_scheduled": "remeasure_waiting",
    "remeasuring": "remeasure_waiting",
    "remeasure_failed": "failed",
    "report_ready": "report_ready",
    "rejected": "rejected",
}


@dataclass
class RequestFacts:
    status: str  # fix_requests.status
    plan_statuses: set[str] = field(default_factory=set)  # 지도별 최신 정비안의 상태
    has_manual: bool = False  # manual_required 칸이 있음
    latest_report_failed: bool = False  # 최신 보고서가 generation_failed


def matching(f: RequestFacts) -> set[str]:
    out: set[str] = set()
    if f.status in ("requested", "approved", "fixing", "report_ready", "rejected"):
        out.add(f.status)
    if f.status == "connecting" and not f.plan_statuses:
        out.add("connect_waiting")
    if "awaiting_approval" in f.plan_statuses:
        out.add("plan_waiting")
    if f.has_manual:
        out.add("manual_required")
    if f.status in ("remeasure_scheduled", "remeasuring"):
        out.add("remeasure_waiting")
    if "generation_failed" in f.plan_statuses or f.latest_report_failed or f.status == "remeasure_failed":
        out.add("failed")
    return out


def display_status(f: RequestFacts) -> str:
    hits = matching(f)
    return next((k for k in DISPLAY_ORDER if k in hits), FALLBACK.get(f.status, "requested"))
