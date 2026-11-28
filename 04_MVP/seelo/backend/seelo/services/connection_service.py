"""지도 연결(09 2·5·12장, 04 7.2·8장, 03 E11·E12·E18·E31, W-09-1).

- S15: 사장님이 seelo 계정을 지도 관리자로 초대하고 [초대했어요](E11)를 누른다.
- 연결 확인(E12): `AUTO_FIX_ENABLED=false`(기본)면 **수동 확인 모드**만 — 관리자가 관리 화면에서 직접 확인한
  결과를 API로 보내고 API 안에서 바로 처리한다.
  켜져 있으면 verifyConnection 작업이 관리 화면(MapAdmin)을 연다.
- 연결 성공: 신청이 connecting·fixing·remeasure_scheduled이고 그 지도에 approved·awaiting_approval·generating
  정비안이 없고 기준 측정이 있으면 새 정비안(generating) + readCurrentValues(본문은 11단계).
- 차단(AutomationBlocked)이면 연결 상태를 바꾸지 않고 감사 기록(blocked)·관리자 메일 manual_required.
- 권한 회수(E18): 감지는 11~13단계(읽기·쓰기·반영 확인)에서 revoke()를 부른다.
"""

from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.states import (
    ConnectionStatus,
    FixLogStatus,
    FixPlanStatus,
    FixRequestStatus,
    MatchStatus,
    transition,
)
from seelo.errors import AppError
from seelo.integrations import Clients, get_clients
from seelo.integrations.browser import StoreRef
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.models.fix import FixLog, FixPlan, FixRequest, MapConnection
from seelo.models.store import Store, StoreSource
from seelo.models.user import User
from seelo.schemas.admin import StatusResponse, VerifyConnectionRequest
from seelo.schemas.fix import ConnectionView, ConnectState, SeeloAccounts
from seelo.services import audit, email_service, fix_apply_service, jobs
from seelo.services.eligibility import current_store
from seelo.timeutil import now_utc

log = structlog.get_logger()

# S15를 볼 수 있는 신청 상태(04 7.2: approved~report_ready, remeasure_failed 포함)
VIEWABLE = {
    FixRequestStatus.APPROVED,
    FixRequestStatus.CONNECTING,
    FixRequestStatus.FIXING,
    FixRequestStatus.REMEASURE_SCHEDULED,
    FixRequestStatus.REMEASURING,
    FixRequestStatus.REMEASURE_FAILED,
    FixRequestStatus.REPORT_READY,
}
IN_PROGRESS = VIEWABLE - {FixRequestStatus.REPORT_READY}  # 초대·연결 확인을 받는 상태
INVITABLE = {ConnectionStatus.NOT_CONNECTED, ConnectionStatus.NEEDS_ATTENTION, ConnectionStatus.REVOKED}
VERIFIABLE = {ConnectionStatus.NOT_CONNECTED, ConnectionStatus.INVITED, ConnectionStatus.NEEDS_ATTENTION}
PLAN_STAGE = {FixRequestStatus.CONNECTING, FixRequestStatus.FIXING, FixRequestStatus.REMEASURE_SCHEDULED}
LIVE_PLAN = {FixPlanStatus.APPROVED, FixPlanStatus.AWAITING_APPROVAL, FixPlanStatus.GENERATING}
INVITE_REMINDER_AFTER = timedelta(days=3)
VERIFY_ATTEMPTS = 2  # 일시 오류 1번 다시(06 4장)


def _view(conn: MapConnection, store_found: bool) -> ConnectionView:
    return ConnectionView(
        provider=conn.provider,  # type: ignore[arg-type]
        status=conn.status,  # type: ignore[arg-type]
        attention_reason=conn.attention_reason,
        invited_at=conn.invited_at,
        invite_not_arrived=conn.status == ConnectionStatus.INVITED
        and conn.invite_reminder_sent_at is not None,
        store_found_on_map=store_found,
        can_invite=conn.status in INVITABLE,
    )


async def _request_for(db: AsyncSession, user: User, statuses: set[str]) -> tuple[Store, FixRequest]:
    store = await current_store(db, user.id)
    req = (
        await db.scalar(
            select(FixRequest).where(FixRequest.store_id == store.id).order_by(FixRequest.id.desc()).limit(1)
        )
        if store
        else None
    )
    if store is None or req is None or req.status not in statuses:
        raise AppError("NOT_FOUND")
    return store, req


async def _found(db: AsyncSession, store_id: int) -> dict[str, bool]:
    rows = await db.scalars(select(StoreSource).where(StoreSource.store_id == store_id))
    return {r.provider: r.match_status == MatchStatus.FOUND for r in rows}


