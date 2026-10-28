"""가짜 지도 관리 화면(11 3장, 17 1장). 가짜 모드와 테스트가 같은 클래스를 쓴다.

- 칸 값을 메모리에 둔다. 쓰면 바로 읽힌다(reflect 지연을 켜면 pending으로 남음).
- 상황 만들기: block_on(칸 또는 "open"/"read"), transient_on(칸, 횟수), not_visible(), needs_attention(사유),
  delay_reflection(칸), fail_write(칸, 사유). 열기·읽기·쓰기 순서를 events에 남긴다.
- before_write: 쓰기 직전에 부르는 함수(테스트가 그 순간 DB의 before_value가 이미 커밋됐는지 본다).
- 가짜 모드 FAKE_MAP_BEHAVIOR: block이면 첫 쓰기에서 AutomationBlocked, reflect_delay면 모든 쓰기가 반영 대기.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from seelo.integrations.browser import ReadValue, StoreRef
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
    TransientAutomationError,
)


@dataclass
class FakeMapAdmin:
    provider: str
    values: dict[str, Any] = field(default_factory=dict)
    visible: bool = True
    attention: str | None = None
    blocked: set[str] = field(default_factory=set)
    block_first_write: bool = False
    transient: dict[str, int] = field(default_factory=dict)
    delayed: set[str] = field(default_factory=set)
    delay_all: bool = False
    pending: dict[str, Any] = field(default_factory=dict)
    write_fail: dict[str, str] = field(default_factory=dict)
    events: list[tuple[Any, ...]] = field(default_factory=list)
    before_write: Callable[[str], Awaitable[None]] | None = None

    # --- 상황 만들기 ---
    def block_on(self, key: str = "open") -> None:
        self.blocked.add(key)

    def transient_on(self, key: str, times: int = 1) -> None:
        self.transient[key] = times

    def not_visible(self) -> None:
        self.visible = False

    def needs_attention(self, reason: str) -> None:
        self.attention = reason

    def delay_reflection(self, key: str) -> None:
        self.delayed.add(key)

    def fail_write(self, key: str, reason: str = "unsupported_field") -> None:
        """그 칸 쓰기가 FieldWriteFailed(셀렉터를 정하지 못한 칸·API가 받지 않는 값)."""
        self.write_fail[key] = reason

    def reflect(self, key: str) -> None:
        """반영 대기 중인 값을 화면에 반영한다(시간이 지나 지도에 반영된 것처럼)."""
        if key in self.pending:
            self.values[key] = self.pending.pop(key)

    def _check(self, key: str) -> None:
        if key in self.blocked:
            raise AutomationBlocked("security_check")
        if self.transient.get(key, 0) > 0:
            self.transient[key] -= 1
            raise TransientAutomationError(key)
        if not self.visible:
            raise StoreNotVisible()

    # --- MapAdmin ---
    async def open_store(self, store: StoreRef, external_ref: str | None) -> str:
        self.events.append(("open", store.store_id))
        self._check("open")
        if self.attention:
            raise AttentionNeeded(self.attention)
        return external_ref or f"fake-{self.provider}-{store.store_id}"

    async def read_fields(self, fields: list[str]) -> dict[str, ReadValue]:
        self.events.append(("read", tuple(fields)))
        self._check("read")
        return {f: ReadValue(self.values.get(f), f in self.pending) for f in fields}

    async def write_field(self, field_: str, value: object) -> None:
        if self.before_write is not None:
            await self.before_write(field_)
        self.events.append(("write", field_))
        if field_ in self.write_fail:
            raise FieldWriteFailed(self.write_fail[field_])
        if self.block_first_write:
            self.block_first_write = False
            raise AutomationBlocked("security_check")
        self._check(field_)
        if self.delay_all or field_ in self.delayed:
            self.pending[field_] = value
        else:
            self.values[field_] = value


@dataclass
class FakeMapAdmins:
    """Clients.map_admin 자리: map_admin("google") → async with → FakeMapAdmin."""

    admins: dict[str, FakeMapAdmin] = field(
        default_factory=lambda: {p: FakeMapAdmin(provider=p) for p in ("google", "kakao")}
    )
    opened: list[str] = field(default_factory=list)

    def __call__(self, provider: str) -> AbstractAsyncContextManager[FakeMapAdmin]:
        return self._session(provider)

    @asynccontextmanager
    async def _session(self, provider: str) -> AsyncIterator[FakeMapAdmin]:
        self.opened.append(provider)
        yield self.admins[provider]

    def __getitem__(self, provider: str) -> FakeMapAdmin:
        return self.admins[provider]


def fake_map_admins(behavior: str = "normal") -> FakeMapAdmins:
    admins = FakeMapAdmins()
    for a in admins.admins.values():
        a.block_first_write = behavior == "block"
        a.delay_all = behavior == "reflect_delay"
    return admins
