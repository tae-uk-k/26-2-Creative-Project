"""W-09-6 로컬 HTML(카카오 파트너센터): 한 줄 소개 쓰기·다시 읽기, 로그인·보안 확인 차단, 권한 없음.

tests/browser_site.py는 흉내 낸 화면이다(PoC 전). Playwright·Chromium이 없으면 건너뛴다.
"""

import pytest

from seelo.integrations.browser import StoreRef
from seelo.integrations.browser.guards import AttentionNeeded, AutomationBlocked, FieldWriteFailed
from tests.browser_site import AdminSite, open_admin

pytest.importorskip("playwright.async_api")
REF = StoreRef(store_id=1, name="데모식당", address=None, google_place_id=None, kakao_place_id="K1")


async def test_intro_write_and_read_again() -> None:
    site = AdminSite("kakao", values={"intro": "옛 소개"}, review_after_save={"intro"})
    async with open_admin(site) as admin:
        assert await admin.open_store(REF, None) == "77"
        before = await admin.read_fields(["intro", "hours", "price_items"])
        await admin.write_field("intro", "명동 칼국수 맛집")
        after = await admin.read_fields(["intro"])
        with pytest.raises(FieldWriteFailed):
            await admin.write_field("hours", {"days": {}})  # 셀렉터를 정하지 못한 칸
    assert {k: v.value for k, v in before.items()} == {"intro": "옛 소개"}
    assert (after["intro"].value, after["intro"].pending_review) == ("명동 칼국수 맛집", True)  # 검토 중
    assert site.saves == [("intro", "명동 칼국수 맛집")]


@pytest.mark.parametrize(("mode", "reason"), [("login", "login_required"), ("security", "security_check")])
async def test_blocked(monkeypatch: pytest.MonkeyPatch, mode: str, reason: str) -> None:
    from seelo.integrations.browser import guards

    monkeypatch.setattr(guards, "READY_TIMEOUT_MS", 1500)
    site = AdminSite("kakao", values={"intro": "옛 소개"}, mode=mode)
    async with open_admin(site) as admin:
        with pytest.raises(AutomationBlocked) as e:
            await admin.open_store(REF, "77")
    assert e.value.reason == reason and site.saves == []


async def test_no_owner_authority() -> None:
    async with open_admin(AdminSite("kakao", mode="attention")) as admin:
        with pytest.raises(AttentionNeeded) as e:
            await admin.open_store(REF, "77")
    assert e.value.reason == "no_owner_authority"
