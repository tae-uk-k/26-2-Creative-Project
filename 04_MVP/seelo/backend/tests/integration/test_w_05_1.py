"""W-05-1 추천 추출 extractRecommendations(08 3장).

추천 저장(순위·출처·조건)·1번 다시·실패 처리(분모에서 빠짐)·추천 0개도 성공·프롬프트의 이름 후보·중복 실행.
"""

import json
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Metric, Recommendation
from seelo.schemas.llm import ExtractionOut
from seelo.services import extract_service, finalize_service, measure_service
from tests.map_world import G_EN, g_detail, k, n, north, seed_google_snapshot, seed_measuring

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, settings_env: Any, tmp_path: Any) -> None:
    monkeypatch.setattr(measure_service, "BACKOFF_S", (0.0, 0.0))
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps({"openai": {"m-cheap": {"inputPer1M": 1000.0, "outputPer1M": 1000.0}}, "gemini": {}}),
        encoding="utf-8",
    )
    settings_env(
        AI_REPEAT_COUNT="1",
        OPENAI_MEASURE_MODEL="m-openai",
        GEMINI_MEASURE_MODEL="m-gemini",
        OPENAI_CHEAP_MODEL="m-cheap",
        PRICING_FILE=str(pricing),
    )


async def _answered(db: AsyncSession, **kw: Any) -> tuple[int, int, list[int]]:
    """가게 데모식당·측정 running, 질문 3 × 공급자 2 = 실행 6개를 모두 부른 상태. (store, run, 응답 id들)."""
    store_id, run_id, _ = await seed_measuring(db, name="데모식당", **kw)
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    await measure_service.run(run_id)
    for ex_id in (await db.scalars(select(AiExecution.id).where(AiExecution.run_id == run_id))).all():
        await measure_service.call_ai(ex_id)
    db.expire_all()
    ids = (await db.scalars(select(AiResponse.id).order_by(AiResponse.id))).all()
    return store_id, run_id, list(ids)


async def _finalize_jobs(db: AsyncSession) -> int:
    return await db.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'finalizeRun'"))


def _extract_calls(ai: Any) -> list[dict[str, Any]]:
    return [c for c in ai.openai.calls if c.get("schema") == "ExtractionOut"]


async def test_saves_ranked_recommendations_with_sources(db: AsyncSession, ai: Any) -> None:
    _, run_id, ids = await _answered(db)
    await extract_service.extract(ids[0])
    db.expire_all()
    resp = await db.get(AiResponse, ids[0])
    assert resp.extraction_status == "succeeded" and resp.extraction_json["recommendations"]
    recs = (
        await db.scalars(select(Recommendation).where(Recommendation.response_id == ids[0]).order_by("rank"))
    ).all()
    # 첫 답변: 명동칼국수 1위, 데모식당 2위 …(가짜 답변 n=0). 판정(is_target)은 마무리에서
    assert [(r.rank, r.name) for r in recs][:2] == [(1, "명동칼국수"), (2, "데모식당")]
    assert recs[1].normalized_name == "데모식당" and not any(r.is_target for r in recs)
    assert recs[0].source_urls == [
        {"url": "https://www.tripadvisor.com/Restaurant_Review-demo", "domain": "tripadvisor.com"}
    ]
    run = await db.get(MeasurementRun, run_id)
    assert run.cost_usd > 0  # 추출 호출 비용을 측정에 더함(06 6장)


async def test_retry_once_then_succeeds(db: AsyncSession, ai: Any) -> None:
    _, _, ids = await _answered(db)
    ai.openai.fail_next(1, "parse_failed", only="ExtractionOut")
    await extract_service.extract(ids[0])
    db.expire_all()
    assert (await db.get(AiResponse, ids[0])).extraction_status == "succeeded"
    assert len(_extract_calls(ai)) == 2


