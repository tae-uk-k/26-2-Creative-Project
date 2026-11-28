"""재측정 시작·읽기 전용 값 비교(10 1·2장, E19~E21)."""

import asyncio
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import session_scope
from seelo.domain.attributes import ATTRIBUTES, google_value
from seelo.domain.field_dictionary import same_value, spec
from seelo.domain.hours import from_google_periods
from seelo.domain.states import transition
from seelo.errors import AppError
from seelo.integrations import Clients, get_clients
from seelo.integrations.browser.guards import FieldWriteFailed, StoreNotVisible, TransientAutomationError
from seelo.models.fix import FixLog, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import SourceSnapshot, Store
from seelo.models.user import User
from seelo.schemas.run import RunIdResponse
from seelo.services import audit, connection_service, fix_plan_service, jobs
from seelo.timeutil import now_utc

log = structlog.get_logger()
COMPARE_STATUSES = {"applied", "manual_done", "pending_reflection"}
PLACE_FIELDS = {"regular_hours", "website", "phone", "attributes"}


async def _start(s: AsyncSession, schedule_id: int, *, admin: User | None = None) -> int | None:
    req_id = await s.scalar(
        select(RemeasureSchedule.fix_request_id).where(RemeasureSchedule.id == schedule_id)
    )
    req = await s.get(FixRequest, req_id, with_for_update=True) if req_id else None
    schedule = await s.get(RemeasureSchedule, schedule_id, with_for_update=True)
    now = now_utc()
    if schedule is None or schedule.status != "scheduled" or (admin is None and schedule.due_at > now):
        return None
    store = await s.get(Store, req.store_id) if req else None
    base = await s.get(MeasurementRun, req.base_run_id) if req and req.base_run_id else None
    if req is None or req.status != "remeasure_scheduled" or store is None or store.status == "archived":
        await transition(s, RemeasureSchedule, schedule_id, from_={"scheduled"}, to="canceled")
        log.warning("remeasure_schedule_canceled", schedule_id=schedule_id)
        return None
    if base is None or base.question_set_id is None:
        # 질문을 새로 만들거나 서로 다른 조건으로 비교하지 않는다.
        log.warning("remeasure_base_missing", fix_request_id=req.id)
        if admin:
            raise AppError("INVALID_STATE", {"currentStatus": "base_questions_missing"})
        return None
    trigger = "admin" if admin else schedule.triggered_by
    await transition(s, FixRequest, req.id, from_={"remeasure_scheduled"}, to="remeasuring")
    run = MeasurementRun(
        store_id=req.store_id,
        fix_request_id=req.id,
        question_set_id=base.question_set_id,
        kind="remeasure",
        is_free=False,
        trigger=trigger,
        status="queued",
        stage="collecting",
    )
    s.add(run)
    await s.flush()
    values = {"run_id": run.id, "started_at": now}
    if admin:
        values.update(due_at=now, triggered_by="admin")
    await transition(s, RemeasureSchedule, schedule_id, from_={"scheduled"}, to="started", values=values)
    from seelo.worker.tasks_collect import collect_store

    await jobs.defer(
        s,
        collect_store,
        args={"store_id": req.store_id, "run_id": run.id},
        links=jobs.JobLinks(store_id=req.store_id, run_id=run.id, fix_request_id=req.id),
        queueing_lock=f"collect:{req.store_id}:{run.id}",
        lock=f"store:{req.store_id}",
    )
    if admin:
        audit.record(
            s, actor_id=admin.id, action="remeasure.now", target_type="fix_request", target_id=req.id
        )
    return run.id


async def dispatch(schedule_ids: list[int] | None = None) -> list[int]:
    """예약마다 신청을 잠그고 측정·큐를 함께 커밋한다(E19)."""
    if schedule_ids is None:
        async with session_scope() as s:
            schedule_ids = list(
                await s.scalars(
                    select(RemeasureSchedule.id)
                    .where(
                        RemeasureSchedule.status == "scheduled",
                        RemeasureSchedule.due_at <= now_utc(),
                    )
                    .order_by(RemeasureSchedule.id)
                )
            )
    runs = []
    for sid in schedule_ids:
        async with session_scope() as s:
            run_id = await _start(s, sid)
            await s.commit()
            if run_id is not None:
                runs.append(run_id)
    return runs


async def remeasure_now(db: AsyncSession, admin: User, request_id: int) -> RunIdResponse:
    req = await db.get(FixRequest, request_id, with_for_update=True)
    if req is None:
        raise AppError("NOT_FOUND")
    if req.status != "remeasure_scheduled":
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    sid = await db.scalar(
        select(RemeasureSchedule.id).where(
            RemeasureSchedule.fix_request_id == request_id,
            RemeasureSchedule.status == "scheduled",
        )
    )
    run_id = await _start(db, sid, admin=admin) if sid else None
    if run_id is None:
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    await db.commit()
    return RunIdResponse(run_id=run_id)


async def defer_compare(s: AsyncSession, request_id: int, run_id: int, store_id: int) -> None:
    """관리 화면을 읽지 않으면 plan 큐. 수동 모드에 fix 워커가 없다(06 4장)."""
    from seelo.worker.tasks_report import compare_fix_values

    rows = (
        await s.execute(
            select(FixLog.provider, FixLog.field)
            .join(
                MapConnection,
                (MapConnection.fix_request_id == FixLog.fix_request_id)
                & (MapConnection.provider == FixLog.provider),
            )
            .where(
                FixLog.fix_request_id == request_id,
                FixLog.status.in_(COMPARE_STATUSES),
                MapConnection.status == "connected",
            )
        )
    ).all()
    admin_providers = {
        p
        for p, f in rows
        if fix_plan_service.reads_current_values(p) and (p == "kakao" or f not in PLACE_FIELDS)
    }
    browser = bool(admin_providers)
    await jobs.defer(
        s,
        compare_fix_values,
        args={"fix_request_id": request_id, "run_id": run_id},
        links=jobs.JobLinks(store_id=store_id, run_id=run_id, fix_request_id=request_id),
        queueing_lock=f"compare:{request_id}:{run_id}",
        queue="fix" if browser else "plan",
        lock=("fix:kakao" if "kakao" in admin_providers else "fix:google") if browser else None,
    )


