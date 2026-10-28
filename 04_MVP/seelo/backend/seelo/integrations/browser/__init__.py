"""지도 관리 화면 조작 인터페이스(09 8.4). 구현은 13단계(google_admin·kakao_partner·gbp_api).
가짜는 integrations/fake_admin.py.

- 쓰기는 사장님이 초대한 가게(연결 connected)의 승인한 칸만(09 8.1). 코드는 로그인하지 않는다.
- 예외(AutomationBlocked·TransientAutomationError·StoreNotVisible·AttentionNeeded)는 guards.py.
- Playwright는 정비 워커 이미지에만 있다(의존성 그룹 browser). 이 패키지는 Playwright를 바로 불러오지 않는다.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StoreRef:
    """관리 화면에서 가게를 찾을 단서. 카카오 값은 저장하지 않으므로 장소 id만 넘긴다."""

    store_id: int
    name: str
    address: str | None
    google_place_id: str | None
    kakao_place_id: str | None


@dataclass
class ReadValue:
    value: Any  # 칸 type 형식(09 3장)
    pending_review: bool  # 화면에 "검토 중"류 표시가 있으면 참 [PoC]


class MapAdmin(Protocol):
    async def open_store(self, store: StoreRef, external_ref: str | None) -> str:
        """가게 정보 편집 화면을 연다. external_ref를 돌려준다. 못 찾으면 StoreNotVisible."""
        ...

    async def read_fields(self, fields: list[str]) -> dict[str, ReadValue]: ...

    async def write_field(self, field: str, value: object) -> None: ...