# --- S15 ----------------------------------------------------------------------------------


async def state(db: AsyncSession, user: User) -> ConnectState:
    store, req = await _request_for(db, user, VIEWABLE)
    found = await _found(db, store.id)
    conns = {
        c.provider: c
        for c in await db.scalars(select(MapConnection).where(MapConnection.fix_request_id == req.id))
    }
    s = get_settings()
    return ConnectState(
        request_id=req.id,
        seelo_accounts=SeeloAccounts(google=s.seelo_google_account_email, kakao=s.seelo_kakao_account_id),
        google=_view(conns["google"], found.get("google", False)),
        kakao=_view(conns["kakao"], found.get("kakao", False)),
    )


async def mark_invited(db: AsyncSession, user: User, provider: str) -> ConnectionView:
    """E11. 이미 invited면 아무것도 바꾸지 않는다(200). connected 등은 409."""
    store, req = await _request_for(db, user, VIEWABLE)
    if req.status not in IN_PROGRESS:
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    conn = await db.scalar(
        select(MapConnection)
        .where(MapConnection.fix_request_id == req.id, MapConnection.provider == provider)
        .with_for_update()
    )
    if conn.status != ConnectionStatus.INVITED:
        moved = await transition(
            db,
            MapConnection,
            conn.id,
            from_=INVITABLE,
            to=ConnectionStatus.INVITED,
            values={"invited_at": now_utc(), "invite_reminder_sent_at": None, "attention_reason": None},
        )
        if not moved:
            raise AppError("INVALID_STATE", {"currentStatus": conn.status})
        await db.commit()
        await db.refresh(conn)
    found = (await _found(db, store.id)).get(provider, False)
    return _view(conn, found)


# --- E12 연결 확인 -------------------------------------------------------------------------


async def maybe_create_plan(s: AsyncSession, req: FixRequest, provider: str) -> int | None:
    """연결된 지도의 정비안 만들기 단계(E12). 만들었으면 정비안 id. 커밋은 부르는 쪽."""
    if req.status not in PLAN_STAGE or req.base_run_id is None:
        return None
    plans = (
        await s.scalars(select(FixPlan).where(FixPlan.fix_request_id == req.id, FixPlan.provider == provider))
    ).all()
    if any(p.status in LIVE_PLAN for p in plans):
        return None  # 정비는 신청 1건당 지도마다 한 번(다시 연결해도 새로 만들지 않음, 09 12장)
    version = (max((p.version for p in plans), default=0)) + 1
    plan = FixPlan(
        fix_request_id=req.id,
        provider=provider,
        base_run_id=req.base_run_id,
        version=version,
        status=FixPlanStatus.GENERATING,
    )
    s.add(plan)
    await s.flush()
    from seelo.services.fix_plan_service import defer_read

    await defer_read(s, plan.id, provider, store_id=req.store_id, request_id=req.id)
    log.info("fix_plan_created", request_id=req.id, provider=provider, plan_id=plan.id, version=version)
    return plan.id


async def plans_for_connected(s: AsyncSession, req: FixRequest) -> list[int]:
    """E4에서 신청이 connecting이 됐을 때: 이미 연결된 지도마다 정비안 만들기 단계."""
    conns = (
        await s.scalars(
            select(MapConnection).where(
                MapConnection.fix_request_id == req.id, MapConnection.status == ConnectionStatus.CONNECTED
            )
        )
    ).all()
    made = [await maybe_create_plan(s, req, c.provider) for c in conns]
    return [p for p in made if p is not None]


async def _apply_result(
    s: AsyncSession,
    conn: MapConnection,
    req: FixRequest,
    *,
    result: str,
    attention_reason: str | None,
    external_ref: str | None,
    actor_id: int | None,
    mode: str,
) -> str:
    """E12 결과 반영(연결 행은 잠근 상태). 바뀐 상태를 돌려준다."""
    conn_id, provider = conn.id, conn.provider
    if result == "connected":
        connected_at = now_utc()
        moved = await transition(
            s,
            MapConnection,
            conn_id,
            from_=VERIFIABLE,
            to=ConnectionStatus.CONNECTED,
            values={
                "connected_at": connected_at,
                "confirmed_by": actor_id,
                "external_ref": external_ref,
                "attention_reason": None,
            },
        )
        if not moved:
            raise AppError("INVALID_STATE", {"currentStatus": conn.status})
        await maybe_create_plan(s, req, provider)
        owner = await s.get(User, req.user_id)
        await email_service.queue(
            s,
            "map_connection",
            user=owner,
            params={"kind": "connected", "provider": provider},
            dedupe_key=f"map_connection:{conn_id}:connected:{connected_at.isoformat()}",
        )
        status = ConnectionStatus.CONNECTED
    else:
        moved = await transition(
            s,
            MapConnection,
            conn_id,
            from_=VERIFIABLE,
            to=ConnectionStatus.NEEDS_ATTENTION,
            values={"attention_reason": attention_reason},
        )
        if not moved:
            raise AppError("INVALID_STATE", {"currentStatus": conn.status})
        status = ConnectionStatus.NEEDS_ATTENTION
    audit.record(
        s,
        actor_id=actor_id,
        action="connection.verify",
        target_type="map_connection",
        target_id=conn_id,
        detail={"result": str(status), "attentionReason": attention_reason, "mode": mode},
    )
    log.info("connection_verified", connection_id=conn_id, provider=provider, result=str(status), mode=mode)
    return status


