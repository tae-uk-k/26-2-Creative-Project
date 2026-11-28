"""가게 요청·응답(04 5.2, 14 1.3)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from seelo.schemas.common import CamelModel, StoreSummary


class IdentifyRequest(CamelModel):
    name: str = Field(min_length=1, max_length=50)
    link: str = Field(min_length=1, max_length=2000)
    mode: Literal["new", "change"]
    confirm_replace: bool = False

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise PydanticCustomError("required", "가게 이름을 넣어 주세요")
        return v


class IdentifyConfirmed(CamelModel):
    result: Literal["confirmed"] = "confirmed"
    store_id: int
    run_id: int | None
    next: str


class Candidate(CamelModel):
    candidate_id: str
    name: str
    address: str | None
    category: str | None
    providers: list[Literal["google", "kakao", "naver"]]


class IdentifyCandidates(CamelModel):
    result: Literal["candidates"] = "candidates"
    candidate_token: str
    candidates: list[Candidate]


IdentifyResult = Annotated[IdentifyConfirmed | IdentifyCandidates, Field(discriminator="result")]


class IdentifySelectRequest(CamelModel):
    candidate_token: str = Field(max_length=200)
    candidate_id: str = Field(max_length=200)


class CurrentStoreResponse(CamelModel):
    store: StoreSummary | None


class HistoryItem(CamelModel):
    store_id: int
    name: str
    archived_at: datetime
    diagnosis_run_id: int | None
    report_id: int | None


class HistoryResponse(CamelModel):
    stores: list[HistoryItem]


class NotMineRequest(CamelModel):
    run_id: int