def _place_value(g: dict, field: str, applied: Any) -> Any:
    if field == "regular_hours":
        hours = g.get("regularOpeningHours")
        return from_google_periods(hours.get("periods")) if hours and "periods" in hours else None
    if field == "attributes":
        return (
            {k: google_value(k, g) if k in ATTRIBUTES else None for k in applied}
            if isinstance(applied, dict)
            else None
        )
    return g.get({"website": "websiteUri", "phone": "nationalPhoneNumber"}.get(field, ""))


async def compare_fix_values(request_id: int, run_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        req = await s.get(FixRequest, request_id)
        run = await s.get(MeasurementRun, run_id)
        if (
            req is None
            or req.status != "remeasuring"
            or run is None
            or run.kind != "remeasure"
            or run.status != "completed"
            or run.fix_request_id != request_id
            or run.store_id != req.store_id
        ):
            return
        if await s.scalar(
            select(ComparisonReport.id).where(
                ComparisonReport.fix_request_id == request_id,
                ComparisonReport.after_run_id == run_id,
            )
        ):
            return
        logs = list(
            await s.scalars(
                select(FixLog).where(
                    FixLog.fix_request_id == request_id,
                    FixLog.status.in_(COMPARE_STATUSES),
                )
            )
        )
        items = [(r.id, r.provider, r.field, r.applied_value) for r in logs]
        connections = {
            c.provider: (c.status, c.external_ref)
            for c in await s.scalars(select(MapConnection).where(MapConnection.fix_request_id == request_id))
        }
        snap = await s.scalar(
            select(SourceSnapshot)
            .where(
                SourceSnapshot.run_id == run_id,
                SourceSnapshot.provider == "google",
                SourceSnapshot.status == "ok",
            )
            .order_by(SourceSnapshot.id.desc())
            .limit(1)
        )
        google = (snap.payload or {}).get("ko") or {} if snap else {}
        ref = await connection_service.store_ref(s, req.store_id)
        await s.commit()

    values: dict[int, Any] = {}
    revoked = set()
    for provider in ("google", "kakao"):
        subset = [(i, f, a) for i, p, f, a in items if p == provider]
        admin_items = []
        for i, f, applied in subset:
            if provider == "google" and f in PLACE_FIELDS:
                values[i] = _place_value(google, f, applied)
            else:
                admin_items.append((i, f))
        status, external_ref = connections.get(provider, (None, None))
        if not admin_items or status != "connected" or not fix_plan_service.reads_current_values(provider):
            continue
        try:
            async with asyncio.timeout(120):
                async with clients.map_admin(provider) as admin:
                    await admin.open_store(ref, external_ref)
                    # 칸별 실패는 그 칸만 unknown. 차단은 같은 지도 읽기를 즉시 끝낸다.
                    for i, field in admin_items:
                        try:
                            got = await admin.read_fields([field])
                            values[i] = got[field].value if field in got else None
                        except (KeyError, ValueError, FieldWriteFailed, TransientAutomationError):
                            values[i] = None
        except StoreNotVisible:
            revoked.add(provider)
        except Exception as e:
            log.warning(
                "compare_read_unknown", request_id=request_id, provider=provider, error=type(e).__name__
            )

    async with session_scope() as s:
        req = await s.get(FixRequest, request_id, with_for_update=True)
        run = await s.get(MeasurementRun, run_id)
        if req is None or req.status != "remeasuring" or run is None or run.status != "completed":
            return
        if await s.scalar(
            select(ComparisonReport.id).where(
                ComparisonReport.fix_request_id == request_id,
                ComparisonReport.after_run_id == run_id,
            )
        ):
            return
        for provider in revoked:
            await connection_service.revoke(s, request_id, provider)
        for i, provider, field, applied in items:
            lg = await s.get(FixLog, i)
            if lg is None or lg.status not in COMPARE_STATUSES:
                continue
            value = values.get(i)
            field_spec = spec(provider, field)
            unknown = value is None or (
                field == "attributes" and isinstance(value, dict) and any(v is None for v in value.values())
            )
            lg.remeasure_value = value
            lg.remeasure_match = (
                "unknown"
                if unknown or field_spec is None
                else ("match" if same_value(field_spec.type, applied, value) else "differs")
            )
        # E26 재시도도 최초 예약의 관리자 실행을 이어받고, 경과일은 성공 측정의 시작 시각 기준.
        schedule = await s.scalar(
            select(RemeasureSchedule)
            .where(
                RemeasureSchedule.fix_request_id == request_id,
                RemeasureSchedule.status == "started",
            )
            .order_by(RemeasureSchedule.id.desc())
            .limit(1)
        )
        started = schedule.started_at if schedule and schedule.run_id == run_id else run.started_at
        interval = (
            (started - req.fix_completed_at) // timedelta(days=1) if started and req.fix_completed_at else 0
        )
        from seelo.services import report_service

        await report_service.create(s, req, run_id, interval_days=interval)
        await s.commit()