async def store_ref(s: AsyncSession, store_id: int) -> StoreRef:
    """관리 화면에서 가게를 찾을 단서(이름·장소 id). 카카오 값은 장소 id만 넘긴다."""
    store = await s.get(Store, store_id)
    src = {
        r.provider: r for r in await s.scalars(select(StoreSource).where(StoreSource.store_id == store_id))
    }
    return StoreRef(
        store_id=store_id,
        name=store.name,
        address=None,
        google_place_id=getattr(src.get("google"), "external_id", None),
        kakao_place_id=getattr(src.get("kakao"), "external_id", None),
    )


async def _locked(s: AsyncSession, connection_id: int) -> tuple[MapConnection, FixRequest]:
    conn = await s.get(MapConnection, connection_id, with_for_update=True)
    if conn is None:
        raise AppError("NOT_FOUND")
    req = await s.get(FixRequest, conn.fix_request_id, with_for_update=True)
    if req.status not in IN_PROGRESS:
        raise AppError("INVALID_STATE", {"currentStatus": req.status})
    if conn.status not in VERIFIABLE:
        raise AppError("INVALID_STATE", {"currentStatus": conn.status})
    return conn, req


async def admin_verify(
    db: AsyncSession, admin: User, connection_id: int, body: VerifyConnectionRequest
) -> tuple[int, dict[str, Any]]:
    """(HTTP 상태, 본문). manualResult가 있으면 바로 처리(200 {status}), 없으면 작업 등록(202 {})."""
    conn, req = await _locked(db, connection_id)
    if body.manual_result is not None:
        if body.manual_result == "needs_attention" and body.attention_reason is None:
            raise AppError("VALIDATION_ERROR", {"fields": {"attentionReason": "required"}})
        status = await _apply_result(
            db,
            conn,
            req,
            result=body.manual_result,
            attention_reason=body.attention_reason if body.manual_result == "needs_attention" else None,
            external_ref=body.external_ref,
            actor_id=admin.id,
            mode="manual",
        )
        await db.commit()
        return 200, StatusResponse(status=status).model_dump()
    if not get_settings().auto_fix_enabled:  # 자동 확인이 꺼져 있으면 수동 결과가 필요하다
        raise AppError("VALIDATION_ERROR", {"fields": {"manualResult": "required"}})
    from seelo.worker.tasks_fix import verify_connection

    await jobs.defer(
        db,
        verify_connection,
        args={"connection_id": connection_id, "requested_by": admin.id},
        links=jobs.JobLinks(store_id=req.store_id, fix_request_id=req.id),
        queueing_lock=f"verifyConn:{connection_id}",
        lock=f"fix:{conn.provider}",
    )
    await db.commit()
    return 202, {}


