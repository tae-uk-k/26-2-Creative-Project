"""AI 측정 runMeasurement·callAi(08 2장, W-04-2·3)와 진행률(04 5.3).

- 질문 문장만 보낸다(지시문·앞뒤 문장 없음).
- 같은 측정의 완료 처리는 측정 행을 먼저 UPDATE(잠금)해 한 줄로 세운다. 그래야 마지막 두 호출이 동시에
  끝나도 finalizeRun이 정확히 한 번 등록된다(maybe_finalize).
- 끝난 실행(succeeded·failed)은 다시 부르지 않는다(워커 재시작에도).
"""

import asyncio
import random
from decimal import Decimal

import structlog
from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.states import ExecStatus, RunKind, RunStage, RunStatus, RunTrigger
from seelo.errors import AppError
from seelo.integrations import Clients, LlmResult, get_clients
from seelo.integrations.llm import LlmError, cost_usd
from seelo.models.fix import FixRequest
from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Question
from seelo.models.store import Store
from seelo.models.user import User
from seelo.schemas.run import RunProgress
from seelo.services import jobs
from seelo.timeutil import kst_day_range, now_utc

log = structlog.get_logger()

PROVIDERS = ("openai", "gemini")
AI_CALL_TIMEOUT_S = 60.0
MAX_ATTEMPTS = 3  # 처음 1 + 다시 2
BACKOFF_S = (2.0, 4.0)  # ±20% 무작위
COST_WAIT_MINUTES = 30
NOT_DONE = (ExecStatus.PENDING, ExecStatus.RUNNING)


def _model(provider: str) -> str:
    s = get_settings()
    return s.openai_measure_model if provider == "openai" else s.gemini_measure_model


# --- 2.1 runMeasurement ------------------------------------------------------------------


async def _spent_today(s: AsyncSession) -> float:
    start, end = kst_day_range()
    total = await s.scalar(
        select(func.coalesce(func.sum(MeasurementRun.cost_usd), 0)).where(
            MeasurementRun.created_at >= start, MeasurementRun.created_at < end
        )
    )
    return float(total or 0)


async def run(run_id: int) -> None:
    from seelo.worker.tasks_measure import call_ai, run_measurement

    async with session_scope() as s:
        r = await s.get(MeasurementRun, run_id, with_for_update=True)
        if r is None or r.status != RunStatus.RUNNING or r.question_set_id is None:
            log.info("run_measurement_skip", run_id=run_id)
            return
        links = jobs.JobLinks(store_id=r.store_id, run_id=run_id)
        limit = get_settings().daily_cost_limit_usd
        if limit > 0 and await _spent_today(s) >= limit:  # 0이면 상한 없음
            r.waiting_reason = "cost_limit"
            await jobs.defer(
                s,
                run_measurement,
                args={"run_id": run_id},
                links=links,
                queueing_lock=f"measure:{run_id}",
                schedule_in={"minutes": COST_WAIT_MINUTES},
            )
            await s.commit()
            log.warning("run_waiting_cost_limit", run_id=run_id, limit=limit)
            return
        r.waiting_reason = None
        r.stage = RunStage.CALLING_AI
        question_ids = (
            await s.scalars(
                select(Question.id)
                .where(Question.question_set_id == r.question_set_id)
                .order_by(Question.order_no)
            )
        ).all()
        repeats = get_settings().ai_repeat_count
        rows = [
            {"run_id": run_id, "question_id": q, "provider": p, "repeat_no": n, "status": ExecStatus.PENDING}
            for q in question_ids
            for p in PROVIDERS
            for n in range(1, repeats + 1)
        ]
        if rows:
            await s.execute(
                insert(AiExecution).values(rows).on_conflict_do_nothing(constraint="uq_ai_execution")
            )
        r.progress_total = await s.scalar(
            select(func.count()).select_from(AiExecution).where(AiExecution.run_id == run_id)
        )
        pending = (
            await s.execute(
                select(AiExecution.id, AiExecution.provider).where(
                    AiExecution.run_id == run_id, AiExecution.status.in_(NOT_DONE)
                )
            )
        ).all()
        for ex_id, provider in pending:
            await jobs.defer(
                s,
                call_ai,
                args={"execution_id": ex_id},
                links=links,
                queueing_lock=f"callAi:{ex_id}",
                queue=f"ai_{provider}",
            )
        await s.commit()
    log.info("run_measurement_enqueued", run_id=run_id, calls=len(pending), total=len(rows))


