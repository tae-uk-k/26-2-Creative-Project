"""정비 신청(09 1장, 04 7.1, 03 E8·E9·E10·E26, W-08).

- 신청(E8): 가게가 diagnosed·collected이고 rejected가 아닌 신청이 없을 때만. 동시 신청은 부분 고유 인덱스
  `uq_fix_request_store_active` 위반 → 409 ALREADY_REQUESTED. 관리자에게 메일 fix_requested.
- 승인(E9)·거절(E10)은 조건부 전이. 이미 처리된 신청이면 409 INVALID_STATE. 감사 기록·메일 fix_decided.
- 승인할 때 기준 측정(base_run_id)이 없으면(무료 사용 뒤 바꾼 가게) 측정부터 다시 한다(collectStore).
"""

from datetime import date

import structlog
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.fix_steps import fix_steps
from seelo.domain.states import (
    ConnectionStatus,
    FixRequestStatus,
    RunKind,
    RunStage,
    RunStatus,
    RunTrigger,
    StoreStatus,
    transition,
)
from seelo.errors import AppError
from seelo.models.fix import FixPlan, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import Store
from seelo.models.user import User
from seelo.schemas.admin import StatusResponse
from seelo.schemas.fix import CreatedRequest, FixRequestState, FixRequestView, FixStep
from seelo.schemas.run import RunIdResponse
from seelo.services import audit, email_service, jobs
from seelo.services.eligibility import current_store
from seelo.services.store_service import RETRY_PER_DAY, retries_used_today
from seelo.timeutil import kst_date, now_utc

log = structlog.get_logger()

REQUESTABLE_STORE = (StoreStatus.DIAGNOSED, StoreStatus.COLLECTED)
MAP_PROVIDERS = ("google", "kakao")


async def _has_open_request(db: AsyncSession, store_id: int) -> bool:
    """rejected가 아닌 신청(진행 중·완료 모두)이 있음."""
    return bool(
        await db.scalar(
            select(
                exists().where(
                    FixRequest.store_id == store_id, FixRequest.status != FixRequestStatus.REJECTED
                )
            )
        )
    )


async def can_request_fix(db: AsyncSession, store: Store) -> bool:
    """03 7장: 가게 diagnosed·collected이고 rejected가 아닌 신청이 없음."""
    return store.status in REQUESTABLE_STORE and not await _has_open_request(db, store.id)


async def _latest_diagnosis(db: AsyncSession, store_id: int) -> int | None:
    return await db.scalar(
        select(MeasurementRun.id)
        .where(
            MeasurementRun.store_id == store_id,
            MeasurementRun.kind == RunKind.DIAGNOSIS,
            MeasurementRun.status == RunStatus.COMPLETED,
        )
        .order_by(MeasurementRun.id.desc())
        .limit(1)
    )


# --- S12 상태 -----------------------------------------------------------------------------


async def _view(db: AsyncSession, req: FixRequest) -> FixRequestView:
    connected = bool(
        await db.scalar(
            select(
                exists().where(
                    MapConnection.fix_request_id == req.id, MapConnection.status == ConnectionStatus.CONNECTED
                )
            )
        )
    )
    plans = (await db.scalars(select(FixPlan).where(FixPlan.fix_request_id == req.id))).all()
    latest: dict[str, FixPlan] = {}
    for p in plans:  # 지도별 최신 버전
        if p.provider not in latest or p.version > latest[p.provider].version:
            latest[p.provider] = p
    steps = fix_steps(
        req.status, connected=connected, plan_statuses={p.id: p.status for p in latest.values()}
    )
    sched = await db.scalar(
        select(RemeasureSchedule)
        .where(RemeasureSchedule.fix_request_id == req.id, RemeasureSchedule.status == "scheduled")
        .order_by(RemeasureSchedule.id.desc())
        .limit(1)
    )
    report_id = await db.scalar(
        select(ComparisonReport.id)
        .where(ComparisonReport.fix_request_id == req.id, ComparisonReport.status == "completed")
        .order_by(ComparisonReport.version.desc())
        .limit(1)
    )
    due: date | None = kst_date(sched.due_at) if sched else None
    return FixRequestView(
        id=req.id,
        status=req.status,
        created_at=req.created_at,
        reject_reason=req.reject_reason,
        has_base_run=req.base_run_id is not None,
        steps=[FixStep(key=s.key, state=s.state, action_path=s.action_path) for s in steps],  # type: ignore[arg-type]
        remeasure_due_date=due,
        report_id=report_id,
    )


