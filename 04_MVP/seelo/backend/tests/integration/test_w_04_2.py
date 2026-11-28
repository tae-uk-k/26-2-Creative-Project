"""W-04-2 AI 측정 호출(08 2.1·2.2, 06 6장): 실행 행·재시도·비용·하루 상한·질문 문장만 보냄."""

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Question
from seelo.services import measure_service
from seelo.timeutil import now_utc
from tests.map_world import QUESTIONS, seed_measuring

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch, settings_env: Any) -> None:
    monkeypatch.setattr(measure_service, "BACKOFF_S", (0.0, 0.0))
    settings_env(AI_REPEAT_COUNT="2", OPENAI_MEASURE_MODEL="m-openai", GEMINI_MEASURE_MODEL="m-gemini")


async def _jobs(db: AsyncSession, name: str) -> list[dict]:
    rows = await db.execute(
        text("SELECT args, queue_name FROM procrastinate_jobs WHERE task_name = :n ORDER BY id"), {"n": name}
    )
    return [{"args": r[0], "queue": r[1]} for r in rows]


async def _executions(db: AsyncSession, run_id: int) -> list[AiExecution]:
    db.expire_all()
    return list(
        (
            await db.scalars(select(AiExecution).where(AiExecution.run_id == run_id).order_by(AiExecution.id))
        ).all()
    )


async def test_run_creates_executions_and_enqueues_per_provider(db: AsyncSession, ai: Any) -> None:
    _, run_id, qids = await seed_measuring(db)
    await measure_service.run(run_id)
    ex = await _executions(db, run_id)
    assert len(ex) == 3 * 2 * 2  # 질문 3 × 공급자 2 × 반복 2
    assert {(e.question_id, e.provider, e.repeat_no) for e in ex} == {
        (q, p, n) for q in qids for p in ("openai", "gemini") for n in (1, 2)
    }
    run = await db.get(MeasurementRun, run_id)
    assert (run.progress_total, run.stage, run.waiting_reason) == (12, "calling_ai", None)
    jobs = await _jobs(db, "callAi")
    assert len(jobs) == 12
    by_id = {e.id: e.provider for e in ex}
    assert all(j["queue"] == f"ai_{by_id[j['args']['execution_id']]}" for j in jobs)


