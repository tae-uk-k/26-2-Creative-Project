"""브라우저 골격(09 8.2·8.3): 오래된 실패 기록 폴더 지우기, 가짜 관리 화면 상황 만들기."""

import os
import time
from pathlib import Path

import pytest

from seelo.integrations.browser import StoreRef
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.integrations.browser.session import prune_artifacts
from seelo.integrations.fake_admin import FakeMapAdmin, fake_map_admins

REF = StoreRef(store_id=7, name="데모식당", address=None, google_place_id="G1", kakao_place_id="K1")


def test_prune_artifacts_keeps_recent(tmp_path: Path) -> None:
    old = tmp_path / "applyFix" / "101"
    new = tmp_path / "applyFix" / "102"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    eight_days = time.time() - 8 * 24 * 3600
    os.utime(old, (eight_days, eight_days))
    assert prune_artifacts(tmp_path) == 1
    assert not old.exists() and new.exists()
    assert prune_artifacts(tmp_path / "none") == 0


async def test_fake_admin_situations() -> None:
    a = FakeMapAdmin(provider="google")
    assert await a.open_store(REF, None) == "fake-google-7"
    assert await a.open_store(REF, "locations/9") == "locations/9"
    a.transient_on("open", 1)
    with pytest.raises(TransientAutomationError):
        await a.open_store(REF, None)
    await a.open_store(REF, None)  # 한 번만
    a.needs_attention("verification_required")
    with pytest.raises(AttentionNeeded):
        await a.open_store(REF, None)
    a.attention = None
    a.delay_reflection("phone")
    await a.write_field("phone", "02-1")
    assert (await a.read_fields(["phone"]))["phone"].pending_review is True
    a.reflect("phone")
    got = (await a.read_fields(["phone"]))["phone"]
    assert (got.value, got.pending_review) == ("02-1", False)
    a.block_on("phone")
    with pytest.raises(AutomationBlocked):
        await a.write_field("phone", "02-2")
    a.not_visible()
    with pytest.raises(StoreNotVisible):
        await a.read_fields(["phone"])
    assert [e[0] for e in a.events][:3] == ["open", "open", "open"]


async def test_fake_behavior_block_first_write() -> None:
    admins = fake_map_admins("block")
    async with admins("kakao") as a:
        with pytest.raises(AutomationBlocked):
            await a.write_field("intro", "x")
        await a.write_field("intro", "y")  # 첫 쓰기만 막힘
    assert admins["kakao"].values == {"intro": "y"} and admins.opened == ["kakao"]