async def state(db: AsyncSession, user: User) -> FixRequestState:
    store = await current_store(db, user.id)
    if store is None:
        return FixRequestState(request=None, can_request=False, needs_measurement_first=False)
    req = await db.scalar(
        select(FixRequest).where(FixRequest.store_id == store.id).order_by(FixRequest.id.desc()).limit(1)
    )
    return FixRequestState(
        request=await _view(db, req) if req is not None else None,
        can_request=await can_request_fix(db, store),
        needs_measurement_first=store.status == StoreStatus.COLLECTED,
    )


# --- E8 신청 ------------------------------------------------------------------------------


async def create(db: AsyncSession, user: User) -> CreatedRequest:
    store = await current_store(db, user.id, for_update=True)  # 같은 가게의 신청을 한 줄로
    if store is None:
        raise AppError("NO_STORE")
    if await _has_open_request(db, store.id):
        raise AppError("ALREADY_REQUESTED")
    if store.status not in REQUESTABLE_STORE:
        raise AppError("NOT_ELIGIBLE", {"reason": "store_not_ready"})
    req = FixRequest(
        user_id=user.id,
        store_id=store.id,
        status=FixRequestStatus.REQUESTED,
        base_run_id=await _latest_diagnosis(db, store.id),
    )
    db.add(req)
    try:
        await db.flush()
    except IntegrityError as e:  # 동시 신청: 부분 고유 인덱스 위반
        await db.rollback()
        raise AppError("ALREADY_REQUESTED") from e
    request_id, store_name = req.id, store.name
    await email_service.queue(
        db,
        "fix_requested",
        params={"request_id": request_id, "store_name": store_name},
        dedupe_key=f"fix_requested:{request_id}",
    )  # 받는 사람: 관리자 주소(ADMIN_NOTIFY_EMAILS)
    await db.commit()
    log.info("fix_requested", request_id=request_id, store_id=store.id)
    return CreatedRequest(request_id=request_id)


# --- E9·E10 관리자 결정 ---------------------------------------------------------------------


async def _decided(db: AsyncSession, request_id: int, to: str, admin: User, **values: object) -> FixRequest:
    req = await db.get(FixRequest, request_id, with_for_update=True)
    if req is None:
        raise AppError("NOT_FOUND")
    moved = await transition(
        db,
        FixRequest,
        request_id,
        from_={FixRequestStatus.REQUESTED},
        to=to,
        values={"decided_by": admin.id, "decided_at": now_utc(), **values},
    )
    if not moved:
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    return req


async def approve(db: AsyncSession, admin: User, request_id: int) -> StatusResponse:
    """E9: approved, 연결 2행(not_connected). 기준 측정이 있으면 connecting, 없으면 가게 측정부터."""
    req = await _decided(db, request_id, FixRequestStatus.APPROVED, admin)
    store_id, owner_id, base_run_id = req.store_id, req.user_id, req.base_run_id
    db.add_all(
        MapConnection(fix_request_id=request_id, provider=p, status=ConnectionStatus.NOT_CONNECTED)
        for p in MAP_PROVIDERS
    )
    status = FixRequestStatus.APPROVED
    if base_run_id is not None:
        await transition(
            db, FixRequest, request_id, from_={FixRequestStatus.APPROVED}, to=FixRequestStatus.CONNECTING
        )
        status = FixRequestStatus.CONNECTING
    else:
        await _measure_first(db, store_id, request_id)
    owner = await db.get(User, owner_id)
    await email_service.queue(
        db,
        "fix_decided",
        user=owner,
        params={"decision": "approved", "reject_reason": None},
        dedupe_key=f"fix_decided:{request_id}",
    )
    audit.record(
        db, actor_id=admin.id, action="fix_request.approve", target_type="fix_request", target_id=request_id
    )
    await db.commit()
    log.info("fix_request_approved", request_id=request_id, status=str(status))
    return StatusResponse(status=status)


