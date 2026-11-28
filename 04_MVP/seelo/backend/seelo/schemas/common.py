"""API 공통 스키마(14 1.1). 필드는 snake_case, JSON은 camelCase."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


Provider = Literal["google", "kakao"]
LoginProvider = Literal["email", "google", "kakao"]
AiProviderT = Literal["openai", "gemini"]
SourceMark = Literal["found", "not_found", "candidate"]
CategoryT = Literal["restaurant", "cafe", "bar"]
StoreStatusT = Literal["collecting", "collected", "measuring", "diagnosed", "measure_failed", "archived"]
ConnectionStatusT = Literal["not_connected", "invited", "connected", "needs_attention", "revoked"]


class RateSummary(CamelModel):
    success_count: int
    appearance_count: int
    rate: float | None  # 0~1, 소수점 4자리
    avg_rank: float | None  # 소수점 1자리


class ProviderRates(CamelModel):
    openai: RateSummary
    gemini: RateSummary


class StoreSources(CamelModel):
    google: SourceMark
    kakao: SourceMark
    naver: SourceMark
    website: SourceMark
    instagram: SourceMark


class StoreSummary(CamelModel):
    id: int
    name: str
    address: str | None
    category: CategoryT
    status: StoreStatusT
    sources: StoreSources


class DomainCount(CamelModel):
    domain: str
    count: int


class Page[T](CamelModel):
    items: list[T]
    page: int
    page_size: int
    total: int
