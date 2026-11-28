"""W-03-4 AI 웹 검색 수집(07 6.4): 공급자별 웹 검색 → 정리 → 이름·주소로 거르기 → web_evidence.

한쪽 실패 → 다른 쪽만 저장, 둘 다 실패 → 행 없음(수집은 계속), 주소 출처(Google → 카카오), 네이버 값 없음.
"""

import json
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import MeasurementRun
from seelo.models.store import Store, WebEvidence
from seelo.schemas.llm import EvidenceSiteOut, WebEvidenceExtractOut
from seelo.services import collect_service
from tests.map_world import G_EN, g_detail, k, n, north, seed_store

pytestmark = pytest.mark.usefixtures("queue_app")

ADDRESS = "대한민국 서울특별시 중구 명동10길 29"
AI_HEAD = "Find publicly available information about this place."


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        OPENAI_MEASURE_MODEL="m-openai", GEMINI_MEASURE_MODEL="m-gemini", OPENAI_CHEAP_MODEL="m-cheap"
    )


def _google(maps: Any) -> None:
    maps.places.world = [g_detail("G1", "명동교자")]
    maps.places.english = {"G1": G_EN}


async def _collect(db: AsyncSession, **kw: Any) -> tuple[int, int]:
    store_id, run_id = await seed_store(db, **{"naver": False, **kw})
    await collect_service.collect_store(store_id, run_id)
    db.expire_all()
    return store_id, run_id


async def _evidence(db: AsyncSession) -> list[WebEvidence]:
    return list((await db.scalars(select(WebEvidence).order_by(WebEvidence.id))).all())


def _ai_prompts(ai: Any) -> list[str]:
    return [c["prompt"] for c in ai.openai.calls + ai.gemini.calls if c["prompt"].startswith(AI_HEAD)]


def _site(name: str | None, address: str | None, url: str = "https://x.example/1") -> EvidenceSiteOut:
    return EvidenceSiteOut(
        url=url, site_name="x", name=name, address=address, phone=None, hours_text=None, menu=[],
        instagram_url=None,
    )  # fmt: skip


async def test_both_providers_saved_and_other_place_dropped(
    db: AsyncSession, maps: Any, ai: Any, settings_env: Any, tmp_path: Any
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "openai": {
                    "m-openai": {"inputPer1M": 1, "webSearchPerCall": 0.01},
                    "m-cheap": {"inputPer1M": 1},
                },
                "gemini": {"m-gemini": {"inputPer1M": 1, "groundingPerQuery": 0.01}},
            }
        ),
        encoding="utf-8",
    )
    settings_env(PRICING_FILE=str(pricing))
    _google(maps)
    store_id, run_id = await _collect(db)
    rows = await _evidence(db)
    # 공급자마다 3곳 중 2곳(같은 가게)만. "다른식당"은 이름·주소 모두 달라 버림
    assert sorted((r.provider, r.site_url) for r in rows) == sorted(
        (p, u)
        for p in ("openai", "gemini")
        for u in (
            "https://www.tripadvisor.com/Restaurant_Review-demo",
            "https://korean.visitkorea.or.kr/detail/demo",
        )
    )
    r = rows[0]
    assert (r.store_id, r.run_id, r.expires_at is not None) == (store_id, run_id, True)
    assert set(r.fields) == set(EvidenceSiteOut.model_fields)  # 저장 형식 = EvidenceSiteOut
    assert r.fields["name"] == "명동교자" and r.fields["phone"] == "02-776-0000"
    # 1단계 프롬프트는 07 6.4 그대로: 가게 이름·Google 주소만
    prompts = _ai_prompts(ai)
    assert len(prompts) == 2 and prompts[0] == (
        f"{AI_HEAD}\nName: 명동교자\nAddress: {ADDRESS}\n"
        "Search the web and list every website that has information about this exact place.\n"
        "For each website, give the URL, the site name, and the place's name, address, phone number,\n"
        "opening hours, and menu items with prices exactly as stated on that site."
    )
    assert (await db.get(MeasurementRun, run_id)).cost_usd > 0  # 두 단계 호출 비용을 측정에 더함


async def test_one_provider_fails_other_saved(db: AsyncSession, maps: Any, ai: Any) -> None:
    _google(maps)
    ai.gemini.fail_next(3, "server_error", only="web_answer")
    store_id, _ = await _collect(db)
    assert {r.provider for r in await _evidence(db)} == {"openai"}
    assert (await db.get(Store, store_id)).status == "measuring"  # 수집은 계속


async def test_cleanup_step_failure_only_drops_that_provider(db: AsyncSession, maps: Any, ai: Any) -> None:
    _google(maps)
    ai.openai.fail_next(1, "parse_failed", only="WebEvidenceExtractOut")  # 두 정리 호출 중 하나
    await _collect(db)
    rows = await _evidence(db)
    assert len(rows) == 2 and len({r.provider for r in rows}) == 1


async def test_both_fail_no_rows_collection_continues(db: AsyncSession, maps: Any, ai: Any) -> None:
    _google(maps)
    ai.openai.fail_next(1, "auth_error", only="web_answer")
    ai.gemini.fail_next(1, "auth_error", only="web_answer")
    store_id, _ = await _collect(db)
    assert await _evidence(db) == []
    assert (await db.get(Store, store_id)).status == "measuring"


async def test_sites_kept_by_name_or_address(db: AsyncSession, maps: Any, ai: Any) -> None:
    _google(maps)
    ai.openai.results["WebEvidenceExtractOut"] = WebEvidenceExtractOut(
        sites=[
            _site("명동교자 본점", None, "https://a.example/"),  # 이름(지점명)
            _site("Myeongdong Kyoja", None, "https://b.example/"),  # 영문 이름(Google en)
            _site("엉뚱한이름", "서울 중구 명동10길 29", "https://c.example/"),  # 주소
            _site("다른식당", "서울 중구 명동10길 30", "https://d.example/"),  # 둘 다 다름
            _site(None, None, "https://e.example/"),  # 판단할 수 없음
            _site("명동교자", None, "  "),  # 주소 없는 사이트
        ]
    )
    await _collect(db)
    kept = {r.site_url for r in await _evidence(db)}
    assert kept == {"https://a.example/", "https://b.example/", "https://c.example/"}


async def test_kakao_road_address_when_no_google(db: AsyncSession, maps: Any, ai: Any) -> None:
    maps.kakao.world = [k("K1", "명동교자", north(10), road="서울 중구 명동길 99")]
    maps.naver.world = [n("명동교자", north(10), road="서울특별시 중구 네이버만있는로 7")]
    await _collect(db, google_id=None, naver=True)
    prompts = _ai_prompts(ai)
    assert prompts and all("Address: 서울 중구 명동길 99" in p for p in prompts)
    assert all("네이버만있는로" not in c["prompt"] for c in ai.openai.calls + ai.gemini.calls)


async def test_no_address_skips_search(db: AsyncSession, maps: Any, ai: Any) -> None:
    await _collect(db, google_id=None, kakao_id=None)
    assert _ai_prompts(ai) == [] and await _evidence(db) == []
