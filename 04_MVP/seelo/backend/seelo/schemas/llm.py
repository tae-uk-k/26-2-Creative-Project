"""LLM 구조화 출력 스키마(08 0.4). 규칙: 기본값 없음, 없는 값은 X | None, 자유 키 딕셔너리 없음,
선택지는 Literal, 중첩 3단계 이하, 이름 끝에 Out.
"""

from typing import Literal

from pydantic import BaseModel

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
AttributeKey = Literal[  # 08 0.1 조건 키(domain/attributes.py의 ATTRIBUTES와 같은 키)
    "vegetarian",
    "budget",
    "card_payment",
    "reservation",
    "takeout",
    "delivery",
    "kid_friendly",
    "group_friendly",
    "outdoor_seating",
    "alcohol",
    "wheelchair",
    "pet_friendly",
    "halal",
    "english_menu",
]


class IntervalOut(BaseModel):
    open: str  # "HH:MM"
    close: str  # "HH:MM", 자정 넘으면 다음 날 시각


class DayHoursOut(BaseModel):
    day: Day
    closed: bool
    intervals: list[IntervalOut]
    breaks: list[IntervalOut]


class WeeklyHoursOut(BaseModel):
    days: list[DayHoursOut]  # 텍스트에 나온 요일만
    notes: str | None


class MenuItemOut(BaseModel):
    name: str
    price: int | None  # 원. 숫자로 적혀 있을 때만
    description: str | None


class WebsiteExtractOut(BaseModel):
    hours_text: str | None  # 원문 그대로
    hours: WeeklyHoursOut | None
    menu: list[MenuItemOut]
    intro: str | None
    phone: str | None
    address: str | None


class EvidenceSiteOut(BaseModel):
    url: str
    site_name: str | None
    name: str | None
    address: str | None
    phone: str | None
    hours_text: str | None
    menu: list[MenuItemOut]
    instagram_url: str | None


class WebEvidenceExtractOut(BaseModel):
    sites: list[EvidenceSiteOut]


class ExtractedRecOut(BaseModel):
    name: str
    order: int  # 답변에서 처음 나온 순서(1부터)
    source_numbers: list[int]
    mentioned_attributes: list[AttributeKey]


class TargetClaimOut(BaseModel):
    field: Literal["hours", "location", "price", "phone"]
    value: str


class ExtractionOut(BaseModel):
    recommendations: list[ExtractedRecOut]
    target_claims: list[TargetClaimOut]


class ClaimResultOut(BaseModel):
    index: int  # 프롬프트의 [번호]
    claim_matches_truth: bool
    claim_matches_map: bool | None  # 지도 값이 없으면 null


class ClaimChecksOut(BaseModel):
    """AI가 틀리게 말함(08 6.4) 문장 비교. 여러 주장을 한 번에 비교한다."""

    results: list[ClaimResultOut]


class SentenceRefOut(BaseModel):
    text: str
    fact_ids: list[str]


class MenuTextOut(BaseModel):
    fact_id: str
    name_en: str
    description_en: str | None


class PlanTextsOut(BaseModel):
    """정비안 글(09 6.5). 지도별로 필요 없는 필드는 null·[]."""

    google_description: list[SentenceRefOut] | None
    kakao_intro: str | None
    menu_texts: list[MenuTextOut]
    kakao_tags: list[str]


class GeneratedQuestionOut(BaseModel):
    lang: Literal["en", "ko"]
    intent_type: Literal["basic", "conditional"]
    text: str
    text_ko: str | None


class GeneratedQuestionsOut(BaseModel):
    questions: list[GeneratedQuestionOut]
    region_en: str | None
