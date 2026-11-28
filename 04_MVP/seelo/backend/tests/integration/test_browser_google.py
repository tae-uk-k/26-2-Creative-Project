"""W-09-5 로컬 HTML(Google): 화면 조작 엔진·차단 감지를 진짜 브라우저(Playwright)로 시험한다.

tests/browser_site.py는 흉내 낸 화면이다. PoC로 실제 관리 화면 HTML을 저장하면
같은 방식으로 셀렉터를 시험한다.
Playwright·Chromium이 없으면 건너뛴다.
"""

import dataclasses
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations import get_clients, set_clients
from seelo.integrations.browser import StoreRef
from seelo.integrations.browser import guards as guards_mod
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
)
from seelo.integrations.browser.screen import load_screen_config
from seelo.models.fix import FixLog
from seelo.services import fix_apply_service
from tests.browser_site import AdminSite, open_admin
from tests.map_world import approved_plan, seed_plan_world

pytest.importorskip("playwright.async_api")
REF = StoreRef(store_id=1, name="데모식당", address=None, google_place_id="G1", kakao_place_id=None)


def _site(**kw: Any) -> AdminSite:
    return AdminSite("google", values={"description": "옛 소개", "website": "https://old.example/"}, **kw)


async def test_open_from_list_then_read() -> None:
    site = _site()
    async with open_admin(site) as admin:
        assert await admin.open_store(REF, None) == "77"  # 목록에서 이름으로 찾고 주소에서 식별값
        got = await admin.read_fields(["description", "website", "regular_hours", "menu"])
    assert {k: (v.value, v.pending_review) for k, v in got.items()} == {
        "description": ("옛 소개", False),
        "website": ("https://old.example/", False),
    }  # 셀렉터가 없는 칸(영업시간·메뉴)은 빠진다 → 지금 값 null


async def test_write_then_read_again_and_review_badge() -> None:
    site = _site(review_after_save={"website"})
    async with open_admin(site) as admin:
        assert await admin.open_store(REF, "77") == "77"
        await admin.write_field("description", "명동의 칼국수 집이에요.")
        await admin.write_field("website", "https://new.example/")
        got = await admin.read_fields(["description", "website"])
    assert site.saves == [("description", "명동의 칼국수 집이에요."), ("website", "https://new.example/")]
    assert (got["description"].value, got["description"].pending_review) == ("명동의 칼국수 집이에요.", False)
    assert (got["website"].value, got["website"].pending_review) == ("https://new.example/", True)  # 검토 중


async def test_field_without_screen_is_write_failed() -> None:
    site = _site()
    async with open_admin(site) as admin:
        await admin.open_store(REF, "77")
        for f, v in (("regular_hours", {"days": {}}), ("menu", []), ("attributes", {"vegetarian": True})):
            with pytest.raises(FieldWriteFailed) as e:
                await admin.write_field(f, v)
            assert e.value.reason == "unsupported_field"
    assert site.saves == []


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("login", "login_required"),
        ("security", "security_check"),
        ("captcha", "captcha"),
        ("broken", "unexpected_screen"),
    ],
)
async def test_blocked_screens_stop_at_once(monkeypatch: pytest.MonkeyPatch, mode: str, reason: str) -> None:
    monkeypatch.setattr(guards_mod, "READY_TIMEOUT_MS", 1500)  # 예상 밖 화면: 기다리다 멈춤(시험은 짧게)
    site = _site(mode=mode)
    async with open_admin(site) as admin:
        with pytest.raises(AutomationBlocked) as e:
            await admin.open_store(REF, "77")
    assert e.value.reason == reason and site.saves == []


async def test_store_not_visible_and_attention() -> None:
    async with open_admin(_site()) as admin:
        with pytest.raises(StoreNotVisible):
            await admin.open_store(REF, "99")  # 정보 화면이 "가게 없음"
        with pytest.raises(StoreNotVisible):
            await admin.open_store(dataclasses.replace(REF, name="없는가게"), None)  # 목록에 없음
    async with open_admin(_site(mode="attention")) as admin:
        with pytest.raises(AttentionNeeded) as e:
            await admin.open_store(REF, "77")
    assert e.value.reason == "verification_required"


async def test_empty_selector_file_never_opens_screen() -> None:
    """PoC 전(selectors/google.yaml이 비어 있음): 화면을 열지 않고 수동 처리로."""
    site = _site()
    async with open_admin(site) as admin:
        real = await admin.same_page(load_screen_config("google"))
        with pytest.raises(AutomationBlocked) as e:
            await real.open_store(REF, None)
    assert e.value.reason == "selectors_missing"


async def test_apply_fix_through_screen(db: AsyncSession, fake_mailer: Any, settings_env: Any) -> None:
    """applyFix가 화면 엔진으로 칸을 쓰고 다시 읽는다. 셀렉터가 없는 칸은 그 칸만 수동 처리."""
    settings_env(AUTO_FIX_ENABLED="true", ADMIN_NOTIFY_EMAILS="ops@seelo.test")
    w = await seed_plan_world(db)
    p = await approved_plan(
        db,
        w,
        "google",
        {"description": "명동의 칼국수 집이에요.", "regular_hours": {"days": {}}, "phone": "02-776-0000"},
    )
    site = _site()
    site.stores = {"77": "명동교자"}
    site.values["phone"] = "02-111-2222"

    @asynccontextmanager
    async def map_admin(provider: str) -> AsyncIterator[Any]:
        async with open_admin(site) as admin:
            yield admin

    set_clients(dataclasses.replace(get_clients(), map_admin=map_admin))
    await fix_apply_service.apply(p["plan_id"])
    db.expire_all()
    logs = {lg.field: lg for lg in await db.scalars(select(FixLog))}
    assert (logs["description"].status, logs["description"].before_value) == ("applied", "옛 소개")
    assert (logs["phone"].status, logs["phone"].before_value) == ("applied", "02-111-2222")
    hours = logs["regular_hours"]
    assert (hours.status, hours.manual_reason, hours.error_code) == (
        "manual_required",
        "write_failed",
        "unsupported_field",
    )
    assert site.saves == [("description", "명동의 칼국수 집이에요."), ("phone", "02-776-0000")]
