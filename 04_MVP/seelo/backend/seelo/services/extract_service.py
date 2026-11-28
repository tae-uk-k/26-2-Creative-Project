"""추천 추출 extractRecommendations(08 3장, W-05-1).

- LLM(OPENAI_CHEAP_MODEL, structured, 60초)에 출처 번호를 넣은 원문·출처 도메인·우리 가게 이름(사장님 입력과
  Google ko·en만)을 보낸다. 카카오·네이버 이름은 보내지 않는다.
- 실패(스키마 오류·거절·시간 초과)면 작업 안에서 1번 다시. 그래도 실패면 extraction_status = failed,
  측정 extraction_failed_count += 1(원문은 남긴다). 추천 0개도 성공이다.
- 저장은 한 트랜잭션이고 측정 행을 먼저 잠근다(비용 더하기·실패 수 UPDATE). 마지막에 maybe_finalize.
"""

import asyncio
from decimal import Decimal

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.extraction import RecRow, extraction_prompt, postprocess
from seelo.domain.states import ExtractionStatus, RunStatus
from seelo.integrations import Clients, StructuredResult, get_clients
from seelo.integrations.llm import LlmError, cost_usd
from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Recommendation
from seelo.models.store import Store
from seelo.schemas.llm import ExtractionOut
from seelo.services.collect_service import latest_snapshot
from seelo.services.measure_service import maybe_finalize

log = structlog.get_logger()

EXTRACT_TIMEOUT_S = 60.0
EXTRACT_ATTEMPTS = 2  # 처음 1 + 다시 1


def prompt_names(store_name: str, google: dict | None) -> list[str]:
    """추출 프롬프트에 넣는 우리 가게 이름: 사장님 입력, Google ko·en displayName(08 3.2)."""
    ko, en = (google or {}).get("ko") or {}, (google or {}).get("en") or {}
    names = [store_name, (ko.get("displayName") or {}).get("text"), (en.get("displayName") or {}).get("text")]
    return [n for n in dict.fromkeys(names) if n]


async def _lock_run(s: AsyncSession, run_id: int, *, cost: float = 0.0, failed: bool = False) -> bool:
    """측정 행을 먼저 갱신해 잠금을 잡는다. 측정이 running이 아니면 False(결과를 버림)."""
    values: dict = {"cost_usd": MeasurementRun.cost_usd + Decimal(str(round(cost, 6)))}
    if failed:
        values["extraction_failed_count"] = MeasurementRun.extraction_failed_count + 1
    locked = await s.scalar(
        update(MeasurementRun)
        .where(MeasurementRun.id == run_id, MeasurementRun.status == RunStatus.RUNNING)
        .values(**values)
        .returning(MeasurementRun.id)
    )
    return locked is not None


async def _finish_response(s: AsyncSession, response_id: int, status: str, **values: object) -> bool:
    """pending인 응답만 끝낸다(같은 작업이 두 번 돌아도 한 번만)."""
    done = await s.scalar(
        update(AiResponse)
        .where(AiResponse.id == response_id, AiResponse.extraction_status == ExtractionStatus.PENDING)
        .values(extraction_status=status, **values)
        .returning(AiResponse.id)
    )
    return done is not None


async def extract(response_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        row = (
            await s.execute(
                select(AiResponse, AiExecution.run_id, MeasurementRun.status, Store.name, Store.id)
                .join(AiExecution, AiExecution.id == AiResponse.execution_id)
                .join(MeasurementRun, MeasurementRun.id == AiExecution.run_id)
                .join(Store, Store.id == MeasurementRun.store_id)
                .where(AiResponse.id == response_id)
            )
        ).first()
        if row is None:
            log.info("extract_skip_missing", response_id=response_id)
            return
        resp, run_id, run_status, store_name, store_id = row
        if resp.extraction_status != ExtractionStatus.PENDING or run_status != RunStatus.RUNNING:
            log.info("extract_skip", response_id=response_id, run_id=run_id)
            return
        google = await latest_snapshot(s, store_id, run_id, "google")
        prompt = extraction_prompt(
            resp.annotated_text or resp.raw_text, resp.source_urls or [], prompt_names(store_name, google)
        )
        sources = list(resp.source_urls or [])
        await s.commit()  # LLM 호출 동안 트랜잭션을 열어 두지 않는다

    result, reason = await _call(clients, prompt, response_id)
    if result is None:
        await _record_failure(response_id, run_id, reason)
        return
    out: ExtractionOut = result.parsed  # type: ignore[assignment]
    rows = postprocess(out, sources)
    cost = cost_usd(
        "openai", result.model_id, input_tokens=result.input_tokens, output_tokens=result.output_tokens
    )
    await _record_success(response_id, run_id, out, rows, cost)


async def _call(clients: Clients, prompt: str, response_id: int) -> tuple[StructuredResult | None, str]:
    model = get_settings().openai_cheap_model
    reason = "unknown"
    for attempt in range(1, EXTRACT_ATTEMPTS + 1):
        try:
            async with asyncio.timeout(EXTRACT_TIMEOUT_S):
                return await clients.openai.structured(prompt, ExtractionOut, model=model), ""
        except TimeoutError:
            reason = "timeout"
        except LlmError as e:
            reason = e.reason
        log.info("extract_attempt_failed", response_id=response_id, attempt=attempt, reason=reason)
    return None, reason


async def _record_success(
    response_id: int, run_id: int, out: ExtractionOut, rows: list[RecRow], cost: float
) -> None:
    async with session_scope() as s:
        if not await _lock_run(s, run_id, cost=cost):  # 그 사이 측정이 끝났거나 취소됨
            await s.rollback()
            return
        claims = [c.model_dump() for c in out.target_claims]
        if not await _finish_response(
            s,
            response_id,
            ExtractionStatus.SUCCEEDED,
            extraction_json=out.model_dump(),
            target_claims=claims,
        ):
            await s.rollback()
            return
        s.add_all(
            Recommendation(
                response_id=response_id,
                name=r.name,
                normalized_name=r.normalized_name,
                rank=r.rank,
                source_urls=r.source_urls,
                mentioned_attributes=r.mentioned_attributes,
                is_target=False,  # 판정은 finalizeRun(08 4장)
            )
            for r in rows
        )
        await s.flush()
        await maybe_finalize(s, run_id)
        await s.commit()
    log.info("extracted", response_id=response_id, recommendations=len(rows))


async def _record_failure(response_id: int, run_id: int, reason: str) -> None:
    async with session_scope() as s:
        if not await _lock_run(s, run_id, failed=True):
            await s.rollback()
            return
        if not await _finish_response(s, response_id, ExtractionStatus.FAILED):
            await s.rollback()
            return
        await maybe_finalize(s, run_id)
        await s.commit()
    log.warning("extraction_failed", response_id=response_id, reason=reason)
