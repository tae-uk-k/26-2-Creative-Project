"""위임받은 상품 관리 화면의 읽기·입력·저장. 플랫폼 API나 비공개 상태를 사용하지 않는다."""

import asyncio
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from seelo.config import get_settings
from seelo.domain.commerce import check_fields, fingerprint, normalize_cafe24_browser_html
from seelo.integrations.browser.guards import AutomationBlocked, guard
from seelo.integrations.browser.session import BrowserSession
from seelo.integrations.commerce import CommerceApiError


def config_path(platform: str, external_id: str | None = None, shop_no: int = 1) -> Path:
    if platform not in {"cafe24", "smartstore"}:
        raise CommerceApiError("invalid_browser_shop")
    configured = get_settings().commerce_browser_config_dir
    if configured:
        root = Path(configured)
        if external_id is not None:
            if (
                not re.fullmatch(r"[a-z0-9_-]{2,50}", external_id)
                or not isinstance(shop_no, int)
                or shop_no < 1
            ):
                raise CommerceApiError("invalid_browser_shop")
            specific = root / platform / external_id / f"{shop_no}.yaml"
            if specific.exists():
                return specific
        shared = root / f"{platform}.yaml"
        if shared.exists():
            return shared
    return Path(__file__).with_name("selectors") / f"{platform}.yaml"