async def _measure_first(db: AsyncSession, store_id: int, request_id: int) -> None:
    """E9 기준 측정 없음: 가게 collected → collecting, 진단 측정(무료 아님, 신청 연결) + collectStore."""
    moved = await transition(db, Store, store_id, from_={StoreStatus.COLLECTED}, to=StoreStatus.COLLECTING)
    if not moved:
        store = await db.get(Store, store_id)
        raise AppError("INVALID_STATE", {"currentStatus": store.status if store else "no_store"})
    run = MeasurementRun(
        store_id=store_id,
        kind=RunKind.DIAGNOSIS,
        is_free=False,
        trigger=RunTrigger.INITIAL,
        status=RunStatus.QUEUED,
        stage=RunStage.COLLECTING,
        fix_request_id=request_id,
    )
    db.add(run)
    await db.flush()
    from seelo.worker.tasks_collect import collect_store

    await jobs.defer(
        db,
        collect_store,
        args={"store_id": store_id, "run_id": run.id},
        links=jobs.JobLinks(store_id=store_id, run_id=run.id, fix_request_id=request_id),
        queueing_lock=f"collect:{store_id}:{run.id}",
        lock=f"store:{store_id}",
    )


async def reject(db: AsyncSession, admin: User, request_id: int, reason: str) -> StatusResponse:
    reason = reason.strip()
    if not reason:
        raise AppError("REJECT_REASON_REQUIRED")
    req = await _decided(db, request_id, FixRequestStatus.REJECTED, admin, reject_reason=reason)
    owner = await db.get(User, req.user_id)
    await email_service.queue(
        db,
        "fix_decided",
        user=owner,
        params={"decision": "rejected", "reject_reason": reason},
        dedupe_key=f"fix_decided:{request_id}",
    )
    audit.record(
        db,
        actor_id=admin.id,
        action="fix_request.reject",
        target_type="fix_request",
        target_id=request_id,
        detail={"reason": reason},
    )
    await db.commit()
    log.info("fix_request_rejected", request_id=request_id)
    return StatusResponse(status=FixRequestStatus.REJECTED)


# --- E26 재측정 다시 시도 -------------------------------------------------------------------


async def retry_remeasure(db: AsyncSession, user: User) -> RunIdResponse:
    """E26: 신청 remeasure_failed → remeasuring, 재측정(trigger retry, 기준 측정의 질문). 하루 3번."""
    store = await current_store(db, user.id, for_update=True)
    req = (
        await db.scalar(
            select(FixRequest).where(FixRequest.store_id == store.id).order_by(FixRequest.id.desc()).limit(1)
        )
        if store
        else None
    )
    if store is None or req is None or req.status != FixRequestStatus.REMEASURE_FAILED:
        raise AppError("INVALID_STATE", {"currentStatus": req.status if req else "no_request"})
    if await retries_used_today(db, store.id) >= RETRY_PER_DAY:
        raise AppError("RETRY_LIMIT")
    base = await db.get(MeasurementRun, req.base_run_id) if req.base_run_id else None
    moved = await transition(
        db,
        FixRequest,
        req.id,
        from_={FixRequestStatus.REMEASURE_FAILED},
        to=FixRequestStatus.REMEASURING,
    )
    if not moved:
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    run = MeasurementRun(
        store_id=store.id,
        kind=RunKind.REMEASURE,
        is_free=False,
        trigger=RunTrigger.RETRY,
        status=RunStatus.QUEUED,
        stage=RunStage.COLLECTING,
        fix_request_id=req.id,
        question_set_id=base.question_set_id if base else None,
    )
    db.add(run)
    await db.flush()
    from seelo.worker.tasks_collect import collect_store

    await jobs.defer(
        db,
        collect_store,
        args={"store_id": store.id, "run_id": run.id},
        links=jobs.JobLinks(store_id=store.id, run_id=run.id, fix_request_id=req.id),
        queueing_lock=f"collect:{store.id}:{run.id}",
        lock=f"store:{store.id}",
    )
    run_id = run.id
    await db.commit()
    return RunIdResponse(run_id=run_id)
