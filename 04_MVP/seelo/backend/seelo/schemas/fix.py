"""자동 정비(04 7장, 14 1.5). 신청(S12, 9단계)·연결(S15, 10단계)·정비안(S13, 11단계). 보고서는 14단계."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from seelo.schemas.common import AiProviderT, CamelModel, ConnectionStatusT, Provider, ProviderRates

StepKey = Literal["received", "approved", "connect", "review", "fixing", "remeasure_waiting", "report"]


class FixStep(CamelModel):
    key: StepKey
    state: Literal["done", "current", "todo"]
    action_path: str | None


class FixRequestView(CamelModel):
    id: int
    status: str
    created_at: datetime
    reject_reason: str | None
    has_base_run: bool  # false면 "신청이 승인되면 측정부터 다시 진행해요"
    steps: list[FixStep]
    remeasure_due_date: date | None
    report_id: int | None


class FixRequestState(CamelModel):
    request: FixRequestView | None
    can_request: bool  # 03 7장 can_request_fix
    needs_measurement_first: bool  # 가게가 collected


class CreatedRequest(CamelModel):
    request_id: int


class ConnectionView(CamelModel):
    provider: Provider
    status: ConnectionStatusT
    attention_reason: str | None
    invited_at: datetime | None
    invite_not_arrived: bool  # status=invited이고 초대 미도착 메일을 보냄
    store_found_on_map: bool  # 그 지도에서 가게를 찾음. false면 화면이 등록 방법 안내
    can_invite: bool  # not_connected·needs_attention·revoked


class SeeloAccounts(CamelModel):
    google: str
    kakao: str


class ConnectState(CamelModel):
    request_id: int
    seelo_accounts: SeeloAccounts
    google: ConnectionView
    kakao: ConnectionView


# --- 정비안(S13, 04 7.3, 11단계) ---------------------------------------------------------------


class PlanListItem(CamelModel):
    plan_id: int
    provider: Provider
    status: Literal["generating", "generation_failed", "awaiting_approval", "approved"]
    version: int


class PlanList(CamelModel):
    plans: list[PlanListItem]


class Position(CamelModel):
    position: int
    total: int


class PlanSummary(CamelModel):
    providers: ProviderRates
    competitor_position: Position
    item_counts: dict[Provider, int]
    connections: dict[Provider, ConnectionStatusT]


class PlanFinding(CamelModel):
    finding_id: int
    category: str
    category_label: str
    title: str
    provider: Provider
    field: str
    question_count: int
    competitor_count: int
    priority: int
    related_response_ids: list[int]
    item_id: int | None


class ItemConstraints(CamelModel):
    type: Literal["text", "hours", "url", "phone", "menu", "attributes", "links", "services", "tags"]
    max_length: int | None = None
    max_items: int | None = None


class ItemResult(CamelModel):
    status: Literal[
        "queued", "applied", "pending_reflection", "manual_required", "manual_done", "disconnected"
    ]
    status_label: str
    applied_at: datetime | None
    verified_at: datetime | None


class PlanItem(CamelModel):
    item_id: int
    order_no: int
    field: str
    field_label: str
    current_value: Any
    proposed_value: Any
    approved_value: Any
    reason: str | None
    finding_ids: list[int]
    needs_owner_input: bool
    sensitive: bool
    owner_confirmed: bool
    owner_edited: bool
    excluded: bool
    constraints: ItemConstraints
    result: ItemResult | None


class OwnerOnlyField(CamelModel):
    field: Literal["name", "address", "category", "phone"]
    guide: str


class PlanDetail(CamelModel):
    plan_id: int
    provider: Provider
    status: str
    version: int
    created_at: datetime
    approved_at: datetime | None
    read_only: bool
    summary: PlanSummary
    findings: list[PlanFinding]
    items: list[PlanItem]
    owner_only_fields: list[OwnerOnlyField]
    map_not_found: bool


class EvidenceAnswer(CamelModel):
    response_id: int
    provider: AiProviderT
    repeat_no: int
    raw_text: str
    highlight_names: list[str]


class EvidenceQuestion(CamelModel):
    order_no: int
    text: str
    answers: list[EvidenceAnswer]


class PlanEvidence(CamelModel):
    questions: list[EvidenceQuestion]


class ApproveItem(CamelModel):
    item_id: int
    excluded: bool
    approved_value: Any = (
        None  # 키가 "있으면" 사장님 값(null이어도 "비움"). 있는지는 model_fields_set으로 본다
    )
    owner_confirmed: bool | None = None


class ApproveRequest(CamelModel):
    items: list[ApproveItem] = Field(max_length=200)


class ApproveResponse(CamelModel):
    plan_id: int
    status: Literal["approved"]
