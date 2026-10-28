"""W-03-2 카카오·네이버 값은 저장하지 않고 AI에 보내지 않는다(07 4.2·4.3, 11 4장)."""

from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations import get_clients
from seelo.models.store import SourceSnapshot, StoreSource
from seelo.services import collect_service
from tests.map_world import G_EN, g_detail, k, n, north, seed_store
from tests.support import dump_db_text

pytestmark = pytest.mark.usefixtures("queue_app")

NAVER_ITEM = n(
    "명동교자 네이버점", north(40), category="네이버전용>칼국수", road="서울특별시 중구 네이버전용로 77"
) | {"link": "https://naver-only-link.example/"}
KAKAO_DOC = k(
    "K1", "명동교자 카카오점", north(30), category="음식점 > 카카오전용분류", road="서울 중구 카카오전용길 9"
)


async def test_kakao_naver_values_not_stored_nor_sent_to_llm(db: AsyncSession, maps: Any, web: Any) -> None:
    # Google에 웹사이트가 없어 네이버 link로 웹사이트를 찾는 경우(네이버 값이 가장 쉽게 새는 길)
    maps.places.world = [g_detail("G1", "명동교자")]
    maps.places.english = {"G1": G_EN}
    maps.kakao.world = [KAKAO_DOC]
    maps.naver.world = [NAVER_ITEM]
    site = "https://naver-only-link.example"
    web.server.robots(site, "User-agent: *\nAllow: /")
    web.server.html(
        f"{site}/",
        "<html><body><p>칼국수 전문점. 매일 10시 반부터.</p><a href='/menu'>메뉴</a></body></html>",
    )
    web.server.html(f"{site}/menu", "<html><body><li>칼국수 11,000원</li></body></html>")

    store_id, run_id = await seed_store(db, name="명동교자")
    await collect_service.collect_store(store_id, run_id)

    # 스냅샷은 Google·웹사이트(·인스타그램)뿐. 카카오·네이버 행 0개
    providers = (await db.scalars(select(SourceSnapshot.provider))).all()
    assert sorted(providers) == ["google", "website"]
    # LLM이 불렸고(웹사이트 정리, AI 웹 검색 두 공급자·정리), 모든 요청 본문에 네이버·카카오 값이 없다
    calls = web.llm.calls + get_clients().gemini.calls
    kinds = sorted(c.get("schema") or c["kind"] for c in calls)
    assert kinds == ["WebEvidenceExtractOut"] * 2 + ["WebsiteExtractOut"] + ["web_answer"] * 2
    naver_values = ["명동교자 네이버점", "네이버전용", "네이버전용로 77", "naver-only-link.example"]
    kakao_values = ["명동교자 카카오점", "카카오전용분류", "카카오전용길 9", "02-776-5348"]
    for call in calls:
        for v in naver_values + kakao_values:
            assert v not in call["prompt"], v
    # DB 전체 텍스트에도 카카오·네이버 응답 값이 없다(store_sources의 카카오 id·place_url만 허용)
    dump = await dump_db_text(db)
    for v in [
        "명동교자 네이버점",
        "네이버전용>칼국수",
        "네이버전용로 77",
        "명동교자 카카오점",
        "카카오전용분류",
        "카카오전용길 9",
    ]:
        assert v not in dump, v
    # 웹사이트 출처 url은 그 사이트 주소(저장 허용: 우리가 읽은 공식 웹사이트)
    url = await db.scalar(select(StoreSource.url).where(StoreSource.provider == "website"))
    assert url == f"{site}/"


@pytest.mark.parametrize("provider", ["kakao", "naver"])
async def test_db_check_blocks_kakao_naver_snapshots(db: AsyncSession, maps: Any, provider: str) -> None:
    store_id, _ = await seed_store(db)
    source_id = await db.scalar(select(StoreSource.id).where(StoreSource.provider == "kakao"))
    db.add(
        SourceSnapshot(
            source_id=source_id,
            store_id=store_id,
            provider=provider,
            status="ok",
            payload={},
            expires_at=text("now()"),
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(SourceSnapshot)) == 0
