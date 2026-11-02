"""재측정·보고서 직전 상태(10 1~3장). 기존 가게·정비 도우미 재사용."""

from datetime import timedelta

from sqlalchemy import select

from seelo.models.fix import FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.store import Store
from seelo.services import fix_apply_service
from seelo.timeutil import now_utc
from tests.map_world import approved_plan, seed_measuring


async def scheduled_world(db, *, email="owner@seelo.test", days=14):
    store_id, run_id, qids = await seed_measuring(db, email=email)
    base = await db.get(MeasurementRun, run_id)
    base.status, base.stage, base.completed_at = "completed", "done", now_utc() - timedelta(days=30)
    store = await db.get(Store, store_id)
    store.status = "diagnosed"
    req = FixRequest(user_id=store.owner_id, store_id=store_id, status="fixing", base_run_id=run_id)
    db.add(req)
    await db.flush()
    w = {
        "store_id": store_id,
        "run_id": run_id,
        "request_id": req.id,
        "qids": qids,
        "question_set_id": base.question_set_id,
        "owner_id": store.owner_id,
    }
    for p in ("google", "kakao"):
        db.add(MapConnection(fix_request_id=req.id, provider=p, status="connected"))
    await db.commit()
    plan = await approved_plan(
        db,
        w,
        "google",
        {"phone": "02-123-4567", "description": "Seelo cafe"},
        status="manual_done",
        method="manual",
    )
    w.update(plan)
    await fix_apply_service.finalize(w["request_id"])
    db.expire_all()
    schedule = await db.scalar(
        select(RemeasureSchedule).where(RemeasureSchedule.fix_request_id == w["request_id"])
    )
    w["schedule_id"] = schedule.id
    # 특정 경과일의 예약. 기본은 14일, 즉시 실행 API는 이 값을 현재로 바꾼다.
    req = await db.get(FixRequest, w["request_id"])
    req.fix_completed_at = now_utc() - timedelta(days=days)
    schedule.due_at = req.fix_completed_at + timedelta(days=14)
    await db.commit()
    return w


async def completed_remeasure(db, *, days=14):
    from seelo.domain.states import transition
    from seelo.services import remeasure_service

    w = await scheduled_world(db, days=days)
    runs = await remeasure_service.dispatch([w["schedule_id"]])
    w["after_id"] = runs[0]
    await transition(
        db, MeasurementRun, runs[0], from_={"queued"}, to="running", values={"started_at": now_utc()}
    )
    await transition(db, MeasurementRun, runs[0], from_={"running"}, to="parsing")
    await transition(
        db,
        MeasurementRun,
        runs[0],
        from_={"parsing"},
        to="completed",
        values={"completed_at": now_utc(), "stage": "done"},
    )
    await db.commit()
    return w
