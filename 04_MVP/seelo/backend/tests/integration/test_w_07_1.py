"""W-07-1·2 고쳐야 할 점이 측정 마무리에서 저장되는 흐름(08 6장).

규칙 하나하나는 unit/test_findings_rules.py·test_priority.py. 여기서는
- 출처(Google 스냅샷·웹사이트·웹 근거·카카오·네이버 다시 부르기)를 모아 판정·저장하는지
- 카카오·네이버 값이 DB와 AI 비교 LLM 입력에 없는지
- 주변 가게 사실 조회(반경 2km, 실패하면 근거 부족)와 AI 비교 실패
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations.fake_web import demo_extraction
from seelo.models.finding import Finding
from seelo.models.measurement import MeasurementRun
from seelo.models.store import SourceSnapshot, StoreSource, WebEvidence
from seelo.schemas.llm import ClaimChecksOut, ClaimResultOut, ExtractionOut, TargetClaimOut
from seelo.timeutil import now_utc
from tests.map_world import g, g_detail, k, measure_to_end, n, north, seed_google_snapshot, seed_measuring
from tests.support import dump_db_text

pytestmark = pytest.mark.usefixtures("queue_app")

KAKAO_ONLY = ["02-555-0101", "카카오만길 3"]
NAVER_ONLY = ["네이버만로 5"]


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        AI_REPEAT_COUNT="1", OPENAI_MEASURE_MODEL="m", GEMINI_MEASURE_MODEL="m", OPENAI_CHEAP_MODEL="c"
    )


def _extraction_with_claim(prompt: str) -> ExtractionOut:
    """가짜 추출 + 데모식당이 나온 답변에는 전화번호 주장(지도 값과 같고 웹사이트와 다름)."""
    out = demo_extraction(prompt)
    if any(r.name == "데모식당" for r in out.recommendations):
        out.target_claims = [TargetClaimOut(field="phone", value="Call 02-776-5348")]
    return out


async def _world(db: AsyncSession, maps: Any, ai: Any) -> tuple[int, int]:
    kakao = k("K1", "데모식당", north(10), road="서울 중구 카카오만길 3")
    kakao["phone"] = "02-555-0101"
    maps.kakao.world = [kakao]
    maps.naver.world = [n("데모식당", north(10), road="서울특별시 중구 네이버만로 5")]
    competitor = g("C1", "명동칼국수", north(150)) | {
        "nationalPhoneNumber": "02-1", "websiteUri": "https://c1.example/", "servesVegetarianFood": True,
    }  # fmt: skip
    maps.places.world = [competitor]
    ai.openai.results["ExtractionOut"] = _extraction_with_claim
    store_id, run_id, _ = await seed_measuring(db, name="데모식당")
    # Google: 웹사이트 없음, 채식·카드 결제 정보 없음, 전화 02-776-5348
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    db.add(
        StoreSource(store_id=store_id, provider="website", url="https://demo.example/", match_status="found")
    )
    await db.flush()
    src = await db.scalar(select(StoreSource.id).where(StoreSource.provider == "website"))
    db.add(
        SourceSnapshot(
            source_id=src, store_id=store_id, run_id=run_id, provider="website", status="ok",
            payload={"url": "https://demo.example/", "extract": {
                "phone": "02-776-0000", "hours_text": None, "hours": None, "menu": [], "intro": None,
                "address": "서울 중구 명동10길 29",
            }},
            expires_at=now_utc() + timedelta(days=30),
        )
    )  # fmt: skip
    db.add(
        WebEvidence(
            store_id=store_id, run_id=run_id, provider="openai", site_url="https://t.example/",
            fields={"url": "https://t.example/", "name": "데모식당", "phone": "02-776-0000"},
            expires_at=now_utc() + timedelta(days=30),
        )
    )  # fmt: skip
    await db.commit()
    return store_id, run_id


async def _findings(db: AsyncSession, run_id: int) -> list[Finding]:
    return list(
        (await db.scalars(select(Finding).where(Finding.run_id == run_id).order_by(Finding.priority))).all()
    )


async def test_findings_saved_with_priority_and_no_kakao_naver_values(
    db: AsyncSession, maps: Any, ai: Any
) -> None:
    ai.openai.results["ClaimChecksOut"] = ClaimChecksOut(
        results=[ClaimResultOut(index=1, claim_matches_truth=False, claim_matches_map=True)]
    )
    _, run_id = await _world(db, maps, ai)
    await measure_to_end(db, run_id)
    assert (await db.get(MeasurementRun, run_id)).status == "completed"
    found = await _findings(db, run_id)
    assert {(f.provider, f.title_key) for f in found} == {
        ("google", "map_missing.website"),
        ("google", "map_missing.attributes"),
        ("google", "source_mismatch.phone"),  # 공식 웹사이트 전화가 다름
        ("kakao", "source_mismatch.phone"),  # 카카오 다시 부른 전화도 웹사이트와 다름
        ("kakao", "source_mismatch.address"),  # 카카오 주소(카카오만길)도 웹사이트 주소와 다름
        ("google", "ai_wrong.phone"),  # AI가 지도 값(틀린 번호)을 그대로 말함
    }
    assert [f.priority for f in found] == [1, 2, 3, 4, 5, 6] and all(f.stage == "diagnosis" for f in found)
    website = next(f for f in found if f.title_key == "map_missing.website")
    assert website.competitor_count == 1  # 명동칼국수는 웹사이트가 있음(사실 조회)
    attrs = next(f for f in found if f.title_key == "map_missing.attributes")
    assert attrs.evidence["missingKeys"] == ["vegetarian", "card_payment"]
    # 카카오·네이버 값은 DB 어디에도 없다
    dump = await dump_db_text(db)
    for v in KAKAO_ONLY + NAVER_ONLY:
        assert v not in dump, v
    kakao_row = next(f for f in found if f.provider == "kakao")
    assert "mapValue" not in kakao_row.evidence
    # AI 비교 LLM 입력: 주장·웹사이트 값·Google 값만
    compare = [c["prompt"] for c in ai.openai.calls if c.get("schema") == "ClaimChecksOut"]
    assert len(compare) == 1 and "02-776-0000" in compare[0] and "02-776-5348" in compare[0]
    for v in KAKAO_ONLY + NAVER_ONLY:
        assert v not in compare[0], v
    # 주변 가게 사실 조회: 이름 + 지역, 가게 좌표 기준 반경 2km
    searches = [c for name, c in maps.places.calls if name == "search_text"]
    assert searches and all(c["radius_m"] == 2000.0 for c in searches)
    assert any(c["query"] == "명동칼국수 명동" for c in searches)


async def test_competitor_lookup_failure_marks_insufficient(db: AsyncSession, maps: Any, ai: Any) -> None:
    _, run_id = await _world(db, maps, ai)
    await measure_to_end(db, run_id, finalize=False)
    maps.places.fail_next(4, "5xx")  # 주변 가게 4곳(반복 1번이라 4곳) 조회가 모두 실패
    from seelo.services import finalize_service

    await finalize_service.finalize(run_id)
    db.expire_all()
    found = await _findings(db, run_id)
    assert (await db.get(MeasurementRun, run_id)).status == "completed"
    missing = [f for f in found if f.category == "map_missing"]
    assert missing and all(f.evidence.get("insufficient") for f in missing)
    assert found[-len(missing) :] == missing  # 근거 부족은 맨 뒤


async def test_claim_compare_failure_skips_only_ai_wrong(db: AsyncSession, maps: Any, ai: Any) -> None:
    ai.openai.fail_next(1, "api_error", only="ClaimChecksOut")
    _, run_id = await _world(db, maps, ai)
    await measure_to_end(db, run_id)
    keys = {f.title_key for f in await _findings(db, run_id)}
    assert "ai_wrong.phone" not in keys and "source_mismatch.phone" in keys


async def test_remeasure_makes_no_findings(db: AsyncSession, maps: Any, ai: Any) -> None:
    store_id, run_id, _ = await seed_measuring(db, name="데모식당", kind="remeasure")
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    await measure_to_end(db, run_id)
    assert (await db.get(MeasurementRun, run_id)).status == "completed"
    assert await _findings(db, run_id) == []
