"""쇼핑몰 브라우저·AI 작업 등록과 실행.

- 브라우저 작업은 Playwright·프로필 볼륨이 있는 worker-fix의 commerce_browser 큐에서 실행한다.
- 같은 몰 프로필은 Procrastinate lock으로 한 번에 하나만 연다. 같은 상품·정비안 작업은 중복 등록하지 않는다.
- 작업은 자동 재시도하지 않는다. 저장 결과가 불명확하면 정비안을 uncertain으로 두고 재조회 작업만 받는다.
- 중단 의심 작업은 실패로 정리하고 새 작업을 받는다. 저장 작업은 다시 보내지 않고 재조회로 판정한다.
"""

import asyncio
import shutil
from datetime import timedelta
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.errors import AppError
from seelo.models.commerce import CommerceJob, CommerceShop
from seelo.models.user import User
from seelo.services import jobs
from seelo.timeutil import now_utc

log = structlog.get_logger()

BROWSER_KINDS = {"collect", "apply", "rollback", "verify", "catalog", "forget_session"}
AI_KINDS = {"prepare", "measure"}
ACTIVE = ("queued", "running")
# 사람이 브라우저에서 해결해야 하는 상태. 해결 전까지 같은 몰의 다른 작업도 실패한다.
SESSION_PROBLEMS = {"login_required", "captcha", "security_check"}


def worker_mode() -> bool:
    return get_settings().commerce_browser_runner == "worker"


def profile_key(shop: CommerceShop) -> str:
    return f"{shop.platform}:{shop.external_id}:{shop.shop_no}"


def profile_path(shop: CommerceShop) -> Path:
    # BrowserProduct와 같은 몰별 경로. 플랫폼·몰 ID는 등록 때 고정 패턴으로 검사한 값이다.
    root = Path(get_settings().commerce_browser_profile_root)
    return root / shop.platform / shop.external_id / str(shop.shop_no)


def forget_profile(target: Path) -> bool:
    """몰별 전용 프로필(로그인 세션 포함)을 지운다. 프로필 루트 밖 경로는 지우지 않는다."""
    root = Path(get_settings().commerce_browser_profile_root).resolve()
    if not target.resolve().is_relative_to(root) or not target.exists():
        return False
    shutil.rmtree(target)
    return True


def is_stale(job: CommerceJob) -> bool:
    limit = timedelta(minutes=get_settings().commerce_job_stale_minutes)
    started = job.started_at if job.status == "running" else job.created_at
    return job.status in ACTIVE and started is not None and started < now_utc() - limit


def job_view(job: CommerceJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "shopId": job.shop_id,
        "productId": job.product_id,
        "planId": job.plan_id,
        "kind": job.kind,
        "status": job.status,
        "errorCode": job.error_code,
        "result": job.result,
        "stale": is_stale(job),
        "createdAt": job.created_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
    }


async def latest_for_plan(db: AsyncSession, plan_id: int) -> CommerceJob | None:
    return await db.scalar(
        select(CommerceJob).where(CommerceJob.plan_id == plan_id).order_by(CommerceJob.id.desc()).limit(1)
    )


async def enqueue(
    db: AsyncSession,
    user: User,
    shop: CommerceShop,
    kind: str,
    *,
    dedupe: str,
    product_id: int | None = None,
    plan_id: int | None = None,
    payload: dict | None = None,
) -> CommerceJob:
    """작업 행과 큐 등록을 같은 트랜잭션으로 커밋한다."""
    from seelo.services.commerce_service import event
    from seelo.worker.tasks_commerce import (
        commerce_ai_job,
        commerce_browser_job,
        commerce_measure_gemini,
        commerce_measure_openai,
    )

    existing = await db.scalar(
        select(CommerceJob)
        .where(
            CommerceJob.shop_id == shop.id,
            CommerceJob.dedupe_key == dedupe,
            CommerceJob.status.in_(ACTIVE),
        )
        .with_for_update()
    )
    if existing is not None:
        if not is_stale(existing):
            raise AppError("INVALID_STATE", {"reason": "job_in_progress", "jobId": existing.id})
        existing.status, existing.error_code, existing.finished_at = "failed", "stalled", now_utc()
        await db.flush()
    job = CommerceJob(
        shop_id=shop.id,
        product_id=product_id,
        plan_id=plan_id,
        kind=kind,
        dedupe_key=dedupe,
        input=payload or {},
        result={},
        requested_by=user.id,
    )
    try:
        # 동시에 같은 작업을 등록하면 부분 고유 인덱스가 막는다. SAVEPOINT만 되돌려 요청 세션을 보존한다.
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError as error:
        raise AppError("INVALID_STATE", {"reason": "job_in_progress"}) from error
    browser = kind in BROWSER_KINDS
    if kind == "measure":
        # 측정은 공급자별 AI 큐에서 돈다. 기존 측정 워커의 동시 실행 한도를 그대로 쓴다.
        task = commerce_measure_openai if job.input.get("provider") == "openai" else commerce_measure_gemini
        lock = f"commerce-measure:{job.input.get('runId')}"
    else:
        task = commerce_browser_job if browser else commerce_ai_job
        # 같은 몰 프로필은 동시에 열지 않는다. AI 준비는 같은 상품 안에서만 직렬화한다.
        lock = ("commerce-browser:" + profile_key(shop)) if browser else f"commerce-ai:{product_id}"
    job.queue_job_id = await jobs.defer(db, task, args={"job_id": job.id}, links=jobs.JobLinks(), lock=lock)
    event(db, user, "job", shop.id, jobId=job.id, kind=kind)
    await db.commit()
    return job


