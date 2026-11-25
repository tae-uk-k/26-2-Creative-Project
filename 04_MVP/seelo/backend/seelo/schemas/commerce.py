"""쇼핑몰 API 계약. 판매자 비밀번호·개인용 앱 키는 입력받지 않는다."""

from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from seelo.schemas.common import CamelModel

Platform = Literal["cafe24", "smartstore"]
FactKey = Literal[
    "purpose",
    "model",
    "material",
    "size",
    "weight",
    "components",
    "power",
    "compatibility",
    "care",
    # 식품·건강식품. 함량·섭취량은 단위와 출처(인용문)를 함께 검사한다. 효능·인증·후기 키는 두지 않는다.
    "ingredients",
    "nutrition",
    "serving",
    "allergens",
    "origin",
    "storage",
    "manufacturer",
]


class CommerceInput(CamelModel):
    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"], populate_by_name=True, extra="forbid"
    )


class ShopCreate(CommerceInput):
    """스토어 주소만 받아도 서버가 플랫폼·스토어 ID·쇼핑몰 번호를 판별한다.

    연결 도메인처럼 주소로 판별할 수 없을 때만 platform·externalId를 직접 받는다.
    """

    store_url: str | None = Field(default=None, min_length=1, max_length=2048)
    platform: Platform | None = None
    external_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{1,49}$")
    shop_no: int | None = Field(default=None, ge=1, le=1000)
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("external_id")
    @classmethod
    def mall_id(cls, value: str | None) -> str | None:
        if value is not None and ".." in value:
            raise ValueError("mall_id_invalid")
        return value

    @model_validator(mode="after")
    def target(self) -> "ShopCreate":
        if self.store_url is None and (self.platform is None or self.external_id is None):
            raise ValueError("store_url_or_platform_and_external_id_required")
        return self


class ManagerStatus(CommerceInput):
    status: Literal["invited", "verified", "revoked"]
    # 운영자가 위임 목록에서 직접 확인한 고유값. 가게 선택에 그대로 대조한다(AI 추정 금지).
    store_name: str | None = Field(default=None, min_length=1, max_length=100)
    store_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,100}$")


class SellerLink(CommerceInput):
    account_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_@.-]+$")


class ProductNo(CommerceInput):
    external_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")


class ProductImport(CommerceInput):
    """상품번호 또는 카페24 상품 주소. 스마트스토어 공개 주소의 번호는 원상품번호가 아니므로 받지 않는다."""

    external_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")
    product_url: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def one_target(self) -> "ProductImport":
        if (self.external_id is None) == (self.product_url is None):
            raise ValueError("external_id_or_product_url_required")
        return self


class ManualSnapshot(ProductNo):
    name: str = Field(min_length=1, max_length=250)
    identity: str = Field(min_length=1, max_length=250)
    fields: dict[str, str] = Field(max_length=12)


class FactInput(CommerceInput):
    key: FactKey
    value: str = Field(min_length=1, max_length=1000)
    identity: str = Field(min_length=1, max_length=250)
    source_url: str = Field(min_length=1, max_length=2048)
    quote: str = Field(min_length=1, max_length=4000)


class FactsInput(CommerceInput):
    facts: list[FactInput] = Field(max_length=30)


class ResearchInput(CommerceInput):
    source_urls: list[str] = Field(default_factory=list, max_length=3)


class ExtractedFact(CommerceInput):
    key: FactKey
    value: str = Field(min_length=1, max_length=1000)
    identity: str = Field(min_length=1, max_length=250)
    source_index: int = Field(ge=0, le=3)
    quote: str = Field(min_length=1, max_length=4000)


class FactExtraction(CommerceInput):
    facts: list[ExtractedFact] = Field(max_length=30)


class PlanCreate(CommerceInput):
    # 비우면 서버가 정한다. 필드는 현재 실행기가 자동 저장하는 항목 중 권장 범위, 필수 사실은 AI 판단.
    fields: list[str] | None = Field(default=None, min_length=1, max_length=8)
    required_facts: list[FactKey] | None = Field(default=None, max_length=16)
    use_ai: bool = True
    allow_editor_conversion: bool = False


class AnswerInput(CommerceInput):
    answers: dict[FactKey, str] = Field(min_length=1, max_length=3)


class PlanApprove(CommerceInput):
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fields: list[str] | None = Field(default=None, min_length=1, max_length=8)
    editor_conversion_confirmed: bool = False


class FactOrder(CommerceInput):
    """AI는 근거 ID의 순서만 선택한다. 상품 사양을 자유 생성하지 않는다."""

    fact_keys: list[FactKey] = Field(min_length=1, max_length=16)


class FactNeeds(CommerceInput):
    """AI는 구매 판단에 필요한 사실 종류만 고른다. 값을 만들지 않는다."""

    required: list[FactKey] = Field(max_length=8)


class MeasureQuery(CommerceInput):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,20}$")
    family: str = Field(default="general", pattern=r"^[a-z_]{1,30}$")
    question: str = Field(min_length=5, max_length=500)


class MeasureSetCreate(CommerceInput):
    """고정 질문 세트. 질문에 대상 상품명·상품 URL을 넣지 않는다(자연 발견 측정)."""

    name: str = Field(min_length=1, max_length=100)
    queries: list[MeasureQuery] = Field(min_length=1, max_length=20)
    common_suffix: str | None = Field(default=None, min_length=5, max_length=500)
    target_names: list[str] = Field(default_factory=list, max_length=5)
    target_urls: list[str] = Field(default_factory=list, max_length=5)


class MeasureRunCreate(CommerceInput):
    label: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    provider: Literal["openai", "gemini"]
    repeats: int = Field(default=3, ge=1, le=5)


class PrepareInput(CommerceInput):
    source_urls: list[str] = Field(default_factory=list, max_length=3)


class PublicationCheck(CommerceInput):
    pc_url: str = Field(min_length=1, max_length=2048)
    mobile_url: str = Field(min_length=1, max_length=2048)
    pc_matches: bool
    mobile_matches: bool
    note: str = Field(min_length=1, max_length=1000)


class ManualResult(CommerceInput):
    values: dict[str, str] = Field(min_length=1, max_length=8)
    note: str = Field(min_length=1, max_length=1000)
