"""W-04-3 진행률·중복 없는 재실행·동시 완료(08 2.1·2.2, 04 5.3)."""

import asyncio
import time
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import AiExecution, MeasurementRun
from seelo.services import measure_service
from tests.map_world import seed_measuring
from tests.support import login

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _small(monkeypatch: pytest.MonkeyPatch, settings_env: Any) -> None:
    monkeypatch.setattr(measure_service, "BACKOFF_S", (0.0, 0.0))
    settings_env(AI_REPEAT_COUNT="2")


async def _call_ai_jobs(db: AsyncSession) -> list[int]:
    rows = await db.execute(
        text("SELECT args FROM procrastinate_jobs WHERE task_name = 'callAi' ORDER BY id")
    )
    return [r[0]["execution_id"] for r in rows]


async def test_progress_api_shape_and_speed(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    await login(client, "owner@seelo.test")
    r = await client.get(f"/api/runs/{run_id}/progress")
    assert r.json() == {
        "runId": run_id,
        "kind": "diagnosis",
        "status": "running",
        "stage": "calling_ai",
        "progressDone": 0,
        "progressTotal": 12,
        "waitingReason": None,
        "failureReason": None,
        "canCancel": True,
        "next": None,
    }
    n = 1000
    started = time.perf_counter()
    for _ in range(n):
        assert (await client.get(f"/api/runs/{run_id}/progress")).status_code == 200
    avg_ms = (time.perf_counter() - started) * 1000 / n
    assert avg_ms < 200, avg_ms
    print(f"progress avg {avg_ms:.1f}ms over {n}")


async def test_progress_completed_next_and_owner_only(make_client: Any, db: AsyncSession, ai: Any) -> None:
    from tests.support import make_user

    _, run_id, _ = await seed_measuring(db)
    await db.execute(
        update(MeasurementRun).where(MeasurementRun.id == run_id).values(status="completed", stage="done")
    )
    await db.commit()
    owner = await make_client()
    await login(owner, "owner@seelo.test")
    body = (await owner.get(f"/api/runs/{run_id}/progress")).json()
    assert (body["next"], body["canCancel"]) == (f"/diagnosis/{run_id}", False)
    other = await make_client()
    await make_user(db, "x@seelo.test")
    await login(other, "x@seelo.test")
    assert (await other.get(f"/api/runs/{run_id}/progress")).status_code == 404


async def test_rerun_enqueues_only_unfinished(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ids = await _call_ai_jobs(db)
    assert len(ids) == 12
    # 일부를 끝내고, 대기 작업을 비운 뒤(워커가 가져간 상태 흉내) 다시 실행
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[:4])).values(status="succeeded"))
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[4:6])).values(status="failed"))
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[6:7])).values(status="running"))
    await db.execute(text("DELETE FROM procrastinate_jobs"))
    await db.commit()
    await measure_service.run(run_id)
    assert sorted(await _call_ai_jobs(db)) == sorted(ids[6:])  # running 1 + pending 5, 끝난 6개는 없음
    assert len((await db.scalars(select(AiExecution.id).where(AiExecution.run_id == run_id))).all()) == 12


async def test_worker_crash_does_not_recall_finished(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ids = await _call_ai_jobs(db)
    await measure_service.call_ai(ids[0])  # 끝남
    # 워커가 호출 중 죽음: 실행이 running으로 남음
    await db.execute(update(AiExecution).where(AiExecution.id == ids[1]).values(status="running", attempt=1))
    await db.commit()
    calls = len(ai.openai.calls) + len(ai.gemini.calls)
    await measure_service.call_ai(ids[0])  # 다시 와도 끝난 실행은 0번
    assert len(ai.openai.calls) + len(ai.gemini.calls) == calls
    await measure_service.call_ai(ids[1])  # running으로 남은 것은 다시 부른다
    assert len(ai.openai.calls) + len(ai.gemini.calls) == calls + 1


async def test_last_two_finishing_together_register_finalize_once(db: AsyncSession, ai: Any) -> None:
    """마지막 두 실행이 동시에 실패로 끝나도 finalizeRun은 정확히 1번(측정 행 잠금, 실제 PG 두 세션)."""
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ids = await _call_ai_jobs(db)
    # 앞의 10개는 이미 실패로 끝남(추출 대기 없음), 마지막 2개만 남김
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[:10])).values(status="failed"))
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[10:])).values(status="running"))
    await db.commit()
    await asyncio.gather(
        measure_service._record_failure(ids[10], run_id, "timeout"),
        measure_service._record_failure(ids[11], run_id, "timeout"),
    )
    rows = (
        await db.execute(text("SELECT args FROM procrastinate_jobs WHERE task_name = 'finalizeRun'"))
    ).all()
    assert [r[0] for r in rows] == [{"run_id": run_id}]
    db.expire_all()
    assert (await db.get(MeasurementRun, run_id)).progress_done == 2


async def test_finalize_not_registered_while_extraction_pending(db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await measure_service.run(run_id)
    ids = await _call_ai_jobs(db)
    await measure_service.call_ai(ids[0])  # 성공 → 추출 대기(pending)
    await db.execute(update(AiExecution).where(AiExecution.id.in_(ids[1:11])).values(status="failed"))
    await db.execute(update(AiExecution).where(AiExecution.id == ids[11]).values(status="running"))
    await db.commit()
    await measure_service._record_failure(ids[11], run_id, "timeout")
    assert (
        await db.execute(text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'finalizeRun'"))
    ).scalar() == 0
