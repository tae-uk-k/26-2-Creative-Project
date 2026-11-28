"""W-04-4 측정 다시 시도(03 E25)·실패 시 무료 차감 없음·멈춘 작업 정리(06 5장 failStuckWork)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import EmailLog
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger
from seelo.services import jobs, maintenance
from seelo.timeutil import now_utc
from seelo.worker.tasks_measure import call_ai
from tests.map_world import seed_measuring, seed_store
from tests.support import login

pytestmark = pytest.mark.usefixtures("queue_app")


async def _age(db: AsyncSession, run_ids: list[int], minutes: float) -> None:
    """updated_at을 과거로. 트리거가 UPDATE마다 now()로 덮으므로 이 문장에서만 끈다(테스트 전용)."""
    await db.execute(text("SET LOCAL session_replication_role = replica"))
    await db.execute(
        update(MeasurementRun)
        .where(MeasurementRun.id.in_(run_ids))
        .values(updated_at=now_utc() - timedelta(minutes=minutes))
    )
    await db.execute(text("SET LOCAL session_replication_role = DEFAULT"))


async def _failed_store(db: AsyncSession) -> tuple[int, int]:
    store_id, run_id = await seed_store(db)
    await db.execute(text("UPDATE stores SET status = 'measure_failed' WHERE id = :i"), {"i": store_id})
    await db.execute(
        text("UPDATE measurement_runs SET status = 'failed', failure_reason = 'failure_rate' WHERE id = :i"),
        {"i": run_id},
    )
    await db.commit()
    return store_id, run_id


async def test_retry_three_times_then_429(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, _ = await _failed_store(db)
    await login(client, "owner@seelo.test")
    for _ in range(3):
        r = await client.post("/api/stores/current/retry")
        assert r.status_code == 202, r.text
        run = await db.get(MeasurementRun, r.json()["runId"])
        assert (run.kind, run.trigger, run.status, run.is_free) == ("diagnosis", "retry", "queued", True)
        new_run_id = run.id
        db.expire_all()
        assert (await db.get(Store, store_id)).status == "collecting"
        # 수집이 또 실패했다고 치고 다시 measure_failed로
        await db.execute(text("UPDATE stores SET status = 'measure_failed' WHERE id = :i"), {"i": store_id})
        await db.execute(
            text("UPDATE measurement_runs SET status = 'failed' WHERE id = :i"), {"i": new_run_id}
        )
        await db.commit()
    r = await client.post("/api/stores/current/retry")
    assert r.status_code == 429 and r.json()["error"]["code"] == "RETRY_LIMIT"
    jobs_ = (
        await db.execute(text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'collectStore'"))
    ).scalar()
    assert jobs_ == 3


async def test_retry_only_when_measure_failed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await seed_store(db)  # collecting
    await login(client, "owner@seelo.test")
    r = await client.post("/api/stores/current/retry")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "collecting"}


async def test_retry_with_request_is_not_free_and_links_approved(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    store_id, _ = await _failed_store(db)
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="approved"))
    await db.commit()
    req_id = await db.scalar(select(FixRequest.id))
    await login(client, "owner@seelo.test")
    run = await db.get(MeasurementRun, (await client.post("/api/stores/current/retry")).json()["runId"])
    assert (run.is_free, run.fix_request_id) == (False, req_id)


async def test_failure_does_not_use_up_free_diagnosis(db: AsyncSession, ai: Any) -> None:
    """측정이 실패로 끝나도 free_usage_ledger는 0행(무료 차감 없음)."""
    store_id, run_id, _ = await seed_measuring(db)
    await _age(db, [run_id], 31)
    await db.commit()
    counts = await maintenance.fail_stuck_work(db)
    await db.commit()
    assert counts["runs"] == 1
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 0


async def test_fail_stuck_work_rules(db: AsyncSession, ai: Any) -> None:
    now = now_utc()
    # ① 멈춤: 31분 전, 작업 없음 → failed(stuck), 가게 measure_failed, 메일
    s1, r1, _ = await seed_measuring(db, email="a@seelo.test")
    # ② 아직 살아 있는 작업이 있음 → 그대로
    s2, r2, _ = await seed_measuring(db, email="b@seelo.test")
    await jobs.defer(db, call_ai, args={"execution_id": 1}, links=jobs.JobLinks(store_id=s2, run_id=r2))
    # ③ 비용 대기 중 → 그대로
    s3, r3, _ = await seed_measuring(db, email="c@seelo.test")
    # ④ 29분 → 그대로
    s4, r4, _ = await seed_measuring(db, email="d@seelo.test")
    await db.execute(
        update(MeasurementRun).where(MeasurementRun.id == r3).values(waiting_reason="cost_limit")
    )
    await db.commit()
    await _age(db, [r1, r2, r3], 31)
    await _age(db, [r4], 29)
    await db.commit()

    counts = await maintenance.fail_stuck_work(db, now)
    await db.commit()
    assert counts == {"runs": 1, "fix_plans": 0, "reports": 0}
    db.expire_all()
    run1 = await db.get(MeasurementRun, r1)
    assert (run1.status, run1.failure_reason) == ("failed", "stuck")
    assert (await db.get(Store, s1)).status == "measure_failed"
    assert {(await db.get(MeasurementRun, r)).status for r in (r2, r3, r4)} == {"running"}
    mail = await db.scalar(select(EmailLog))
    assert mail.type == "diagnosis_result" and mail.template_params == {"result": "failed", "run_id": r1}


async def test_stuck_remeasure_marks_request_failed(db: AsyncSession, ai: Any) -> None:
    store_id, run_id, _ = await seed_measuring(db, kind="remeasure")
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="remeasuring"))
    await db.flush()
    req_id = await db.scalar(select(FixRequest.id))
    await db.execute(update(MeasurementRun).where(MeasurementRun.id == run_id).values(fix_request_id=req_id))
    await _age(db, [run_id], 60)
    await db.execute(text("UPDATE stores SET status = 'diagnosed' WHERE id = :i"), {"i": store_id})
    await db.commit()
    await maintenance.fail_stuck_work(db)
    await db.commit()
    db.expire_all()
    assert (await db.get(FixRequest, req_id)).status == "remeasure_failed"
    assert (await db.get(Store, store_id)).status == "diagnosed"  # 재측정은 가게 상태를 바꾸지 않는다
    assert await db.scalar(select(func.count()).select_from(EmailLog)) == 0


def test_periodic_jobs_registered() -> None:
    import seelo.worker.periodic  # noqa: F401
    from seelo.worker.app import app

    crons = {t.task.name: t.cron for t in app.periodic_registry.periodic_tasks.values()}
    assert crons["retryStalledJobs"] == "*/10 * * * *" and crons["failStuckWork"] == "*/10 * * * *"