async def verify(
    connection_id: int, requested_by: int | None = None, *, clients: Clients | None = None
) -> None:
    """verifyConnection 작업(AUTO_FIX_ENABLED=true). 관리 화면에서 가게를 연다(09 5장 2번)."""
    clients = clients or get_clients()
    if not get_settings().auto_fix_enabled:
        log.warning("verify_connection_disabled", connection_id=connection_id)
        return
    async with session_scope() as s:
        try:
            conn, req = await _locked(s, connection_id)
        except AppError as e:
            log.info("verify_connection_skip", connection_id=connection_id, code=e.code)
            return
        ref = await store_ref(s, req.store_id)
        provider, external_ref, request_id = conn.provider, conn.external_ref, req.id
        await s.commit()  # 화면을 여는 동안 트랜잭션을 열어 두지 않는다

    result, reason, new_ref = "connected", None, None
    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        try:
            async with clients.map_admin(provider) as admin:
                new_ref = await admin.open_store(ref, external_ref)
            break
        except StoreNotVisible:
            result, reason = "needs_attention", "store_not_visible"
            break
        except AttentionNeeded as e:
            result, reason = "needs_attention", e.reason
            break
        except AutomationBlocked as e:
            await _blocked(connection_id, request_id, provider, requested_by, e.reason)
            return
        except TransientAutomationError:
            if attempt == VERIFY_ATTEMPTS:  # 두 번 모두 일시 오류: 상태는 그대로, 관리자가 다시 확인
                log.error("verify_connection_transient", connection_id=connection_id)
                return
    async with session_scope() as s:
        try:
            conn, req = await _locked(s, connection_id)
        except AppError:
            return  # 그 사이 상태가 바뀜(관리자 수동 처리 등)
        await _apply_result(
            s,
            conn,
            req,
            result=result,
            attention_reason=reason,
            external_ref=new_ref,
            actor_id=requested_by,
            mode="auto",
        )
        await s.commit()


async def _blocked(
    connection_id: int, request_id: int, provider: str, actor_id: int | None, reason: str
) -> None:
    """연결 상태는 그대로. 같은 초대의 차단 메일은 한 통(10 4장)."""
    async with session_scope() as s:
        try:
            conn, _ = await _locked(s, connection_id)
        except AppError:
            return
        event_at = conn.invited_at or conn.created_at
        audit.record(
            s,
            actor_id=actor_id,
            action="connection.verify",
            target_type="map_connection",
            target_id=connection_id,
            detail={"result": "blocked", "reason": reason, "mode": "auto"},
        )
        await email_service.queue(
            s,
            "manual_required",
            params={
                "request_id": request_id,
                "items": [{"provider": provider, "field_label": "연결 확인", "reason": "automation_blocked"}],
            },
            dedupe_key=f"manual_required:verify:{connection_id}:{event_at.isoformat()}",
        )
        await s.commit()
    log.warning("verify_connection_blocked", connection_id=connection_id, reason=reason)


# --- E31 초대 미도착 --------------------------------------------------------------------------


async def check_pending_invites(s: AsyncSession, now: Any = None) -> int:
    """invited 3일 지나고 아직 안내하지 않은 연결에 메일 1번(두 번 돌려도 1통). 커밋은 부르는 쪽."""
    now = now or now_utc()
    conns = (
        await s.scalars(
            select(MapConnection)
            .where(
                MapConnection.status == ConnectionStatus.INVITED,
                MapConnection.invited_at < now - INVITE_REMINDER_AFTER,
                MapConnection.invite_reminder_sent_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for c in conns:
        c.invite_reminder_sent_at = now
        owner_id = await s.scalar(select(FixRequest.user_id).where(FixRequest.id == c.fix_request_id))
        await email_service.queue(
            s,
            "map_connection",
            user=await s.get(User, owner_id),
            params={"kind": "reminder", "provider": c.provider},
            dedupe_key=f"map_connection:{c.id}:reminder:{c.invited_at.isoformat()}",
        )
    return len(conns)


# --- E18 권한 회수 ---------------------------------------------------------------------------


async def revoke(s: AsyncSession, request_id: int, provider: str) -> bool:
    """연결 → revoked, 그 지도의 남은 칸(queued·pending_reflection·manual_required) → disconnected,
    finalizeFix 등록. 이미 revoked 등이면 False. 커밋은 부르는 쪽(감지한 작업)."""
    conn_id = await s.scalar(
        select(MapConnection.id).where(
            MapConnection.fix_request_id == request_id, MapConnection.provider == provider
        )
    )
    if conn_id is None:
        return False
    moved = await transition(
        s,
        MapConnection,
        conn_id,
        from_={ConnectionStatus.CONNECTED},
        to=ConnectionStatus.REVOKED,
        values={"revoked_at": now_utc()},
    )
    if not moved:
        return False
    left = await s.execute(
        update(FixLog)
        .where(
            FixLog.fix_request_id == request_id,
            FixLog.provider == provider,
            FixLog.status.in_(
                [FixLogStatus.QUEUED, FixLogStatus.PENDING_REFLECTION, FixLogStatus.MANUAL_REQUIRED]
            ),
        )
        .values(status=FixLogStatus.DISCONNECTED)
    )
    store_id = await s.scalar(select(FixRequest.store_id).where(FixRequest.id == request_id))
    await fix_apply_service.defer_finalize(s, request_id, store_id=store_id)
    log.warning("connection_revoked", request_id=request_id, provider=provider, disconnected=left.rowcount)
    return True
