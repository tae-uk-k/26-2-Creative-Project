"""전후 비교 보고서 계약(10 3.2, 04 7.4)."""

from datetime import datetime
from typing import Any, Literal

from seelo.schemas.common import CamelModel, ProviderRates, RateSummary
from seelo.schemas.diagnosis import QuestionProviders


class RateComparison(CamelModel):
    before: RateSummary
    after: RateSummary
    rate_delta_pp: float | None


class Position(CamelModel):
    position: int
    total: int


class ReportSummary(CamelModel):
    providers: dict[str, RateComparison]
    competitor_position: dict[str, Position]
    no_change: bool
    headline: str


class ComparedCompetitor(CamelModel):
    name: str
    before: ProviderRates
    after: ProviderRates


class NewCompetitor(CamelModel):
    name: str
    after: ProviderRates


class ComparedTarget(CamelModel):
    before: ProviderRates
    after: ProviderRates


class ReportCompetitors(CamelModel):
    before_top5: list[ComparedCompetitor]
    new_top5_after: list[NewCompetitor]
    target: ComparedTarget


class ReportQuestion(CamelModel):
    order_no: int
    lang: Literal["en", "ko"]
    text: str
    text_ko: str | None
    before: QuestionProviders
    after: QuestionProviders
    excluded_providers: list[str]


class ChangeView(CamelModel):
    provider: Literal["google", "kakao"]
    field: str
    field_label: str
    before_value: Any
    applied_value: Any
    status: str
    method: str
    verified_at: datetime | None
    remeasure_match: Literal["match", "differs", "unknown"]
    note: str | None = None


class ReportConditions(CamelModel):
    question_set_id: int
    repeat_count: int
    providers: list[str]
    models: dict[str, dict[str, str | None]]


class ReportContent(CamelModel):
    schema_version: Literal[1] = 1
    measured_at: dict[str, datetime]
    fix_completed_at: datetime
    interval_days: int
    early_remeasure: bool
    summary: ReportSummary
    competitors: ReportCompetitors
    questions: list[ReportQuestion]
    sources: dict[str, Any]
    changes: list[ChangeView]
    conditions: ReportConditions
    notices: list[str]


class ReportResponse(CamelModel):
    report_id: int
    fix_request_id: int
    version: int
    created_at: datetime
    content: ReportContent
