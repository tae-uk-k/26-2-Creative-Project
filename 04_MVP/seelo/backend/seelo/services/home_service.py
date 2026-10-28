"""홈 GET /api/home(04 5.1, 03 4장).

카드 판정은 domain/home_card.pick_card(순수 함수). 여기서는 입력을 모으고 카드별 data를 채운다.
- 입력: 보관 중이 아닌 가게, 그 가게의 가장 최근 신청, 그 신청의 지도별 최신 정비안, 연결, 수동 처리 칸.
- `unknown`이 나오면 오류 로그를 남기고 data 없는 카드로 응답한다.
"""

from typing import Any

import structlog
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.home_card import pick_card
from seelo.domain.states import RunKind, RunStatus
from seelo.integrations import Clients
from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import Store
from seelo.models.user import User
from seelo.schemas.home import HomeResponse
from seelo.services.diagnosis_service import findings_count, metric_rows, provider_rates
from seelo.services.eligibility import active_request, current_store
from seelo.services.store_service import RETRY_PER_DAY, retries_used_today, summary
from seelo.timeutil import kst_date

log = structlog.get_logger()

ACTIVE_RUN = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING)
PROVIDERS_MAP = ("google", "kakao")


async def _latest_run(db: AsyncSession, store_id: int, *, statuses: tuple[str, ...], **where: Any) -> Any:
    q = select(MeasurementRun).where(MeasurementRun.store_id == store_id, MeasurementRun.status.in_(statuses))
    for col, val in where.items():
        q = q.where(getattr(MeasurementRun, col) == val)
    return await db.scalar(q.order_by(MeasurementRun.id.desc()).limit(1))


async def _latest_plans(db: AsyncSession, request_id: int) -> list[FixPlan]:
    """지도별 최신 버전 정비안."""
    latest = (
        select(FixPlan.provider, func.max(FixPlan.version).label("v"))
        .where(FixPlan.fix_request_id == request_id)
        .group_by(FixPlan.provider)
        .subquery()
    )
    return list(
        (
            await db.scalars(
                select(FixPlan)
                .join(latest, (FixPlan.provider == latest.c.provider) & (FixPlan.version == latest.c.v))
                .where(FixPlan.fix_request_id == request_id)
            )
        ).all()
    )


def _progress(run: MeasurementRun | None, *, with_kind: bool) -> dict[str, Any]:
    if run is None:  # 무료 사용 뒤 바꾼 가게의 수집처럼 측정이 없는 경우
        base = {"runId": None, "stage": None, "progressDone": 0, "progressTotal": 0}
        return {**base, "kind": None, "waitingReason": None} if with_kind else base
    base = {
        "runId": run.id,
        "stage": run.stage,
        "progressDone": run.progress_done,
        "progressTotal": run.progress_total,
    }
    return {**base, "kind": run.kind, "waitingReason": run.waiting_reason} if with_kind else base


async def _data(
    db: AsyncSession,
    card: str,
    store: Store,
    req: FixRequest | None,
    plans: list[FixPlan],
    connections: list[MapConnection],
) -> dict[str, Any]:
    if card == "fix_requested" and req is not None:
        return {"requestId": req.id, "requestedAt": req.created_at}
    if card == "fix_rejected" and req is not None:
        return {"requestId": req.id, "rejectReason": req.reject_reason}
    if card == "measuring":
        run = await _latest_run(db, store.id, statuses=ACTIVE_RUN)
        return _progress(run, with_kind=True)
    if card == "measure_failed":
        run = await _latest_run(db, store.id, statuses=(RunStatus.FAILED,), kind=RunKind.DIAGNOSIS)
        return {"runId": run.id if run else None}
    if card == "diagnosed":
        run = await _latest_run(db, store.id, statuses=(RunStatus.COMPLETED,), kind=RunKind.DIAGNOSIS)
        if run is None:
            return {"runId": None, "providers": None, "findingsCount": 0}
        rates = provider_rates(await metric_rows(db, run.id))
        return {
            "runId": run.id,
            "providers": rates.model_dump(by_alias=True),
            "findingsCount": await findings_count(db, run.id),
        }
    if card == "plan_needs_approval":
        ids = [p.id for p in plans if p.status == "awaiting_approval"]
        items = await db.scalar(
            select(func.count()).select_from(FixPlanItem).where(FixPlanItem.fix_plan_id.in_(ids))
        )
        return {"planIds": sorted(ids), "itemCount": int(items or 0)}
    if card == "connect_needed":
        by = {c.provider: c.status for c in connections}
        return {"connections": {p: by.get(p, "not_connected") for p in PROVIDERS_MAP}}
    if card == "remeasure_waiting" and req is not None:
        sched = await db.scalar(
            select(RemeasureSchedule)
            .where(RemeasureSchedule.fix_request_id == req.id, RemeasureSchedule.status == "scheduled")
            .order_by(RemeasureSchedule.id.desc())
            .limit(1)
        )
        changed = await db.scalar(
            select(func.count())
            .select_from(FixLog)
            .where(FixLog.fix_request_id == req.id, FixLog.status.in_(("applied", "manual_done")))
        )
        return {
            "dueDate": kst_date(sched.due_at).isoformat() if sched else None,
            "changedCount": int(changed or 0),
        }
    if card == "remeasuring" and req is not None:
        run = await _latest_run(
            db, store.id, statuses=ACTIVE_RUN, kind=RunKind.REMEASURE, fix_request_id=req.id
        )
        return _progress(run, with_kind=False)
    if card == "remeasure_failed" and req is not None:
        return {"requestId": req.id}
    if card == "report_ready" and req is not None:
        return await _report_data(db, req)
    return {}