async def _execute(db: AsyncSession, job: CommerceJob, user: User) -> dict:
    from seelo.services import commerce_service as service

    if job.kind == "collect":
        view = await service.collect(db, user, job.shop_id, job.input["productNo"])
        return {"productId": view["id"], "snapshotHash": view["snapshotHash"]}
    if job.kind in {"apply", "rollback"}:
        from seelo.models.commerce import CommerceWrite

        view = await service.apply(db, user, job.plan_id, rollback=job.kind == "rollback")
        write = await db.scalar(
            select(CommerceWrite)
            .where(CommerceWrite.plan_id == job.plan_id)
            .order_by(CommerceWrite.id.desc())
            .limit(1)
        )
        # 저장 중 로그인 만료처럼 결과가 불명확해진 원인도 남긴다. 같은 저장은 다시 보내지 않는다.
        return {"planStatus": view["status"], "writeError": write.error_code if write else None}
    if job.kind == "verify":
        view = await service.verify(db, user, job.plan_id)
        return {"planStatus": view["status"]}
    if job.kind == "catalog":
        return await service.catalog(db, user, job.shop_id, job.input)
    if job.kind == "prepare":
        return await service.prepare(db, user, job.product_id, job.input)
    if job.kind == "measure":
        from seelo.services import commerce_measure

        return await commerce_measure.execute(db, job.input["runId"])
    if job.kind == "forget_session":
        shop = await db.get(CommerceShop, job.shop_id)
        return {"removed": await asyncio.to_thread(forget_profile, profile_path(shop))}
    raise AppError("COMMERCE_INVALID", {"reason": "unknown_job"})


async def run(job_id: int) -> None:
    """작업 하나를 실행한다. 이미 시작했거나 끝난 작업은 다시 실행하지 않는다."""
    async with session_scope() as db:
        job = await db.get(CommerceJob, job_id, with_for_update=True)
        if job is None or job.status != "queued":
            log.info("commerce_job_skip", job_id=job_id, status=job.status if job else None)
            return
        job.status, job.started_at = "running", now_utc()
        await db.commit()
        user = await db.get(User, job.requested_by) if job.requested_by else None
        result, reason = {}, None
        try:
            if user is None:
                raise AppError("FORBIDDEN", {"reason": "requester_missing"})
            result = await _execute(db, job, user)
        except AppError as error:
            await db.rollback()
            reason = str(error.details.get("reason") or error.code.lower())
            result = {"code": error.code}
        except Exception as error:  # 작업 상태를 남기고 끝낸다. 자동 재시도는 하지 않는다.
            log.exception("commerce_job_failed", job_id=job_id, error=type(error).__name__)
            await db.rollback()
            reason = "internal_error"
        job = await db.get(CommerceJob, job_id, with_for_update=True, populate_existing=True)
        job.status = "failed" if reason else "succeeded"
        job.error_code, job.result, job.finished_at = reason, result, now_utc()
        if job.kind == "collect" and result.get("productId"):
            job.product_id = result["productId"]
        collected = job.kind == "collect" and not reason and result.get("productId")
        if job.kind in BROWSER_KINDS - {"forget_session"}:
            shop = await db.get(CommerceShop, job.shop_id, with_for_update=True, populate_existing=True)
            problem = reason or result.get("writeError")
            session = (
                {"status": problem, "jobId": job.id}
                if problem in SESSION_PROBLEMS
                else {"status": "ok", "jobId": job.id}
                if problem is None
                else (shop.delegation or {}).get("browserSession", {})
            )
            if session:
                shop.delegation = {
                    **(shop.delegation or {}),
                    "browserSession": {**session, "checkedAt": now_utc().isoformat()},
                }
        await db.commit()
        log.info("commerce_job_done", job_id=job_id, kind=job.kind, status=job.status, reason=reason)
        if collected and user is not None:
            from seelo.services.commerce_service import auto_prepare

            # 수집 다음 단계(AI 조사·필요 정보 판단·정비안)를 자동으로 이어 간다.
            shop = await db.get(CommerceShop, job.shop_id)
            await auto_prepare(db, user, shop, result["productId"])