async def test_execution_unique_constraint(db: AsyncSession, ai: Any) -> None:
    _, run_id, qids = await seed_measuring(db)
    db.add(AiExecution(run_id=run_id, question_id=qids[0], provider="openai", repeat_no=1, status="pending"))
    await db.commit()
    db.add(AiExecution(run_id=run_id, question_id=qids[0], provider="openai", repeat_no=1, status="pending"))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_request_body_is_exactly_the_question(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    for e in await _executions(db, run_id):
        await measure_service.call_ai(e.id)
    sent = [c["prompt"] for c in ai.openai.calls + ai.gemini.calls if c["kind"] == "web_answer"]
    assert len(sent) == 12
    assert set(sent) == {q for _, _, q, _ in QUESTIONS}  # 지시문·앞뒤 문장 없음
    assert {c["model"] for c in ai.openai.calls} == {"m-openai"} and {
        c["model"] for c in ai.gemini.calls
    } == {"m-gemini"}


async def test_success_saves_raw_answer_sources_and_enqueues_extract(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    first = (await _executions(db, run_id))[0]
    await measure_service.call_ai(first.id)

    ex = (await _executions(db, run_id))[0]
    assert (ex.status, ex.attempt, ex.model_id, ex.web_search_calls) == ("succeeded", 1, "m-openai", 1)
    resp = await db.scalar(select(AiResponse).where(AiResponse.execution_id == ex.id))
    assert (
        resp.raw_text.startswith("Here are some places") and "데모식당" in resp.raw_text
    )  # 첫 답변은 데모식당 2위
    assert resp.annotated_text.count("[1]") >= 1 and resp.annotated_text != resp.raw_text
    assert [s["domain"] for s in resp.source_urls] == [
        "tripadvisor.com",
        "korean.visitkorea.or.kr",
        "google.com",
    ]
    assert resp.extraction_status == "pending"
    assert [j["args"] for j in await _jobs(db, "extractRecommendations")] == [{"response_id": resp.id}]
    assert (await db.get(MeasurementRun, run_id)).progress_done == 1


async def test_transient_errors_retried_twice_then_failed(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ex = (await _executions(db, run_id))[0]
    ai.openai.fail_next(3, "rate_limited")
    await measure_service.call_ai(ex.id)
    ex = (await _executions(db, run_id))[0]
    assert (ex.status, ex.attempt, ex.error_code) == ("failed", 3, "rate_limited") and ex.finished_at
    assert len([c for c in ai.openai.calls if c["kind"] == "web_answer"]) == 3
    assert (await db.get(MeasurementRun, run_id)).progress_done == 1


async def test_transient_then_success(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ex = (await _executions(db, run_id))[0]
    ai.openai.fail_next(2, "server_error")
    await measure_service.call_ai(ex.id)
    ex = (await _executions(db, run_id))[0]
    assert (ex.status, ex.attempt) == ("succeeded", 3)


@pytest.mark.parametrize("reason", ["bad_request", "auth_error", "refused"])
async def test_non_retryable_fails_immediately(db: AsyncSession, ai: Any, reason: str) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ex = (await _executions(db, run_id))[0]
    ai.openai.fail_next(1, reason)
    await measure_service.call_ai(ex.id)
    ex = (await _executions(db, run_id))[0]
    assert (ex.status, ex.attempt, ex.error_code) == ("failed", 1, reason)


async def test_timeout_counts_as_retryable(
    db: AsyncSession, ai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(measure_service, "AI_CALL_TIMEOUT_S", 0.2)
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ex = (await _executions(db, run_id))[0]
    ai.openai.fail_next(3, "hang")
    await measure_service.call_ai(ex.id)
    ex = (await _executions(db, run_id))[0]
    assert (ex.status, ex.attempt, ex.error_code) == ("failed", 3, "timeout")


async def test_cost_per_call_and_run_total(
    db: AsyncSession, ai: Any, settings_env: Any, tmp_path: Any
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "openai": {
                    "m-openai": {"inputPer1M": 1000.0, "outputPer1M": 2000.0, "webSearchPerCall": 0.01}
                },
                "gemini": {
                    "m-gemini": {"inputPer1M": 500.0, "outputPer1M": 500.0, "groundingPerQuery": 0.014}
                },
            }
        )
    )
    settings_env(PRICING_FILE=str(pricing))
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    for e in await _executions(db, run_id):
        await measure_service.call_ai(e.id)
    ex = await _executions(db, run_id)
    assert all(e.cost_usd > 0 for e in ex)
    one = ex[0]
    expected = Decimal(str(round(one.input_tokens / 1e6 * (1000 if one.provider == "openai" else 500)
                                 + one.output_tokens / 1e6 * (2000 if one.provider == "openai" else 500)
                                 + (0.01 if one.provider == "openai" else 0.014), 6)))  # fmt: skip
    assert one.cost_usd == expected
    run = await db.get(MeasurementRun, run_id)
    assert run.cost_usd == sum(e.cost_usd for e in ex)
    assert run.progress_done == 12


async def test_daily_cost_limit_waits_and_reschedules(db: AsyncSession, ai: Any, settings_env: Any) -> None:
    settings_env(DAILY_COST_LIMIT_USD="1.0")
    store_id, run_id, _ = await seed_measuring(db)
    # 오늘 다른 측정이 이미 1달러를 썼다
    other = MeasurementRun(
        store_id=store_id, kind="diagnosis", trigger="retry", status="completed", cost_usd=Decimal("1.0")
    )
    db.add(other)
    await db.commit()
    await measure_service.run(run_id)

    run = await db.get(MeasurementRun, run_id)
    assert run.waiting_reason == "cost_limit"
    assert await db.scalar(select(func.count()).select_from(AiExecution)) == 0
    row = (
        await db.execute(
            text("SELECT scheduled_at, args FROM procrastinate_jobs WHERE task_name = 'runMeasurement'")
        )
    ).one()
    assert row.args == {"run_id": run_id}
    assert timedelta(minutes=29) < row.scheduled_at - now_utc() <= timedelta(minutes=30)

    # 상한을 풀면 다시 시작하고 waiting_reason을 지운다
    settings_env(DAILY_COST_LIMIT_USD="0")
    await db.execute(text("DELETE FROM procrastinate_jobs"))
    await db.commit()
    await measure_service.run(run_id)
    db.expire_all()
    assert (await db.get(MeasurementRun, run_id)).waiting_reason is None
    assert await db.scalar(select(func.count()).select_from(AiExecution)) == 12


async def test_question_text_unchanged_in_db(db: AsyncSession, ai: Any) -> None:
    _, run_id, qids = await seed_measuring(db)
    texts = (
        await db.scalars(select(Question.text).where(Question.id.in_(qids)).order_by(Question.order_no))
    ).all()
    assert list(texts) == [q for _, _, q, _ in QUESTIONS]