async def _report_data(db: AsyncSession, req: FixRequest) -> dict[str, Any]:
    """최신 완료 보고서와 전후 등장률(보고서 내용 대신 두 측정의 지표에서 바로 만든다)."""
    report = await db.scalar(
        select(ComparisonReport)
        .where(ComparisonReport.fix_request_id == req.id, ComparisonReport.status == "completed")
        .order_by(ComparisonReport.version.desc())
        .limit(1)
    )
    if report is None:
        return {"reportId": None, "providers": None}
    before = provider_rates(await metric_rows(db, report.base_run_id)) if report.base_run_id else None
    after = provider_rates(await metric_rows(db, report.after_run_id)) if report.after_run_id else None
    providers = {
        p: {
            "before": getattr(before, p).model_dump(by_alias=True) if before else None,
            "after": getattr(after, p).model_dump(by_alias=True) if after else None,
        }
        for p in ("openai", "gemini")
    }
    return {"reportId": report.id, "providers": providers}


async def home(db: AsyncSession, clients: Clients, user: User) -> HomeResponse:
    has_history = bool(
        await db.scalar(select(exists().where(Store.owner_id == user.id, Store.archived_at.is_not(None))))
    )
    store = await current_store(db, user.id)
    if store is None:
        return HomeResponse(
            card="no_store",
            store=None,
            store_change_blocked=False,
            revoked_providers=[],
            manual_in_progress=False,
            retries_left_today=RETRY_PER_DAY,
            has_history=has_history,
            data={},
        )
    req = await db.scalar(
        select(FixRequest).where(FixRequest.store_id == store.id).order_by(FixRequest.id.desc()).limit(1)
    )
    plans: list[FixPlan] = []
    connections: list[MapConnection] = []
    has_manual = False
    if req is not None:
        plans = await _latest_plans(db, req.id)
        connections = list(
            (await db.scalars(select(MapConnection).where(MapConnection.fix_request_id == req.id))).all()
        )
        has_manual = bool(
            await db.scalar(
                select(exists().where(FixLog.fix_request_id == req.id, FixLog.status == "manual_required"))
            )
        )
    card = pick_card(store, req, plans, connections, has_manual)
    if card == "unknown":
        log.error(
            "home_card_unknown",
            store_id=store.id,
            store_status=store.status,
            request_status=req.status if req else None,
            plan_statuses=sorted({p.status for p in plans}),
        )
    data = {} if card == "unknown" else await _data(db, card, store, req, plans, connections)
    blocked = await active_request(db, store.id) is not None
    retries_left = max(0, RETRY_PER_DAY - await retries_used_today(db, store.id))
    store_summary = await summary(db, clients, store)
    return HomeResponse(
        card=card,  # type: ignore[arg-type]
        store=store_summary,
        store_change_blocked=blocked,
        revoked_providers=sorted(c.provider for c in connections if c.status == "revoked"),  # type: ignore[misc]
        manual_in_progress=has_manual,
        retries_left_today=retries_left,
        has_history=has_history,
        data=data,
    )
