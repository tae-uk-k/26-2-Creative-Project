"""정비 실행·완료(09 9~11·13장, 03 E16·E17·E30·E32, W-09-5·6·7).

- applyFix(E16): 승인한 칸(queued)만 order_no 순으로 쓴다. 칸마다 지금 값을 읽어 before_value·attempt를
  **먼저 커밋한 뒤** 쓰고, 다시 읽어 같으면 applied, 아니면(검토 중 포함) pending_reflection.
  차단(로그인·보안 확인·예상 밖 화면)은 다시 시도하지 않고 그 칸과 남은 칸 모두 manual_required.
  일시 오류는 그 칸만 1번 더. 그래도 실패하거나 쓸 수 없는 칸이면 그 칸만 manual_required(write_failed).
  가게가 안 보이면 권한 회수(E18).
- verifyFix·recheckPendingFixes(E32): 반영 대기 칸을 매시간 **읽기만** 해서 확인한다.
  24시간 지나면 manual_required.
- finalizeFix(E17): 신청이 fixing이고 승인된 정비안의 칸이 모두 끝 상태(applied·manual_done·disconnected)면
  신청 → remeasure_scheduled, 재측정 예약(완료 + 14일), 메일 fix_completed. 신청 행을 잠그고 다시 읽으므로
  몇 번 불러도 결과가 같다. DB만 쓰므로 기본 워커(plan 큐)에서 돈다(수동 모드 compose에는 정비 워커가 없음).
- 관리자 [처리 완료](E30): manual_required → manual_done. 같은 트랜잭션에서 finalizeFix 등록.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import session_scope
from seelo.domain.field_dictionary import field_label, same_value, spec
from seelo.domain.labels import MAP_LABEL
from seelo.domain.states import (
    ConnectionStatus,
    FixLogStatus,
    FixMethod,
    FixPlanStatus,
    FixRequestStatus,
    ScheduleStatus,
    TriggeredBy,
    transition,
)
from seelo.errors import AppError
from seelo.integrations import Clients, get_clients
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.user import User
from seelo.schemas.admin import ManualDoneRequest, StatusResponse
from seelo.services import audit, email_service, jobs
from seelo.timeutil import kst_date, now_utc

log = structlog.get_logger()

REMEASURE_AFTER = timedelta(days=14)
DONE = {FixLogStatus.APPLIED, FixLogStatus.MANUAL_DONE, FixLogStatus.DISCONNECTED}
CHANGED = {FixLogStatus.APPLIED, FixLogStatus.MANUAL_DONE}
APPLY_ATTEMPTS = 2  # 칸별 일시 오류 1번 다시(06 4장). 차단은 0번
OPEN_ATTEMPTS = 2
FIELD_TIMEOUT_S = 180.0  # 칸 하나(읽기·쓰기·다시 읽기). 작업 전체 제한은 15분(06 4장)
REFLECT_LIMIT = timedelta(hours=24)  # D-15
RECHECK_AFTER = timedelta(minutes=55)


async def defer_finalize(s: AsyncSession, request_id: int, *, store_id: int) -> None:
    """finalizeFix 등록(칸 상태를 바꾸는 트랜잭션 안에서). 대기 중인 것이 있으면 하나로 합쳐진다."""
    from seelo.worker.tasks_fix import finalize_fix

    await jobs.defer(
        s,
        finalize_fix,
        args={"fix_request_id": request_id},
        links=jobs.JobLinks(store_id=store_id, fix_request_id=request_id),
        queueing_lock=f"finalizeFix:{request_id}",
        lock=f"request:{request_id}",
    )


# --- E16 자동 정비 -------------------------------------------------------------------------------


def _manual_item(provider: str, field_: str, reason: str) -> dict[str, str]:
    return {"provider": provider, "field_label": field_label(provider, field_), "reason": reason}


async def _to_manual(
    s: AsyncSession, log_id: int, *, from_: set[str], reason: str, error_code: str | None
) -> bool:
    return await transition(
        s,
        FixLog,
        log_id,
        from_=from_,
        to=FixLogStatus.MANUAL_REQUIRED,
        values={"manual_reason": reason, "error_code": error_code},
    )


async def _apply_one(
    admin: Any, provider: str, log_id: int, field_: str, value: Any
) -> tuple[str, str | None]:
    """칸 하나: 읽기 → before_value 커밋 → 쓰기 → 다시 읽기. (결과 상태, error_code).

    차단·권한 회수·인증 필요는 그대로 올린다(작업 전체를 멈춤).
    """
    after = None
    for attempt in range(1, APPLY_ATTEMPTS + 1):
        try:
            async with asyncio.timeout(FIELD_TIMEOUT_S):
                before = (await admin.read_fields([field_])).get(field_)
                async with session_scope() as s:  # 쓰기 전에 반드시 먼저 커밋(09 9장 3.1)
                    lg = await s.get(FixLog, log_id, with_for_update=True)
                    if lg is None or lg.status != FixLogStatus.QUEUED:
                        return "skipped", None
                    if lg.before_value is None and before is not None:
                        lg.before_value = before.value  # 다시 할 때는 처음 읽은 값을 지킨다
                    lg.attempt += 1
                    await s.commit()
                await admin.write_field(field_, value)
                after = (await admin.read_fields([field_])).get(field_)
            break
        except (TransientAutomationError, TimeoutError) as e:
            log.warning("apply_fix_transient", fix_log_id=log_id, field=field_, attempt=attempt, error=str(e))
            if attempt == APPLY_ATTEMPTS:
                return FixLogStatus.MANUAL_REQUIRED, "transient"
        except FieldWriteFailed as e:
            return FixLogStatus.MANUAL_REQUIRED, e.reason
    sp = spec(provider, field_)
    ok = (
        after is not None
        and not after.pending_review
        and same_value(sp.type if sp else "text", after.value, value)
    )
    return (FixLogStatus.APPLIED if ok else FixLogStatus.PENDING_REFLECTION), None


async def _save_result(
    log_id: int, status: str, error_code: str | None, *, request_id: int, store_id: int
) -> bool:
    now = now_utc()
    async with session_scope() as s:
        if status == FixLogStatus.MANUAL_REQUIRED:
            moved = await _to_manual(
                s, log_id, from_={FixLogStatus.QUEUED}, reason="write_failed", error_code=error_code
            )
        else:
            values: dict[str, Any] = {"applied_at": now}
            values |= {"verified_at": now} if status == FixLogStatus.APPLIED else {"last_checked_at": now}
            moved = await transition(s, FixLog, log_id, from_={FixLogStatus.QUEUED}, to=status, values=values)
        await defer_finalize(s, request_id, store_id=store_id)  # 칸 상태를 바꾸는 트랜잭션마다(09 9장 3.4)
        await s.commit()
    return moved


async def _stop_all(
    plan_id: int, provider: str, *, request_id: int, store_id: int, reason: str, error_code: str
) -> list[dict[str, str]]:
    """이 정비안의 남은 queued 칸을 모두 manual_required로(다시 시도하지 않음)."""
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(FixLog.id, FixLog.field)
                .join(FixPlanItem, FixPlanItem.id == FixLog.fix_plan_item_id)
                .where(FixPlanItem.fix_plan_id == plan_id, FixLog.status == FixLogStatus.QUEUED)
                .order_by(FixPlanItem.order_no)
            )
        ).all()
        items = []
        for log_id, field_ in rows:
            if await _to_manual(s, log_id, from_={FixLogStatus.QUEUED}, reason=reason, error_code=error_code):
                items.append(_manual_item(provider, field_, reason))
        await defer_finalize(s, request_id, store_id=store_id)
        await s.commit()
    return items


async def _mail_manual(request_id: int, items: list[dict[str, str]], dedupe_key: str) -> None:
    if not items:
        return
    async with session_scope() as s:
        await email_service.queue(
            s, "manual_required", params={"request_id": request_id, "items": items}, dedupe_key=dedupe_key
        )
        await s.commit()


async def apply(fix_plan_id: int, *, clients: Clients | None = None) -> None:
    from seelo.services import connection_service

    clients = clients or get_clients()
    async with session_scope() as s:
        plan = await s.get(FixPlan, fix_plan_id)
        req = await s.get(FixRequest, plan.fix_request_id) if plan else None
        conn = (
            await s.scalar(
                select(MapConnection).where(
                    MapConnection.fix_request_id == req.id, MapConnection.provider == plan.provider
                )
            )
            if req
            else None
        )
        if plan is None or plan.status != FixPlanStatus.APPROVED or conn is None:
            log.info("apply_fix_skip", fix_plan_id=fix_plan_id, reason="not_approved")
            return
        provider, request_id, store_id, external_ref = plan.provider, req.id, req.store_id, conn.external_ref
        todo = (
            await s.execute(
                select(FixLog.id, FixLog.field, FixLog.applied_value)
                .join(FixPlanItem, FixPlanItem.id == FixLog.fix_plan_item_id)
                .where(FixPlanItem.fix_plan_id == plan.id, FixLog.status == FixLogStatus.QUEUED)
                .order_by(FixPlanItem.order_no)
            )
        ).all()
        if conn.status != ConnectionStatus.CONNECTED or not todo:
            # 쓸 칸이 없음(정비 완료 뒤 포함). 연결이 끊겼으면 권한 회수(E18)가 남은 칸을 이미 정리했다
            await defer_finalize(s, request_id, store_id=store_id)
            await s.commit()
            log.info(
                "apply_fix_skip", fix_plan_id=fix_plan_id, reason="nothing_to_write", connection=conn.status
            )
            return
        ref = await connection_service.store_ref(s, store_id)
        await s.commit()  # 화면을 여는 동안 트랜잭션을 열어 두지 않는다

    keys = {"request_id": request_id, "store_id": store_id}
    failed: list[dict[str, str]] = []
    counts = {"applied": 0, "pending_reflection": 0, "manual_required": 0}
    try:
        async with clients.map_admin(provider) as admin:
            for attempt in range(1, OPEN_ATTEMPTS + 1):
                try:
                    await admin.open_store(ref, external_ref)
                    break
                except TransientAutomationError:
                    if attempt == OPEN_ATTEMPTS:
                        raise
            for log_id, field_, value in todo:
                status, error_code = await _apply_one(admin, provider, log_id, field_, value)
                if status == "skipped" or not await _save_result(log_id, status, error_code, **keys):
                    continue
                counts[status] += 1
                if status == FixLogStatus.MANUAL_REQUIRED:
                    failed.append(_manual_item(provider, field_, "write_failed"))
    except (AutomationBlocked, AttentionNeeded) as e:  # 다시 시도하지 않는다
        items = await _stop_all(
            fix_plan_id, provider, reason="automation_blocked", error_code=e.reason, **keys
        )
        await _mail_manual(request_id, items, f"manual_required:plan:{fix_plan_id}:blocked")
        log.warning("apply_fix_blocked", fix_plan_id=fix_plan_id, reason=e.reason, stopped=len(items))
    except StoreNotVisible:
        async with session_scope() as s:
            await connection_service.revoke(s, request_id, provider)  # E18: 남은 칸 disconnected
            await s.commit()
        log.warning("apply_fix_store_not_visible", fix_plan_id=fix_plan_id)
    except TransientAutomationError:  # 가게 화면을 두 번 모두 열지 못함: 남은 칸은 수동으로
        failed += await _stop_all(
            fix_plan_id, provider, reason="write_failed", error_code="transient", **keys
        )
    # 같은 정비안의 저장 실패는 작업 끝에 한 번에 묶어 보낸다
    await _mail_manual(request_id, failed, f"manual_required:plan:{fix_plan_id}:write_failed")
    log.info("apply_fix_done", fix_plan_id=fix_plan_id, **counts)


# --- E32 반영 확인 -------------------------------------------------------------------------------


async def verify(fix_log_id: int, round_: int = 1, *, clients: Clients | None = None) -> None:
    """반영 대기 칸을 읽기만 해서 확인한다(쓰기 함수를 부르지 않음)."""
    from seelo.services import connection_service

    clients = clients or get_clients()
    async with session_scope() as s:
        lg = await s.get(FixLog, fix_log_id)
        conn = (
            await s.scalar(
                select(MapConnection).where(
                    MapConnection.fix_request_id == lg.fix_request_id, MapConnection.provider == lg.provider
                )
            )
            if lg
            else None
        )
        if lg is None or lg.status != FixLogStatus.PENDING_REFLECTION or conn is None:
            log.info("verify_fix_skip", fix_log_id=fix_log_id)
            return
        if conn.status != ConnectionStatus.CONNECTED:
            log.info("verify_fix_skip", fix_log_id=fix_log_id, connection=conn.status)
            return
        provider, field_, value = lg.provider, lg.field, lg.applied_value
        request_id, external_ref = lg.fix_request_id, conn.external_ref
        store_id = await s.scalar(select(FixRequest.store_id).where(FixRequest.id == request_id))
        ref = await connection_service.store_ref(s, store_id)
        await s.commit()
    try:
        async with clients.map_admin(provider) as admin:
            await admin.open_store(ref, external_ref)
            got = (await admin.read_fields([field_])).get(field_)
    except StoreNotVisible:
        async with session_scope() as s:
            await connection_service.revoke(s, request_id, provider)
            await s.commit()
        return
    except (AutomationBlocked, AttentionNeeded, TransientAutomationError) as e:
        log.warning("verify_fix_not_checked", fix_log_id=fix_log_id, error=type(e).__name__)
        return  # 상태 그대로, 다음 시각에 다시
    sp = spec(provider, field_)
    ok = (
        got is not None and not got.pending_review and same_value(sp.type if sp else "text", got.value, value)
    )
    now = now_utc()
    async with session_scope() as s:
        if ok:
            await transition(
                s,
                FixLog,
                fix_log_id,
                from_={FixLogStatus.PENDING_REFLECTION},
                to=FixLogStatus.APPLIED,
                values={"verified_at": now, "last_checked_at": now},
            )
            await defer_finalize(s, request_id, store_id=store_id)
        else:
            await s.execute(
                update(FixLog)
                .where(FixLog.id == fix_log_id, FixLog.status == FixLogStatus.PENDING_REFLECTION)
                .values(verify_count=FixLog.verify_count + 1, last_checked_at=now)
            )
        await s.commit()
    log.info("verify_fix", fix_log_id=fix_log_id, round=round_, reflected=ok)


async def recheck_pending(s: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """매시간: 24시간 지난 반영 대기 칸 → manual_required, 아니고 55분 넘게 확인 안 한 칸 → verifyFix."""
    from seelo.worker.tasks_fix import verify_fix

    now = now or now_utc()
    rows = (
        await s.execute(
            select(FixLog, FixRequest.store_id)
            .join(FixRequest, FixRequest.id == FixLog.fix_request_id)
            .where(FixLog.status == FixLogStatus.PENDING_REFLECTION)
            .order_by(FixLog.id)
            # 별도 확인 워커가 갱신한 verify_count/last_checked_at을 캐시 대신 다시 읽는다.
            .execution_options(populate_existing=True)
        )
    ).all()
    counts = {"expired": 0, "verify": 0}
    for lg, store_id in rows:
        if lg.applied_at is not None and now - lg.applied_at >= REFLECT_LIMIT:
            if await _to_manual(
                s, lg.id, from_={FixLogStatus.PENDING_REFLECTION}, reason="not_reflected_24h", error_code=None
            ):
                await email_service.queue(
                    s,
                    "manual_required",
                    params={
                        "request_id": lg.fix_request_id,
                        "items": [_manual_item(lg.provider, lg.field, "not_reflected_24h")],
                    },
                    dedupe_key=f"manual_required:log:{lg.id}",
                )
                await defer_finalize(s, lg.fix_request_id, store_id=store_id)
                counts["expired"] += 1
        elif lg.last_checked_at is None or now - lg.last_checked_at > RECHECK_AFTER:
            round_ = lg.verify_count + 1
            await jobs.defer(
                s,
                verify_fix,
                args={"fix_log_id": lg.id, "round": round_},
                links=jobs.JobLinks(store_id=store_id, fix_request_id=lg.fix_request_id),
                queueing_lock=f"verifyFix:{lg.id}:{round_}",
                lock=f"fix:{lg.provider}",
            )
            counts["verify"] += 1
    return counts


# --- E17 정비 완료 -------------------------------------------------------------------------------


async def finalize(fix_request_id: int) -> None:
    async with session_scope() as s:
        req = await s.get(FixRequest, fix_request_id, with_for_update=True)
        if req is None or req.status != FixRequestStatus.FIXING:
            log.info("finalize_fix_skip", fix_request_id=fix_request_id, reason="not_fixing")
            return
        plan_ids = list(
            await s.scalars(
                select(FixPlan.id).where(
                    FixPlan.fix_request_id == req.id, FixPlan.status == FixPlanStatus.APPROVED
                )
            )
        )
        if not plan_ids:
            log.info("finalize_fix_skip", fix_request_id=fix_request_id, reason="no_approved_plan")
            return
        # 제외한 칸은 기록이 없고, 칸이 0개인 정비안은 끝난 것으로 본다(09 11장 3번)
        logs = (
            await s.execute(
                select(FixLog.provider, FixLog.field, FixLog.status)
                .join(FixPlanItem, FixPlanItem.id == FixLog.fix_plan_item_id)
                .where(FixPlanItem.fix_plan_id.in_(plan_ids))
                .order_by(FixLog.provider, FixPlanItem.order_no)
            )
        ).all()
        left = sum(1 for lg in logs if lg.status not in DONE)
        if left:
            log.info("finalize_fix_skip", fix_request_id=fix_request_id, reason="open_items", left=left)
            return
        now = now_utc()
        await transition(
            s,
            FixRequest,
            req.id,
            from_={FixRequestStatus.FIXING},
            to=FixRequestStatus.REMEASURE_SCHEDULED,
            values={"fix_completed_at": now},
        )
        schedule = RemeasureSchedule(
            fix_request_id=req.id,
            due_at=now + REMEASURE_AFTER,
            triggered_by=TriggeredBy.SCHEDULER,
            status=ScheduleStatus.SCHEDULED,
        )
        s.add(schedule)
        await s.flush()
        await email_service.queue(
            s,
            "fix_completed",
            user=await s.get(User, req.user_id),
            params={
                # 지도+칸 라벨만(값 원문 금지, 16 2장)
                "changed_fields": [
                    f"{MAP_LABEL[lg.provider]} {field_label(lg.provider, lg.field)}"
                    for lg in logs
                    if lg.status in CHANGED
                ],
                "remeasure_date": kst_date(schedule.due_at).isoformat(),
            },
            dedupe_key=f"fix_completed:{schedule.id}",
        )
        schedule_id = schedule.id
        await s.commit()
    log.info("fix_completed", fix_request_id=fix_request_id, schedule_id=schedule_id, items=len(logs))


# --- E30 관리자 [처리 완료] ----------------------------------------------------------------------


async def manual_done(
    db: AsyncSession, admin: User, fix_log_id: int, body: ManualDoneRequest
) -> StatusResponse:
    lg = await db.scalar(
        select(FixLog)
        .where(FixLog.id == fix_log_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if lg is None:
        raise AppError("NOT_FOUND")
    if lg.status != FixLogStatus.MANUAL_REQUIRED:
        raise AppError("INVALID_STATE", {"currentStatus": lg.status})
    values = {"method": FixMethod.MANUAL, "handled_by": admin.id, "handled_at": now_utc()}
    # 자동으로 읽지 못해 before_value가 비었을 때만 관리자가 본 값을 받는다(04 8장)
    before_given = "before_value" in body.model_fields_set and lg.before_value is None
    if before_given:
        values["before_value"] = body.before_value
    await transition(
        db, FixLog, lg.id, from_={FixLogStatus.MANUAL_REQUIRED}, to=FixLogStatus.MANUAL_DONE, values=values
    )
    audit.record(
        db,
        actor_id=admin.id,
        action="fix_log.manual_done",
        target_type="fix_log",
        target_id=lg.id,
        detail={"provider": lg.provider, "field": lg.field, "beforeValueGiven": before_given},
    )
    request_id = lg.fix_request_id
    store_id = await db.scalar(select(FixRequest.store_id).where(FixRequest.id == request_id))
    await defer_finalize(db, request_id, store_id=store_id)
    await db.commit()
    log.info("fix_log_manual_done", fix_log_id=fix_log_id, fix_request_id=request_id)
    return StatusResponse(status=FixLogStatus.MANUAL_DONE)
