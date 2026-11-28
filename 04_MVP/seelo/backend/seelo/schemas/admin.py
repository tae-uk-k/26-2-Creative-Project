"""관리자(04 8장, 14 1.7). 관리자에게는 실패율·비용을 보인다."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from seelo.schemas.common import CamelModel, Provider, StoreSources

AdminFilter = Literal[
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
]


class AdminListItem(CamelModel):
    id: int
    created_at: datetime
    owner_email: str
    store_name: str
    diagnosis_status: str | None  # 그 가게의 가장 최근 진단 측정 상태
    status: str
    display_status: AdminFilter


class RejectRequest(CamelModel):
    reason: str = Field(max_length=500)


class StatusResponse(CamelModel):
    status: str


class ManualDoneRequest(CamelModel):
    """E30. beforeValue는 자동으로 읽지 못해 before_value가 비었을 때만 저장한다."""

    before_value: Any = None


AttentionReasonT = Literal[
    "verification_required",
    "under_review",
    "duplicate_profile",
    "no_owner_authority",
    "guideline_violation",
    "store_not_visible",
    "other",
]


class VerifyConnectionRequest(CamelModel):
    """수동 확인 모드(09 5장): manualResult가 있으면 API 안에서 바로 처리. 없으면 verifyConnection 작업."""

    manual_result: Literal["connected", "needs_attention"] | None = None
    attention_reason: AttentionReasonT | None = None
    external_ref: str | None = Field(default=None, max_length=500)


class ManualItem(CamelModel):
    fix_log_id: int
    fix_request_id: int
    store_name: str
    provider: Provider
    field: str
    field_label: str
    approved_value: Any
    manual_reason: str | None
    admin_url: str
    created_at: datetime


class AdminRequestInfo(CamelModel):
    id: int
    status: str
    display_status: AdminFilter
    created_at: datetime
    reject_reason: str | None
    decided_at: datetime | None
    fix_completed_at: datetime | None


class AdminOwner(CamelModel):
    user_id: int
    email: str


class AdminStore(CamelModel):
    id: int
    name: str
    status: str
    sources: StoreSources


class AdminRunRef(CamelModel):
    id: int
    status: str


class AdminRun(CamelModel):
    id: int
    kind: str
    status: str
    trigger: str
    created_at: datetime
    completed_at: datetime | None
    failure_rate: float | None  # JSON 숫자로(Decimal은 문자열이 됨)
    cost_usd: float


class AdminConnection(CamelModel):
    id: int
    provider: Provider
    status: str
    attention_reason: str | None
    invited_at: datetime | None
    invite_reminder_sent_at: datetime | None
    connected_at: datetime | None
    revoked_at: datetime | None


class AdminPlan(CamelModel):
    id: int
    provider: Provider
    version: int
    status: str
    last_error: str | None
    created_at: datetime
    approved_at: datetime | None


class AdminSchedule(CamelModel):
    id: int
    due_at: datetime
    status: str
    triggered_by: str


class AdminReport(CamelModel):
    id: int
    version: int
    status: str
    last_error: str | None
    created_at: datetime


class AdminRequestDetail(CamelModel):
    request: AdminRequestInfo
    owner: AdminOwner
    store: AdminStore
    base_run: AdminRunRef | None
    runs: list[AdminRun]
    connections: list[AdminConnection]
    plans: list[AdminPlan]
    manual_items: list[ManualItem]
    schedule: AdminSchedule | None
    reports: list[AdminReport]
