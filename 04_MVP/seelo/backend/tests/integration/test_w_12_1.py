"""W-12-1 예약·즉시 재측정(E19·E20)."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from seelo.models.fix import FixRequest, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import AuditLog, JobLink
from seelo.models.user import User
from seelo.services import remeasure_service
from seelo.timeutil import now_utc
from tests.report_world import scheduled_world
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


async def test_only_due_schedules_and_same_question_set(db):
    w = await scheduled_world(db)
    req = await db.get(FixRequest, w["request_id"])
    req_id = req.id
    schedule = await db.get(RemeasureSchedule, w["schedule_id"])
    schedule.due_at = now_utc() + timedelta(minutes=1)
    await db.commit()
    assert await remeasure_service.dispatch() == []
    schedule.due_at = now_utc() - timedelta(seconds=1)
    await db.commit()
    ids = await remeasure_service.dispatch()
    assert len(ids) == 1
    db.expire_all()
    run = await db.get(MeasurementRun, ids[0])
    assert (run.kind, run.trigger, run.is_free, run.question_set_id) == (
        "remeasure",
        "scheduler",
        False,
        w["question_set_id"],
    )
    assert (await db.get(FixRequest, req_id)).status == "remeasuring"
    schedule = await db.get(RemeasureSchedule, w["schedule_id"])
    assert schedule.status == "started" and schedule.run_id == run.id and schedule.started_at
    assert await remeasure_service.dispatch() == []


async def test_concurrent_dispatch_one_run_and_job(db):
    await scheduled_world(db)
    results = await asyncio.gather(remeasure_service.dispatch(), remeasure_service.dispatch())
    assert sum(map(len, results)) == 1
    assert (
        await db.scalar(
            select(func.count()).select_from(MeasurementRun).where(MeasurementRun.kind == "remeasure")
        )
        == 1
    )
    assert (
        await db.scalar(select(func.count()).select_from(JobLink).where(JobLink.task_name == "collectStore"))
        == 1
    )


async def test_now_api_audit_and_duplicate(db, client):
    w = await scheduled_world(db, days=3)
    await login(client, "owner@seelo.test")
    path = f"/api/admin/fix-requests/{w['request_id']}/remeasure-now"
    assert (await client.post(path)).status_code == 403
    admin = await make_user(db, "admin@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, "admin@seelo.test")
    r = await client.post(path)
    assert r.status_code == 202, r.text
    run_id = r.json()["runId"]
    assert (await client.post(path)).status_code == 409
    db.expire_all()
    run = await db.get(MeasurementRun, run_id)
    assert run.trigger == "admin" and run.question_set_id == w["question_set_id"]
    schedule = await db.get(RemeasureSchedule, w["schedule_id"])
    assert schedule.triggered_by == "admin" and schedule.status == "started"
    assert (
        await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "remeasure.now"))
        == 1
    )


async def test_invalid_request_cancels_schedule_and_deleted_owner_cascades(db):
    w = await scheduled_world(db)
    await db.execute(text("UPDATE fix_requests SET status='fixing' WHERE id=:id"), {"id": w["request_id"]})
    await db.commit()
    assert await remeasure_service.dispatch() == []
    db.expire_all()
    assert (await db.get(RemeasureSchedule, w["schedule_id"])).status == "canceled"
    owner = await db.get(User, w["owner_id"])
    await db.delete(owner)
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(RemeasureSchedule)) == 0


async def test_dispatch_rollback_does_not_leave_run_or_job(db, monkeypatch):
    await scheduled_world(db)

    async def fail(*args, **kwargs):
        raise RuntimeError("defer failed")

    monkeypatch.setattr(remeasure_service.jobs, "defer", fail)
    with pytest.raises(RuntimeError):
        await remeasure_service.dispatch()
    db.expire_all()
    assert (
        await db.scalar(
            select(func.count()).select_from(MeasurementRun).where(MeasurementRun.kind == "remeasure")
        )
        == 0
    )
    assert (await db.scalar(select(RemeasureSchedule))).status == "scheduled"
