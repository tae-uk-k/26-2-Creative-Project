"""무료 진단 결과(04 6장, 14 1.4). 고쳐야 할 점은 개수만 — 내용 필드를 이 모델에 더하지 않는다(W-06-2)."""

from datetime import datetime
from typing import Literal

from seelo.schemas.common import AiProviderT, CamelModel, DomainCount, ProviderRates


class QuestionCount(CamelModel):
    appearance_count: int
    success_count: int


class QuestionProviders(CamelModel):
    openai: QuestionCount | None  # None = 측정하지 못함
    gemini: QuestionCount | None


class DiagnosisQuestion(CamelModel):
    order_no: int
    lang: Literal["en", "ko"]
    text: str
    text_ko: str | None
    providers: QuestionProviders


class NamedRates(CamelModel):
    name: str
    providers: ProviderRates


class Competitor(NamedRates):
    rank_order: int


class DiagnosisSources(CamelModel):
    top: list[DomainCount]
    target_sources: list[DomainCount]


class MeasureConditions(CamelModel):
    question_count: int
    repeat_count: int
    providers: list[AiProviderT]
    measured_at: datetime


class DiagnosisResponse(CamelModel):
    run_id: int
    store_id: int
    store_name: str
    measured_at: datetime
    providers: ProviderRates
    target: NamedRates
    competitors: list[Competitor]
    questions: list[DiagnosisQuestion]
    sources: DiagnosisSources
    findings_count: int  # 고쳐야 할 점은 개수만. 내용 필드를 이 모델에 추가하지 않는다
    conditions: MeasureConditions