# --- 2.2 callAi --------------------------------------------------------------------------


async def call_ai(execution_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        ex = await s.get(AiExecution, execution_id, with_for_update=True)
        if ex is None or ex.status not in NOT_DONE:
            log.info("call_ai_skip_done", execution_id=execution_id)
            return
        r = await s.get(MeasurementRun, ex.run_id)
        if r is None or r.status != RunStatus.RUNNING:
            log.info("call_ai_skip_run", execution_id=execution_id)
            return
        question = await s.get(Question, ex.question_id)
        ex.status = ExecStatus.RUNNING
        run_id, provider, text = ex.run_id, ex.provider, question.text
        await s.commit()

    client = clients.openai if provider == "openai" else clients.gemini
    model = _model(provider)
    result: LlmResult | None = None
    error = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        async with session_scope() as s:
            await s.execute(update(AiExecution).where(AiExecution.id == execution_id).values(attempt=attempt))
            await s.commit()
        try:
            settings = get_settings()
            timeout = settings.local_ai_timeout_s if settings.ai_backend == "local_cli" else AI_CALL_TIMEOUT_S
            async with asyncio.timeout(timeout):
                result = await client.web_answer(text, model=model)  # 질문 문장만
            break
        except TimeoutError:
            error, retry = "timeout", True
        except LlmError as e:
            error, retry = e.reason, e.retryable
            if not retry and e.reason in ("bad_request", "auth_error", "not_configured"):
                log.error("ai_config_error", provider=provider, reason=e.reason)  # 오류 추적으로 보낸다
        if not retry or attempt == MAX_ATTEMPTS:
            break
        await asyncio.sleep(BACKOFF_S[attempt - 1] * random.uniform(0.8, 1.2))
    if result is not None:
        await _record_success(execution_id, run_id, provider, model, result)
    else:
        await _record_failure(execution_id, run_id, error)


async def _lock_run_progress(s: AsyncSession, run_id: int, cost: float) -> bool:
    """측정 행을 먼저 갱신해 잠금을 잡는다(같은 측정의 완료 처리를 한 줄로)."""
    locked = await s.scalar(
        update(MeasurementRun)
        .where(MeasurementRun.id == run_id, MeasurementRun.status == RunStatus.RUNNING)
        .values(
            cost_usd=MeasurementRun.cost_usd + Decimal(str(round(cost, 6))),
            progress_done=MeasurementRun.progress_done + 1,
        )
        .returning(MeasurementRun.id)
    )
    return locked is not None


async def _record_success(execution_id: int, run_id: int, provider: str, model: str, res: LlmResult) -> None:
    from seelo.worker.tasks_measure import extract_recommendations

    cost = cost_usd(
        provider,
        res.model_id or model,
        input_tokens=res.input_tokens,
        output_tokens=res.output_tokens,
        search_calls=res.search_calls,
    )
    async with session_scope() as s:
        if not await _lock_run_progress(s, run_id, cost):  # 그 사이 측정이 끝났거나 취소됨
            await s.rollback()
            return
        finished = await s.scalar(
            update(AiExecution)
            .where(AiExecution.id == execution_id, AiExecution.status == ExecStatus.RUNNING)
            .values(
                status=ExecStatus.SUCCEEDED,
                model_id=res.model_id,
                latency_ms=res.latency_ms,
                input_tokens=res.input_tokens,
                output_tokens=res.output_tokens,
                web_search_calls=res.search_calls,
                cost_usd=Decimal(str(round(cost, 6))),
                finished_at=now_utc(),
                error_code=None,
            )
            .returning(AiExecution.id)
        )
        if finished is None:  # 다른 워커가 이미 끝냄
            await s.rollback()
            return
        resp = AiResponse(
            execution_id=execution_id,
            raw_text=res.text,
            raw_json=res.raw,
            source_urls=res.sources,
            annotated_text=res.annotated_text or res.text,
        )
        s.add(resp)
        await s.flush()
        store_id = await s.scalar(select(MeasurementRun.store_id).where(MeasurementRun.id == run_id))
        await jobs.defer(
            s,
            extract_recommendations,
            args={"response_id": resp.id},
            links=jobs.JobLinks(store_id=store_id, run_id=run_id),
            queueing_lock=f"extract:{resp.id}",
        )
        await s.commit()


async def _record_failure(execution_id: int, run_id: int, error: str) -> None:
    async with session_scope() as s:
        if not await _lock_run_progress(s, run_id, 0.0):
            await s.rollback()
            return
        failed = await s.scalar(
            update(AiExecution)
            .where(AiExecution.id == execution_id, AiExecution.status == ExecStatus.RUNNING)
            .values(status=ExecStatus.FAILED, error_code=error, finished_at=now_utc())
            .returning(AiExecution.id)
        )
        if failed is None:
            await s.rollback()
            return
        await maybe_finalize(s, run_id)
        await s.commit()
    log.info("ai_execution_failed", execution_id=execution_id, error=error)


async def maybe_finalize(s: AsyncSession, run_id: int) -> bool:
    """측정 행 잠금을 잡은 트랜잭션 안에서만 부른다. 남은 실행·추출이 없으면 finalizeRun 등록."""
    from seelo.worker.tasks_measure import finalize_run

    open_exec = await s.scalar(
        select(exists().where(AiExecution.run_id == run_id, AiExecution.status.in_(NOT_DONE)))
    )
    open_extract = await s.scalar(
        select(
            exists().where(
                AiResponse.execution_id == AiExecution.id,
                AiExecution.run_id == run_id,
                AiResponse.extraction_status == "pending",
            )
        )
    )
    if open_exec or open_extract:
        return False
    store_id = await s.scalar(select(MeasurementRun.store_id).where(MeasurementRun.id == run_id))
    await jobs.defer(
        s,
        finalize_run,
        args={"run_id": run_id},
        links=jobs.JobLinks(store_id=store_id, run_id=run_id),
        queueing_lock=f"finalize:{run_id}",
        lock=f"run:{run_id}",
    )
    return True


# --- 진행률(04 5.3): DB 조회 1번, 외부 호출 없음 ---------------------------------------------


async def progress(db: AsyncSession, user: User, run_id: int) -> RunProgress:
    other = aliased(MeasurementRun)  # 바깥 측정과 따로(자동 상관 방지)
    completed_other = (
        select(func.count())
        .select_from(other)
        .where(other.store_id == Store.id, other.status == RunStatus.COMPLETED)
        .correlate(Store)
        .scalar_subquery()
    )
    has_request = select(exists().where(FixRequest.store_id == Store.id)).scalar_subquery()
    row = (
        await db.execute(
            select(MeasurementRun, Store.owner_id, Store.archived_at, completed_other, has_request)
            .join(Store, Store.id == MeasurementRun.store_id)
            .where(MeasurementRun.id == run_id)
        )
    ).first()
    if row is None or (row[1] != user.id and user.role != "admin"):
        raise AppError("NOT_FOUND")
    r, _, archived_at, completed_count, requested = row
    can_cancel = (
        r.kind == RunKind.DIAGNOSIS
        and r.trigger == RunTrigger.INITIAL
        and archived_at is None
        and not requested
        and not completed_count
        and r.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING)
    )
    nxt = None
    if r.status == RunStatus.COMPLETED:
        nxt = f"/diagnosis/{r.id}" if r.kind == RunKind.DIAGNOSIS else "/fix/report"
    return RunProgress(
        run_id=r.id,
        kind=r.kind,  # type: ignore[arg-type]
        status=r.status,  # type: ignore[arg-type]
        stage=r.stage,  # type: ignore[arg-type]
        progress_done=r.progress_done,
        progress_total=r.progress_total,
        waiting_reason=r.waiting_reason,  # type: ignore[arg-type]
        failure_reason=r.failure_reason,  # type: ignore[arg-type]
        can_cancel=can_cancel,
        next=nxt,
    )
