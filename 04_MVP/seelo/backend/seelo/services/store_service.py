"""현재 가게·지난 기록·가게 요약·[내 가게가 아니에요](04 5.2, 07 4.2, 03 E28)."""

import structlog
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.states import (
    FixRequestStatus,
    RunKind,
    RunStage,
    RunStatus,
    RunTrigger,
    StoreStatus,
    transition,
)
from seelo.errors import AppError
from seelo.integrations import Clients
from seelo.models.fix import FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import SourceSnapshot, Store, StoreSource
from seelo.models.user import User
from seelo.schemas.common import StoreSources, StoreSummary
from seelo.schemas.run import RunIdResponse
from seelo.schemas.store import CurrentStoreResponse, HistoryItem, HistoryResponse
from seelo.services import jobs
from seelo.services.eligibility import current_store, has_used_free
from seelo.services.refetch import refetch_kakao
from seelo.timeutil import kst_day_range

log = structlog.get_logger()

SOURCE_KEYS = ("google", "kakao", "naver", "website", "instagram")


async def refetch_kakao_address(clients: Clients, store: Store, kakao_id: str | None) -> str | None:
    """카카오 값은 저장하지 않으므로 그때 다시 불러온다(07 4.2). 못 찾거나 오류면 None."""
    place = await refetch_kakao(clients, kakao_id, [store.name])
    return place.address if place else None


async def summary(db: AsyncSession, clients: Clients, store: Store) -> StoreSummary:
    rows = (await db.execute(select(StoreSource).where(StoreSource.store_id == store.id))).scalars().all()
    marks = {r.provider: r.match_status for r in rows}
    address = await db.scalar(
        # 스냅샷 payload = {"ko": <상세 응답>, "en": ..., "photoCount": n}(07 6.2)
        select(SourceSnapshot.payload["ko"]["formattedAddress"].astext)
        .where(
            SourceSnapshot.store_id == store.id,
            SourceSnapshot.provider == "google",
            SourceSnapshot.status == "ok",
        )
        .order_by(SourceSnapshot.collected_at.desc())
        .limit(1)
    )
    if not address:
        kakao = next((r for r in rows if r.provider == "kakao" and r.match_status == "found"), None)
        address = await refetch_kakao_address(clients, store, kakao.external_id if kakao else None)
    return StoreSummary(
        id=store.id,
        name=store.name,
        address=address or None,
        category=store.category,  # type: ignore[arg-type]
        status=store.status,  # type: ignore[arg-type]
        sources=StoreSources(**{k: marks.get(k, "not_found") for k in SOURCE_KEYS}),
    )


async def current(db: AsyncSession, clients: Clients, user: User) -> CurrentStoreResponse:
    store = await current_store(db, user.id)
    return CurrentStoreResponse(store=await summary(db, clients, store) if store else None)


async def history(db: AsyncSession, user: User) -> HistoryResponse:
    last_diag = (
        select(func.max(MeasurementRun.id))
        .where(
            MeasurementRun.store_id == Store.id,
            MeasurementRun.kind == RunKind.DIAGNOSIS,
            MeasurementRun.status == RunStatus.COMPLETED,
        )
        .scalar_subquery()
    )
    last_report = (
        select(func.max(ComparisonReport.id))
        .where(ComparisonReport.store_id == Store.id, ComparisonReport.status == "completed")
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Store.id, Store.name, Store.archived_at, last_diag, last_report)
            .where(Store.owner_id == user.id, Store.archived_at.is_not(None))
            .order_by(Store.archived_at.desc())
        )
    ).all()
    return HistoryResponse(
        stores=[
            HistoryItem(store_id=r[0], name=r[1], archived_at=r[2], diagnosis_run_id=r[3], report_id=r[4])
            for r in rows
        ]
    )


async def not_mine(db: AsyncSession, user: User, run_id: int) -> None:
    """E28: 진단·trigger initial 측정이고, 가게에 completed 측정과 신청이 없을 때만. 측정 취소 → 가게 삭제."""
    run = await db.get(MeasurementRun, run_id)
    store = await db.get(Store, run.store_id) if run is not None else None
    if run is None or store is None or store.owner_id != user.id:
        raise AppError("NOT_FOUND")
    completed = await db.scalar(
        select(
            exists().where(MeasurementRun.store_id == store.id, MeasurementRun.status == RunStatus.COMPLETED)
        )
    )
    requested = await db.scalar(select(exists().where(FixRequest.store_id == store.id)))
    if (
        store.archived_at is not None
        or run.kind != RunKind.DIAGNOSIS
        or run.trigger != RunTrigger.INITIAL
        or completed
        or requested
    ):
        raise AppError("INVALID_STATE", {"currentStatus": store.status})
    store_id = store.id
    await jobs.cancel_jobs(db, store_ids=[store_id])
    if run.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING):
        await transition(
            db,
            MeasurementRun,
            run.id,
            from_={RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING},
            to=RunStatus.CANCELED,
        )
    await db.execute(delete(Store).where(Store.id == store_id))
    await db.commit()
    log.info("store_not_mine_deleted", store_id=store_id, run_id=run_id)


RETRY_PER_DAY = 3


async def retries_used_today(db: AsyncSession, store_id: int) -> int:
    """오늘(KST) 이 가게의 trigger retry 측정 수(03 7장, 진단·재측정 합산)."""
    start, end = kst_day_range()
    return int(
        await db.scalar(
            select(func.count())
            .select_from(MeasurementRun)
            .where(
                MeasurementRun.store_id == store_id,
                MeasurementRun.trigger == RunTrigger.RETRY,
                MeasurementRun.created_at >= start,
                MeasurementRun.created_at < end,
            )
        )
        or 0
    )


async def retry_measurement(db: AsyncSession, user: User) -> RunIdResponse:
    """E25: 측정 실패한 가게를 다시 측정한다. 하루 3번(KST).

    실패는 무료를 차감하지 않으므로 무료 여부를 다시 본다.
    """
    store = await current_store(db, user.id, for_update=True)
    if store is None or store.status != StoreStatus.MEASURE_FAILED:
        raise AppError("INVALID_STATE", {"currentStatus": store.status if store else "no_store"})
    if await retries_used_today(db, store.id) >= RETRY_PER_DAY:
        raise AppError("RETRY_LIMIT")
    requests = (await db.scalars(select(FixRequest).where(FixRequest.store_id == store.id))).all()
    approved = next((r for r in requests if r.status == FixRequestStatus.APPROVED), None)
    is_free = not requests and not await has_used_free(db, user.email)
    run = MeasurementRun(
        store_id=store.id,
        kind=RunKind.DIAGNOSIS,
        is_free=is_free,
        trigger=RunTrigger.RETRY,
        status=RunStatus.QUEUED,
        stage=RunStage.COLLECTING,
        fix_request_id=approved.id if approved else None,
    )
    db.add(run)
    await db.flush()
    await transition(db, Store, store.id, from_={StoreStatus.MEASURE_FAILED}, to=StoreStatus.COLLECTING)
    from seelo.worker.tasks_collect import collect_store

    await jobs.defer(
        db,
        collect_store,
        args={"store_id": store.id, "run_id": run.id},
        links=jobs.JobLinks(store_id=store.id, run_id=run.id),
        queueing_lock=f"collect:{store.id}:{run.id}",
        lock=f"store:{store.id}",
    )
    run_id = run.id
    await db.commit()
    return RunIdResponse(run_id=run_id)