@pytest.mark.parametrize("reason", ["parse_failed", "refused", "hang"])
async def test_two_failures_mark_failed_and_keep_raw(
    db: AsyncSession, ai: Any, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    monkeypatch.setattr(extract_service, "EXTRACT_TIMEOUT_S", 0.05)
    _, run_id, ids = await _answered(db)
    ai.openai.fail_next(2, reason, only="ExtractionOut")
    await extract_service.extract(ids[0])
    db.expire_all()
    resp = await db.get(AiResponse, ids[0])
    assert (resp.extraction_status, bool(resp.raw_text)) == ("failed", True)  # 원문은 남긴다
    assert (await db.get(MeasurementRun, run_id)).extraction_failed_count == 1
    assert await db.scalar(select(func.count()).select_from(Recommendation)) == 0


async def test_zero_recommendations_is_success(db: AsyncSession, ai: Any) -> None:
    _, run_id, ids = await _answered(db)
    ai.openai.results["ExtractionOut"] = ExtractionOut(recommendations=[], target_claims=[])
    await extract_service.extract(ids[0])
    db.expire_all()
    assert (await db.get(AiResponse, ids[0])).extraction_status == "succeeded"
    assert (await db.get(MeasurementRun, run_id)).extraction_failed_count == 0


async def test_prompt_names_are_owner_and_google_only(db: AsyncSession, maps: Any, ai: Any) -> None:
    """추출 LLM에는 사장님 입력·Google ko·en 이름만. 카카오·네이버 이름은 보내지 않는다(08 3.2)."""
    maps.kakao.world = [k("K1", "카카오에만있는이름", north(10))]
    maps.naver.world = [n("네이버에만있는이름", north(10))]
    store_id, run_id, _ = await seed_measuring(db, name="데모식당")
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "구글이름식당"))
    await measure_service.run(run_id)
    first = await db.scalar(select(AiExecution.id).where(AiExecution.run_id == run_id).limit(1))
    await measure_service.call_ai(first)
    await extract_service.extract(await db.scalar(select(AiResponse.id)))
    prompt = _extract_calls(ai)[0]["prompt"]
    assert f"target places: 데모식당, 구글이름식당, {G_EN['displayName']['text']}," in prompt
    assert "카카오에만있는이름" not in prompt and "네이버에만있는이름" not in prompt


async def test_duplicate_job_does_not_double_rows(db: AsyncSession, ai: Any) -> None:
    _, _, ids = await _answered(db)
    await extract_service.extract(ids[0])
    before = await db.scalar(select(func.count()).select_from(Recommendation))
    await extract_service.extract(ids[0])
    assert await db.scalar(select(func.count()).select_from(Recommendation)) == before
    assert len(_extract_calls(ai)) == 1  # 두 번째는 LLM도 부르지 않음


async def test_skips_when_run_not_running(db: AsyncSession, ai: Any) -> None:
    _, run_id, ids = await _answered(db)
    await db.execute(text("UPDATE measurement_runs SET status = 'canceled' WHERE id = :i"), {"i": run_id})
    await db.commit()
    await extract_service.extract(ids[0])
    db.expire_all()
    assert (await db.get(AiResponse, ids[0])).extraction_status == "pending"
    assert _extract_calls(ai) == []


async def test_last_extraction_enqueues_finalize_once(db: AsyncSession, ai: Any) -> None:
    _, _, ids = await _answered(db)
    for rid in ids[:-1]:
        await extract_service.extract(rid)
    assert await _finalize_jobs(db) == 0  # 추출 대기 1개 남음
    ai.openai.fail_next(2, "parse_failed", only="ExtractionOut")  # 마지막은 실패여도 마무리는 등록
    await extract_service.extract(ids[-1])
    assert await _finalize_jobs(db) == 1


async def test_failed_extraction_left_out_of_denominator(db: AsyncSession, ai: Any) -> None:
    """추출 실패 응답은 지표 분모에서 빠진다(실패율에는 넣지 않음)."""
    _, run_id, ids = await _answered(db)
    providers = dict(
        (
            await db.execute(
                select(AiResponse.id, AiExecution.provider).join(
                    AiExecution, AiExecution.id == AiResponse.execution_id
                )
            )
        ).all()
    )
    failed_id = next(rid for rid in ids if providers[rid] == "openai")
    for rid in ids:
        if rid == failed_id:
            ai.openai.fail_next(2, "parse_failed", only="ExtractionOut")
        await extract_service.extract(rid)
    await finalize_service.finalize(run_id)
    db.expire_all()
    run = await db.get(MeasurementRun, run_id)
    assert (run.status, float(run.failure_rate), run.extraction_failed_count) == ("completed", 0.0, 1)
    success = dict(
        (
            await db.execute(
                select(Metric.provider, Metric.value).where(
                    Metric.run_id == run_id,
                    Metric.subject_type == "target",
                    Metric.question_id.is_(None),
                    Metric.metric_name == "success_count",
                )
            )
        ).all()
    )
    assert {p: int(v) for p, v in success.items()} == {"openai": 2, "gemini": 3}
