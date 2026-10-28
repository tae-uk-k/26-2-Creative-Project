"""관리 화면 조작 공통 엔진(09 8.4). 화면 요소 위치는 코드에 적지 않고 `selectors/{provider}.yaml`에서 읽는다.

- 지금 다루는 칸: 입력 칸 하나로 고치는 칸(text·url·phone). 영업시간·메뉴처럼 입력이 복잡한 칸은
  PoC로 실제 화면을 본 뒤 지도별 클래스에 `_write_hours` 등으로 더한다. 그 전에는 FieldWriteFailed
  (→ 그 칸 manual_required write_failed, 16 5장).
- 셀렉터 파일이 비어 있으면(PoC 전) 화면을 열지 않고 AutomationBlocked("selectors_missing") → 수동 처리.
- 모든 이동·클릭·저장 뒤 guard()(로그인·캡차·보안 확인·예상 밖 화면이면 즉시 멈춤). 무작위 대기 없음.
- 읽기는 늘 정보 화면을 새로 불러 읽는다(쓰기 직후 다시 읽기가 화면 캐시를 보지 않게).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from seelo.config import get_settings
from seelo.domain.field_dictionary import spec
from seelo.domain.normalize import same_name
from seelo.integrations.browser import ReadValue, StoreRef
from seelo.integrations.browser.guards import (
    READY_TIMEOUT_MS,
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
    TransientAutomationError,
    guard,
)

SELECTORS_DIR = Path(__file__).resolve().parent / "selectors"
NAV_TIMEOUT_MS = 30_000
SINGLE_TYPES = {"text", "url", "phone"}  # 입력 칸 하나로 읽고 쓰는 칸
_VALUE_JS = "e => ('value' in e) ? e.value : e.textContent"  # 입력 칸이면 값, 아니면 글자


@dataclass(frozen=True)
class FieldScreen:
    read: str
    input: str | None = None
    open_editor: str | None = None
    save: str | None = None
    saved_ready: str | None = None
    review_badge: str | None = None


@dataclass(frozen=True)
class ScreenConfig:
    provider: str
    login_url: str | None = None
    logged_in: str | None = None
    store_list_url: str | None = None
    store_list_ready: str | None = None
    info_url_template: str | None = None  # "{external_ref}"가 들어 있다
    info_ready: str | None = None
    not_found: str | None = None
    row: str | None = None
    row_name: str | None = None
    row_link: str | None = None
    external_ref_pattern: str | None = None  # 정보 화면 주소에서 위치 식별값(그룹 1)
    attention: dict[str, str] = field(default_factory=dict)  # 사유 → 그 표시 셀렉터
    fields: dict[str, FieldScreen] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """PoC로 정보 화면과 가게 찾는 방법을 채웠는가."""
        can_find = bool(self.info_url_template) or bool(self.store_list_url and self.row and self.row_link)
        return bool(self.info_ready) and can_find


def _blank(v: Any) -> str | None:
    return str(v) if v not in (None, "") else None


def parse_screen_config(provider: str, raw: dict[str, Any]) -> ScreenConfig:
    pages = raw.get("pages") or {}
    lst, info = pages.get("store_list") or {}, pages.get("info") or {}
    search, login = raw.get("store_search") or {}, raw.get("login") or {}
    fields = {}
    for key, f in (raw.get("fields") or {}).items():
        if f and _blank(f.get("read")):
            fields[key] = FieldScreen(**{k: _blank(v) for k, v in f.items()})  # type: ignore[arg-type]
    return ScreenConfig(
        provider=provider,
        login_url=_blank(login.get("url")),
        logged_in=_blank(login.get("logged_in")),
        store_list_url=_blank(lst.get("url")),
        store_list_ready=_blank(lst.get("ready")),
        info_url_template=_blank(info.get("url_template")),
        info_ready=_blank(info.get("ready")),
        not_found=_blank(info.get("not_found")),
        row=_blank(search.get("row")),
        row_name=_blank(search.get("name")),
        row_link=_blank(search.get("link")),
        external_ref_pattern=_blank(search.get("external_ref")),
        attention={k: v for k, v in (raw.get("attention") or {}).items() if _blank(v)},
        fields=fields,
    )


def load_screen_config(provider: str, path: Path | None = None) -> ScreenConfig:
    p = path or SELECTORS_DIR / f"{provider}.yaml"
    return parse_screen_config(provider, yaml.safe_load(p.read_text(encoding="utf-8")) or {})


class ScreenAdmin:
    """MapAdmin 구현(브라우저). page는 열린 Playwright 페이지(영구 프로필 세션 또는 테스트 컨텍스트)."""

    def __init__(self, page: Any, config: ScreenConfig) -> None:
        self.page = page
        self.cfg = config
        self.provider = config.provider
        self._info_url: str | None = None
        page.set_default_timeout(READY_TIMEOUT_MS)

    # --- 공통 동작 ---
    async def _guard(self, ready: str | None, *, not_found: str | None = None) -> None:
        if not ready:
            raise AutomationBlocked("selectors_missing")
        await guard(self.page, self.provider, ready, not_found=not_found)

    async def _goto(self, url: str) -> None:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except PlaywrightTimeoutError as e:
            raise TransientAutomationError("goto_timeout") from e
        except PlaywrightError as e:
            if "net::" in str(e):
                raise TransientAutomationError("network") from e
            raise

    async def _click(self, selector: str) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        try:
            await self.page.locator(selector).first.click()
        except PlaywrightTimeoutError as e:
            raise AutomationBlocked("unexpected_screen") from e

    async def _check_attention(self) -> None:
        for reason, selector in self.cfg.attention.items():
            if await self.page.locator(selector).count() > 0:
                raise AttentionNeeded(reason)

    def _ref_from_url(self, url: str) -> str:
        if self.cfg.external_ref_pattern:
            m = re.search(self.cfg.external_ref_pattern, url)
            if m:
                return m.group(1)
        return url

    async def _open_info(self) -> None:
        if self._info_url is None:
            raise RuntimeError("open_store first")
        await self._goto(self._info_url)
        await self._guard(self.cfg.info_ready, not_found=self.cfg.not_found)

    # --- MapAdmin ---
    async def open_store(self, store: StoreRef, external_ref: str | None) -> str:
        if not self.cfg.usable:
            raise AutomationBlocked("selectors_missing")
        if external_ref and self.cfg.info_url_template:
            self._info_url = self.cfg.info_url_template.format(external_ref=external_ref)
            await self._open_info()
        else:
            await self._find_in_list(store)
        await self._check_attention()
        return external_ref or self._ref_from_url(self.page.url)

    async def _find_in_list(self, store: StoreRef) -> None:
        if not (self.cfg.store_list_url and self.cfg.row and self.cfg.row_link):
            raise AutomationBlocked("selectors_missing")
        await self._goto(self.cfg.store_list_url)
        await self._guard(self.cfg.store_list_ready or self.cfg.row)
        rows = self.page.locator(self.cfg.row)
        threshold = get_settings().name_similarity_threshold
        for i in range(await rows.count()):
            row = rows.nth(i)
            name_el = row.locator(self.cfg.row_name).first if self.cfg.row_name else row
            if same_name((await name_el.inner_text()).strip(), store.name, threshold):
                await row.locator(self.cfg.row_link).first.click()
                await self._guard(self.cfg.info_ready, not_found=self.cfg.not_found)
                self._info_url = self.page.url
                return
        raise StoreNotVisible()

    async def read_fields(self, fields: list[str]) -> dict[str, ReadValue]:
        """다룰 수 있는 칸만 돌려준다(셀렉터가 없는 칸은 빠짐 → 지금 값 null)."""
        await self._open_info()
        out: dict[str, ReadValue] = {}
        for f in fields:
            sp, fs = spec(self.provider, f), self.cfg.fields.get(f)
            if sp is None or fs is None or sp.type not in SINGLE_TYPES:
                continue
            el = self.page.locator(fs.read)
            raw = await el.first.evaluate(_VALUE_JS) if await el.count() else None
            pending = bool(fs.review_badge) and await self.page.locator(fs.review_badge).count() > 0
            value = (str(raw).strip() or None) if raw is not None else None
            out[f] = ReadValue(value=value, pending_review=pending)
        return out

    async def write_field(self, field_: str, value: object) -> None:
        sp, fs = spec(self.provider, field_), self.cfg.fields.get(field_)
        if sp is None or fs is None or sp.type not in SINGLE_TYPES or not (fs.input and fs.save):
            raise FieldWriteFailed("unsupported_field")
        if fs.open_editor:
            await self._click(fs.open_editor)
            await self._guard(fs.input)
        await self.page.locator(fs.input).first.fill(str(value))
        await self._click(fs.save)
        await self._guard(fs.saved_ready or self.cfg.info_ready)
