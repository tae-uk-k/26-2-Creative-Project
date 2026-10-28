"""2단계: 작업 등록이 서비스 데이터와 같은 트랜잭션에 묶이는지(06 3장, 12 2단계 완료 조건)."""

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import AuditLog, JobLink
from seelo.models.store import Store
from seelo.models.user import User
from seelo.services import audit, email_service, jobs
from seelo.timeutil import now_utc
from seelo.worker.tasks_email import send_email


async def _job_rows(db: AsyncSession) -> list[Any]:
    return (
        await db.execute(text("SELECT id, task_name, status, args FROM procrastinate_jobs ORDER BY id"))
    ).all()


async def test_rollback_leaves_no_job(db: AsyncSession, queue_app: Any) -> None:
    await email_service.queue(
        db, "fix_requested", to="a@seelo.test", params={"request_id": 1, "store_name": "x"}
    )
    await db.rollback()
    assert await _job_rows(db) == []
    assert await db.scalar(select(func.count()).select_from(JobLink)) == 0


async def test_duplicate_queueing_lock_keeps_outer_changes(db: AsyncSession, queue_app: Any) -> None:
    first = await jobs.defer(
        db, send_email, args={"email_log_id": 1}, links=jobs.JobLinks(), queueing_lock="dup"
    )
    second = await jobs.defer(
        db, send_email, args={"email_log_id": 2}, links=jobs.JobLinks(), queueing_lock="dup"
    )
    audit.record(db, actor_id=None, action="fix_request.approve", target_type="fix_request", target_id=1)
    await db.commit()

    assert first is not None and second is None
    rows = await _job_rows(db)
    assert [(r.id, r.args) for r in rows] == [(first, {"email_log_id": 1})]
    assert await db.scalar(select(func.count()).select_from(JobLink)) == 1
    assert await db.scalar(select(func.count()).select_from(AuditLog)) == 1


async def test_committed_job_runs_in_worker(db: AsyncSession, queue_app: Any, fake_mailer: Any) -> None:
    log_id = await email_service.queue(
        db, "fix_requested", to="a@seelo.test", params={"request_id": 3, "store_name": "데모식당"}
    )
    # 커밋 전에는 다른 연결(워커)에서 보이지 않는다
    async with queue_app.connector.pool.connection() as conn:
        cur = await conn.execute("SELECT count(*) FROM procrastinate_jobs")
        assert (await cur.fetchone())[0] == 0
    await db.commit()

    await queue_app.run_worker_async(queues=["email"], wait=False, install_signal_handlers=False)

    # 워커는 시각에 따라 주기 작업(cleanupUnverified)도 등록하므로 sendEmail만 본다
    rows = [r for r in await _job_rows(db) if r.task_name == "sendEmail"]
    assert [(r.task_name, r.status) for r in rows] == [("sendEmail", "succeeded")]
    db.expire_all()
    status = (await db.execute(text("SELECT status FROM email_logs WHERE id = :i"), {"i": log_id})).scalar()
    assert status == "sent"
    assert [m["to"] for m in fake_mailer.sent] == [["a@seelo.test"]]


async def test_cancel_jobs_for_store(db: AsyncSession, queue_app: Any) -> None:
    user = User(email="c@seelo.test", email_verified_at=now_utc(), terms_agreed_at=now_utc())
    db.add(user)
    await db.flush()
    store = Store(
        owner_id=user.id,
        name="취소 시험",
        input_url="https://maps.app.goo.gl/x",
        input_provider="google",
        category="cafe",
        status="collecting",
    )
    db.add(store)
    await db.flush()
    store_id = store.id
    job_id = await jobs.defer(
        db, send_email, args={"email_log_id": 9}, links=jobs.JobLinks(store_id=store_id), queueing_lock="c1"
    )
    other = await jobs.defer(
        db, send_email, args={"email_log_id": 10}, links=jobs.JobLinks(), queueing_lock="c2"
    )
    await db.commit()

    assert await jobs.cancel_jobs(db, store_ids=[store_id]) == 1
    status = {r.id: r.status for r in await _job_rows(db)}
    assert status == {job_id: "cancelled", other: "todo"}
    assert await jobs.cancel_jobs(db, store_ids=[]) == 0