def load_config(platform: str, external_id: str | None = None, shop_no: int = 1) -> dict:
    try:
        config = yaml.safe_load(config_path(platform, external_id, shop_no).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CommerceApiError("selectors_missing") from error
    if not isinstance(config, dict) or not isinstance(config.get("fields"), dict):
        raise CommerceApiError("selectors_missing")
    return config


def configured_fields(platform: str, external_id: str | None = None, shop_no: int = 1) -> set[str]:
    """브라우저를 열지 않고 선택한 스토어 설정의 입력 칸을 반환한다."""
    try:
        config = load_config(platform, external_id, shop_no)
    except CommerceApiError:
        return set()
    return {key for key, spec in (config.get("fields") or {}).items() if (spec or {}).get("selector")}


def normalize(value: str) -> str:
    """스토어 식별값 비교용. 공백·유니코드 표기만 정리한다. 비슷한 이름을 같은 스토어로 보지 않는다."""
    return unicodedata.normalize("NFC", " ".join(str(value).split()))


class BrowserProduct:
    source = "browser"

    def __init__(
        self,
        platform: str,
        external_id: str,
        shop_no: int,
        *,
        config: dict | None = None,
        identity: dict | None = None,
    ):
        if platform not in {"cafe24", "smartstore"} or not re.fullmatch(r"[a-z0-9_-]{2,50}", external_id):
            raise CommerceApiError("invalid_browser_shop")
        self.platform, self.external_id, self.shop_no = platform, external_id, shop_no
        settings = get_settings()
        if config is None:
            config = load_config(platform, external_id, shop_no)
        self.cfg = config or {}
        # 운영자가 위임 목록에서 확인해 저장한 고유값. 없으면 등록한 스토어 ID를 기대값으로 쓴다.
        identity = identity or {}
        self.expected_values = {
            "external_id": external_id,
            "shop_no": str(shop_no),
            "store_name": identity.get("storeName") or external_id,
            "store_id": identity.get("storeId") or "",
        }
        # 고객 몰마다 세션을 분리한다. 고객 비밀번호는 저장하거나 입력하지 않는다.
        self.profile = str(
            Path(settings.commerce_browser_profile_root) / platform / external_id / str(shop_no)
        )

    @property
    def supported_fields(self) -> set[str]:
        return {key for key, spec in self.cfg.get("fields", {}).items() if spec.get("selector")}

    def edit_url(self, product_no: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,18}", product_no):
            raise CommerceApiError("invalid_product_id")
        if not all(self.cfg.get(key) for key in ("edit_url", "ready", "product_id", "name", "save")):
            raise CommerceApiError("selectors_missing")
        url = self.cfg["edit_url"].format(
            external_id=self.external_id, shop_no=self.shop_no, product_no=product_no
        )
        parsed = urlsplit(url)
        host = f"{self.external_id}.cafe24.com" if self.platform == "cafe24" else "sell.smartstore.naver.com"
        if parsed.scheme != "https" or parsed.netloc != host or parsed.username or parsed.password:
            raise CommerceApiError("invalid_admin_url")
        if not (self.cfg.get("saved_ready") or self.cfg.get("saved_alert")):
            raise CommerceApiError("selectors_missing")
        if not self.supported_fields or not self.cfg.get("protected"):
            raise CommerceApiError("selectors_missing")
        if self.platform == "smartstore" and not self.cfg.get("shop_identity"):
            raise CommerceApiError("shop_identity_required")
        return url

    async def _value(self, page: Any, spec: dict) -> str:
        if spec.get("url_regex"):
            match = re.fullmatch(spec["url_regex"], page.url)
            if not match:
                raise CommerceApiError("unexpected_screen")
            return match.group(1)
        locator = page.locator(spec["selector"])
        if spec.get("multiple"):
            return await locator.evaluate_all(
                "els => JSON.stringify(els.map(el => ({value: el.value, checked: el.checked})))"
            )
        if await locator.count() != 1:
            raise CommerceApiError("unexpected_screen")
        if spec.get("attribute"):
            return await locator.get_attribute(spec["attribute"]) or ""
        return await locator.evaluate(
            "el => ['checkbox', 'radio'].includes(el.type) ? "
            "JSON.stringify({value: el.value, checked: el.checked}) : "
            "('value' in el ? String(el.value) : "
            "(el.isContentEditable ? el.innerHTML : el.textContent)) || ''"
        )

    def expected(self, template: str) -> str:
        return normalize(template.format(**self.expected_values))

    def _identity_specs(self, page_spec: dict | None = None) -> list[dict]:
        specs = []
        source = page_spec if page_spec and page_spec.get("shop_identity") else self.cfg
        if source.get("shop_identity"):
            specs.append(source["shop_identity"])
        specs.extend(source.get("shop_identity_checks") or [])
        return specs

    async def _shop_matches(self, page: Any, page_spec: dict | None = None) -> bool:
        """고유 ID·URL·스토어 이름을 설정한 기대값과 정확히 대조한다. 추정하지 않는다."""
        for spec in self._identity_specs(page_spec):
            try:
                actual = normalize(await self._value(page, spec))
            except CommerceApiError:
                return False
            if actual != self.expected(spec.get("expected", "{external_id}")):
                return False
        shop_no = (page_spec or self.cfg).get("shop_no")
        if shop_no:
            # 카페24 다중 쇼핑몰: 최종 화면 주소의 쇼핑몰 번호가 등록한 번호와 같아야 한다.
            try:
                if (await self._value(page, shop_no)).strip() != str(self.shop_no):
                    return False
            except CommerceApiError:
                return False
        return True

    async def _switch_store(self, page: Any, ready: str) -> None:
        """위임 스토어 목록에서 기대값과 정확히 같은 한 곳만 고른다. 0곳·2곳 이상이면 멈춘다."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        spec = self.cfg["store_switch"]
        await page.locator(spec["open"]).first.click()
        items = page.locator(spec["item"])
        try:
            await items.first.wait_for(timeout=10000)
        except PlaywrightTimeoutError:
            raise CommerceApiError("shop_not_delegated") from None
        expected = self.expected(spec.get("expected", "{store_name}"))
        matches = []
        for index in range(await items.count()):
            item = items.nth(index)
            value = (
                await item.get_attribute(spec["attribute"])
                if spec.get("attribute")
                else await item.inner_text()
            )
            if normalize(value or "") == expected:
                matches.append(index)
        if not matches:
            # 권한이 회수됐거나 다른 계정에 로그인했다. 비슷한 이름을 대신 고르지 않는다.
            raise CommerceApiError("shop_not_delegated")
        if len(matches) > 1:
            raise CommerceApiError("shop_selection_ambiguous")
        await items.nth(matches[0]).click()
        await guard(page, self.platform, spec.get("ready") or ready)

    async def _ensure_store(self, page: Any, url: str, ready: str, page_spec: dict | None = None) -> None:
        """열린 관리 화면의 스토어를 확인하고, 설정한 경우에만 위임 목록에서 전환한다."""
        await guard(page, self.platform, ready)
        if await self._shop_matches(page, page_spec):
            return
        if not self.cfg.get("store_switch"):
            raise CommerceApiError("shop_identity_mismatch")
        await self._switch_store(page, ready)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await guard(page, self.platform, ready)
        if not await self._shop_matches(page, page_spec):
            raise CommerceApiError("shop_identity_mismatch")

    async def _identity(self, page: Any, product_no: str) -> str:
        await guard(page, self.platform, self.cfg["ready"])
        parsed = urlsplit(page.url)
        expected = urlsplit(self.edit_url(product_no))
        if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
            raise CommerceApiError("shop_identity_mismatch")
        actual_id = (await self._value(page, self.cfg["product_id"])).strip()
        if actual_id != product_no:
            raise CommerceApiError("product_identity_mismatch")
        if not await self._shop_matches(page):
            raise CommerceApiError("shop_identity_mismatch")
        name = (await self._value(page, self.cfg["name"])).strip()
        if not name:
            raise CommerceApiError("product_name_required")
        return name

    async def _editor(self, page: Any, spec: dict, value: str | None = None) -> str:
        opened = False
        if spec.get("open"):
            if spec.get("ready_frame"):
                await page.frame_locator(spec["ready_frame"]).locator("body").wait_for()
            button = page.locator(spec["open"])
            active = spec.get("opened")
            if not active or not await page.locator(active).count():
                await button.click()
                if active:
                    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

                    try:
                        await page.locator(active).wait_for(timeout=2000)
                    except PlaywrightTimeoutError:
                        # 카페24는 첫 클릭이 편집기 포커스만 줄 수 있다. 닫힌 상태 확인 후 한 번만 연다.
                        if await button.get_attribute("aria-pressed") != "false":
                            raise CommerceApiError("unexpected_screen") from None
                        await button.click()
                        await page.locator(active).wait_for(timeout=10000)
            opened = True
        await guard(page, self.platform, spec["selector"])
        if spec.get("select_all"):
            await page.locator(spec["selector"]).press("ControlOrMeta+A")
        current = await self._value(page, spec)
        if value is not None:
            if spec.get("attribute"):
                raise CommerceApiError("unsupported_browser_field")
            await page.locator(spec["selector"]).fill(value)
            await guard(page, self.platform, spec["selector"])
        if opened:
            await page.locator(spec.get("close") or spec["open"]).click()
        return current

    async def _snapshot(self, page: Any, product_no: str) -> dict:
        name = await self._identity(page, product_no)
        for action in self.cfg.get("prepare", []):
            if not await page.locator(action["ready"]).count():
                await page.locator(action["open"]).click()
            await guard(page, self.platform, action["ready"])
        fields = {
            key: await self._editor(page, self.cfg["fields"][key]) for key in sorted(self.supported_fields)
        }
        if self.platform == "cafe24" and "description" in fields:
            # Froala의 바깥·연속 문단 줄바꿈 차이를 정규화한다. 태그·속성·문구는 보존한다.
            fields["description"] = normalize_cafe24_browser_html(fields["description"])
        protected = {key: await self._value(page, spec) for key, spec in self.cfg["protected"].items()}
        return {
            "platform": self.platform,
            "external_id": self.external_id,
            "shop_no": self.shop_no,
            "product_no": product_no,
            "source_url": self.edit_url(product_no),
            "name": name,
            "fields": fields,
            "protected": protected,
        }

    def fields(self, raw: dict) -> dict[str, str]:
        return raw["fields"]

    def identity(self, raw: dict) -> tuple[str, str]:
        return raw["name"], raw["name"]

    async def fetch(self, product_no: str) -> dict:
        if sys.platform == "win32" and not isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
            return await asyncio.to_thread(
                lambda: asyncio.run(self.fetch(product_no), loop_factory=asyncio.ProactorEventLoop)
            )
        url = self.edit_url(product_no)
        try:
            async with BrowserSession(self.platform, profile_path=self.profile) as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._ensure_store(page, url, self.cfg["ready"])
                return await self._snapshot(page, product_no)
        except CommerceApiError:
            raise
        except AutomationBlocked as error:
            raise CommerceApiError(error.reason) from error
        except Exception as error:
            raise CommerceApiError("browser_read_failed") from error

    async def write(self, product_no: str, fresh: dict, changes: dict[str, str]) -> None:
        if sys.platform == "win32" and not isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
            return await asyncio.to_thread(
                lambda: asyncio.run(
                    self.write(product_no, fresh, changes), loop_factory=asyncio.ProactorEventLoop
                )
            )
        check_fields(self.platform, changes)
        if not set(changes).issubset(self.supported_fields):
            raise CommerceApiError("unsupported_browser_field")
        url = self.edit_url(product_no)
        sent = False
        try:
            async with BrowserSession(self.platform, profile_path=self.profile) as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._ensure_store(page, url, self.cfg["ready"])
                if fingerprint(await self._snapshot(page, product_no)) != fingerprint(fresh):
                    raise CommerceApiError("browser_source_changed")
                for key, value in changes.items():
                    await self._editor(page, self.cfg["fields"][key], value)
                await self._identity(page, product_no)
                for key, spec in self.cfg["protected"].items():
                    if await self._value(page, spec) != fresh["protected"][key]:
                        raise CommerceApiError("protected_field_changed")
                saved = asyncio.Event()
                unknown_dialog = False

                async def dialog_handler(dialog: Any) -> None:
                    nonlocal unknown_dialog
                    known = dialog.type == "alert" and bool(
                        re.fullmatch(self.cfg.get("saved_alert") or r"(?!)", dialog.message)
                    )
                    # 확인창을 수락하지 않는다. 관찰한 저장 안내에만 완료 표시를 남긴다.
                    await dialog.dismiss()
                    unknown_dialog = not known
                    saved.set()

                page.on("dialog", dialog_handler)
                sent = True
                await page.locator(self.cfg["save"]).click(timeout=15000)
                if self.cfg.get("saved_ready"):
                    await guard(page, self.platform, self.cfg["saved_ready"])
                else:
                    await asyncio.wait_for(saved.wait(), timeout=15)
                if unknown_dialog:
                    raise CommerceApiError("unexpected_dialog", uncertain=True)
                # 서비스의 별도 재조회로 반영을 판정한다. 저장 클릭은 재시도하지 않는다.
        except CommerceApiError:
            raise
        except AutomationBlocked as error:
            raise CommerceApiError(error.reason, uncertain=sent) from error
        except Exception as error:
            raise CommerceApiError("browser_write_failed", uncertain=sent) from error

    def catalog_url(self) -> str:
        spec = self.cfg.get("catalog") or {}
        if not all(spec.get(key) for key in ("url", "ready", "row", "product_id", "name")):
            raise CommerceApiError("catalog_not_configured")
        url = spec["url"].format(external_id=self.external_id, shop_no=self.shop_no)
        parsed = urlsplit(url)
        host = f"{self.external_id}.cafe24.com" if self.platform == "cafe24" else "sell.smartstore.naver.com"
        if parsed.scheme != "https" or parsed.netloc != host or parsed.username or parsed.password:
            raise CommerceApiError("invalid_admin_url")
        if self.platform == "smartstore" and not self._identity_specs(spec):
            raise CommerceApiError("shop_identity_required")
        return url

    async def _row_value(self, row: Any, spec: dict) -> str:
        locator = row.locator(spec["selector"]) if spec.get("selector") else row
        if await locator.count() < 1:
            return ""
        locator = locator.first
        value = (
            await locator.get_attribute(spec["attribute"])
            if spec.get("attribute")
            else await locator.inner_text()
        )
        value = value or ""
        if spec.get("regex"):
            match = re.search(spec["regex"], value)
            return match.group(1) if match else ""
        return value

    async def catalog(self, max_items: int = 500) -> dict:
        """위임받은 관리 화면의 상품 목록. 스토어를 먼저 대조하고 상품번호·이름만 읽는다."""
        if sys.platform == "win32" and not isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
            return await asyncio.to_thread(
                lambda: asyncio.run(self.catalog(max_items), loop_factory=asyncio.ProactorEventLoop)
            )
        url = self.catalog_url()
        spec = self.cfg["catalog"]
        items: dict[str, str] = {}
        skipped, pages, truncated = 0, 0, False
        try:
            async with BrowserSession(self.platform, profile_path=self.profile) as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._ensure_store(page, url, spec["ready"], spec)
                for _ in range(int(spec.get("max_pages", 20))):
                    pages += 1
                    rows = page.locator(spec["row"])
                    for index in range(await rows.count()):
                        row = rows.nth(index)
                        number = (await self._row_value(row, spec["product_id"])).strip()
                        name = normalize(await self._row_value(row, spec["name"]))
                        if not re.fullmatch(r"[1-9][0-9]{0,18}", number) or not name:
                            skipped += 1
                            continue
                        items.setdefault(number, name)
                        if len(items) >= max_items:
                            truncated = True
                            break
                    nxt = page.locator(spec["next"]) if spec.get("next") else None
                    if truncated or nxt is None or not await nxt.count() or await nxt.first.is_disabled():
                        break
                    await nxt.first.click()
                    await guard(page, self.platform, spec["ready"])
                    # 페이지 이동 뒤에도 같은 스토어인지 다시 확인한다.
                    if not await self._shop_matches(page, spec):
                        raise CommerceApiError("shop_identity_mismatch")
        except CommerceApiError:
            raise
        except AutomationBlocked as error:
            raise CommerceApiError(error.reason) from error
        except Exception as error:
            raise CommerceApiError("browser_read_failed") from error
        return {
            "items": [{"productNo": k, "name": v} for k, v in items.items()],
            "pages": pages,
            "skipped": skipped,
            "truncated": truncated,
        }
