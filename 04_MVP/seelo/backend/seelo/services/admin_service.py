"""관리자 정비 신청 목록·상세(04 8장, 03 5장, A01).

- 목록의 대표 상태·필터는 domain/admin_filter. 베타 규모라 신청을 모두 읽어 메모리에서 거르고 나눈다
  (최신 신청 먼저).
- 관리자에게는 측정의 실패율·비용을 보인다. 사장님 화면에는 보이지 않는다.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.admin_filter import RequestFacts, display_status, matching
from seelo.domain.field_dictionary import field_label
from seelo.domain.states import RunKind
from seelo.errors import AppError
from seelo.models.fix import FixLog, FixPlan, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import Store, StoreSource
from seelo.models.user import User
from seelo.schemas.admin import (
    AdminConnection,
    AdminListItem,
    AdminOwner,
    AdminPlan,
    AdminReport,
    AdminRequestDetail,
    AdminRequestInfo,
    AdminRun,
    AdminRunRef,
    AdminSchedule,
    AdminStore,
    ManualItem,
)
from seelo.schemas.common import Page, StoreSources

# 관리 화면 주소 [PoC: 프로필·매장 화면 경로]. 정해지기 전에는 각 서비스 첫 화면(04 8장)
ADMIN_URL = {"google": "https://business.google.com/", "kakao": "https://business.kakao.com/"}
SOURCE_KEYS = ("google", "kakao", "naver", "website", "instagram")


def _latest_by(rows: list[Any], key: Any) -> dict[Any, Any]:
    """key별 version이 가장 큰 행."""
    out: dict[Any, Any] = {}
    for r in rows:
        k = key(r)
        if k not in out or r.version > out[k].version:
            out[k] = r
    return out


async def _facts(
    db: AsyncSession, request_ids: list[int], statuses: dict[int, str]
) -> dict[int, RequestFacts]:
    plans = list((await db.scalars(select(FixPlan).where(FixPlan.fix_request_id.in_(request_ids)))).all())
    latest_plans = _latest_by(plans, lambda p: (p.fix_request_id, p.provider))
    reports = list(
        (
            await db.scalars(select(ComparisonReport).where(ComparisonReport.fix_request_id.in_(request_ids)))
        ).all()
    )
    latest_reports = _latest_by(reports, lambda r: r.fix_request_id)
    manual = set(
        (
            await db.scalars(
                select(FixLog.fix_request_id).where(
                    FixLog.fix_request_id.in_(request_ids), FixLog.status == "manual_required"
                )
            )
        ).all()
    )
    facts = {rid: RequestFacts(status=statuses[rid]) for rid in request_ids}
    for (rid, _), p in latest_plans.items():
        facts[rid].plan_statuses.add(p.status)
    for rid, r in latest_reports.items():
        facts[rid].latest_report_failed = r.status == "generation_failed"
    for rid in manual:
        facts[rid].has_manual = True
    return facts


async def _diagnosis_status(db: AsyncSession, store_ids: list[int]) -> dict[int, str]:
    rows = (
        await db.execute(
            select(MeasurementRun.store_id, MeasurementRun.status)
            .where(MeasurementRun.store_id.in_(store_ids), MeasurementRun.kind == RunKind.DIAGNOSIS)
            .order_by(MeasurementRun.id.desc())
        )
    ).all()
    out: dict[int, str] = {}
    for store_id, status in rows:
        out.setdefault(store_id, status)
    return out


async def list_requests(
    db: AsyncSession, filter_: str | None, page: int, page_size: int
) -> Page[AdminListItem]:
    rows = (
        await db.execute(
            select(FixRequest, Store.name, User.email)
            .join(Store, Store.id == FixRequest.store_id)
            .join(User, User.id == FixRequest.user_id)
            .order_by(FixRequest.created_at.desc(), FixRequest.id.desc())
        )
    ).all()
    ids = [r[0].id for r in rows]
    facts = await _facts(db, ids, {r[0].id: r[0].status for r in rows})
    diag = await _diagnosis_status(db, list({r[0].store_id for r in rows}))
    items = [
        AdminListItem(
            id=req.id,
            created_at=req.created_at,
            owner_email=email,
            store_name=name,
            diagnosis_status=diag.get(req.store_id),
            status=req.status,
            display_status=display_status(facts[req.id]),  # type: ignore[arg-type]
        )
        for req, name, email in rows
        if filter_ is None or filter_ in matching(facts[req.id])
    ]
    start = (page - 1) * page_size
    return Page[AdminListItem](
        items=items[start : start + page_size], page=page, page_size=page_size, total=len(items)
    )


async def manual_items(db: AsyncSession, request_id: int | None = None) -> list[ManualItem]:
    """manual_required 칸(관리자가 직접 고칠 칸). request_id가 있으면 그 신청만."""
    q = (
        select(FixLog, Store.name)
        .join(FixRequest, FixRequest.id == FixLog.fix_request_id)
        .join(Store, Store.id == FixRequest.store_id)
        .where(FixLog.status == "manual_required")
        .order_by(FixLog.created_at, FixLog.id)
    )
    if request_id is not None:
        q = q.where(FixLog.fix_request_id == request_id)
    return [
        ManualItem(
            fix_log_id=log_.id,
            fix_request_id=log_.fix_request_id,
            store_name=store_name,
            provider=log_.provider,  # type: ignore[arg-type]
            field=log_.field,
            field_label=field_label(log_.provider, log_.field),
            approved_value=log_.applied_value,
            manual_reason=log_.manual_reason,
            admin_url=ADMIN_URL.get(log_.provider, ""),
            created_at=log_.created_at,
        )
        for log_, store_name in (await db.execute(q)).all()
    ]


async def detail(db: AsyncSession, request_id: int) -> AdminRequestDetail:
    req = await db.get(FixRequest, request_id)
    if req is None:
        raise AppError("NOT_FOUND")
    store = await db.get(Store, req.store_id)
    owner = await db.get(User, req.user_id)
    facts = (await _facts(db, [req.id], {req.id: req.status}))[req.id]
    marks = {
        s.provider: s.match_status
        for s in await db.scalars(select(StoreSource).where(StoreSource.store_id == store.id))
    }
    runs = (
        await db.scalars(
            select(MeasurementRun)
            .where(MeasurementRun.store_id == store.id)
            .order_by(MeasurementRun.id.desc())
        )
    ).all()
    base = next((r for r in runs if r.id == req.base_run_id), None)
    connections = (
        await db.scalars(
            select(MapConnection)
            .where(MapConnection.fix_request_id == req.id)
            .order_by(MapConnection.provider)
        )
    ).all()
    plans = (
        await db.scalars(
            select(FixPlan)
            .where(FixPlan.fix_request_id == req.id)
            .order_by(FixPlan.provider, FixPlan.version)
        )
    ).all()
    sched = await db.scalar(
        select(RemeasureSchedule)
        .where(RemeasureSchedule.fix_request_id == req.id)
        .order_by(RemeasureSchedule.id.desc())
        .limit(1)
    )
    reports = (
        await db.scalars(
            select(ComparisonReport)
            .where(ComparisonReport.fix_request_id == req.id)
            .order_by(ComparisonReport.version)
        )
    ).all()
    return AdminRequestDetail(
        request=AdminRequestInfo(
            id=req.id,
            status=req.status,
            display_status=display_status(facts),  # type: ignore[arg-type]
            created_at=req.created_at,
            reject_reason=req.reject_reason,
            decided_at=req.decided_at,
            fix_completed_at=req.fix_completed_at,
        ),
        owner=AdminOwner(user_id=owner.id, email=owner.email),
        store=AdminStore(
            id=store.id,
            name=store.name,
            status=store.status,
            sources=StoreSources(**{k: marks.get(k, "not_found") for k in SOURCE_KEYS}),
        ),
        base_run=AdminRunRef(id=base.id, status=base.status) if base else None,
        runs=[
            AdminRun(
                id=r.id,
                kind=r.kind,
                status=r.status,
                trigger=r.trigger,
                created_at=r.created_at,
                completed_at=r.completed_at,
                failure_rate=float(r.failure_rate) if r.failure_rate is not None else None,
                cost_usd=float(r.cost_usd),
            )
            for r in runs
        ],
        connections=[AdminConnection.model_validate(c) for c in connections],
        plans=[AdminPlan.model_validate(p) for p in plans],
        manual_items=await manual_items(db, req.id),
        schedule=AdminSchedule.model_validate(sched) if sched else None,
        reports=[AdminReport.model_validate(r) for r in reports],
    )
