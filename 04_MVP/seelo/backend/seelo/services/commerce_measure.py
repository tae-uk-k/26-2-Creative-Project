"""쇼핑몰 AI 노출 진단 실행·조회·전후 비교.

지도 베타의 질문 생성·측정 흐름과 14일 재측정·가격 정책을 쓰지 않는다. 측정은 운영자·고객이 직접 시작한다.
"""

import hashlib

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.domain import commerce_measure as rules
from seelo.errors import AppError
from seelo.integrations import get_clients
from seelo.integrations.llm import MEASURE_TOOL_OPTIONS, LlmError
from seelo.models.commerce import (
    CommerceJob,
    CommerceMeasureAnswer,
    CommerceMeasureRun,
    CommerceMeasureSet,
    CommercePlan,
)
from seelo.models.user import User
from seelo.schemas import commerce as schema
from seelo.services import commerce_service as service
from seelo.timeutil import now_utc

log = structlog.get_logger()
PROVIDERS = {"openai": "openai_measure_model", "gemini": "gemini_measure_model"}


def set_view(row: CommerceMeasureSet) -> dict:
    return {
        "id": row.id,
        "productId": row.product_id,
        "name": row.name,
        "commonSuffix": row.common_suffix,
        "queries": row.queries,
        "targets": row.targets,
        "createdAt": row.created_at,
    }


def answer_view(row: CommerceMeasureAnswer) -> dict:
    return {
        "id": row.id,
        "query_id": row.query_id,
        "repeat": row.repeat,
        "attempt": row.attempt,
        "status": row.status,
        "errorCode": row.error_code,
        "prompt": row.prompt,
        "rawText": row.raw_text,
        "sources": row.sources,
        "modelId": row.model_id,
        "identified": row.identified,
        "recommended": row.recommended,
        "rank": row.rank,
        "target_url_cited": row.target_url_cited,
        "evaluation": row.evaluation,
        "measuredAt": row.measured_at,
    }


async def run_view(db: AsyncSession, run: CommerceMeasureRun, *, answers: bool = False) -> dict:
    from seelo.services.commerce_jobs import job_view

    measure_set = await db.get(CommerceMeasureSet, run.set_id)
    rows = list(
        await db.scalars(
            select(CommerceMeasureAnswer)
            .where(CommerceMeasureAnswer.run_id == run.id)
            .order_by(CommerceMeasureAnswer.id)
        )
    )
    job = await db.scalar(
        select(CommerceJob)
        .where(CommerceJob.kind == "measure", CommerceJob.input["runId"].as_integer() == run.id)
        .order_by(CommerceJob.id.desc())
        .limit(1)
    )
    views = [answer_view(r) for r in rows]
    view = {
        "id": run.id,
        "setId": run.set_id,
        "productId": run.product_id,
        "label": run.label,
        "status": run.status,
        "condition": run.condition,
        "snapshotHash": run.snapshot_hash,
        "planId": run.plan_id,
        "createdAt": run.created_at,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "job": job_view(job),
        "summary": rules.summarize(measure_set.queries, run.condition["repeats"], views),
    }
    if answers:
        view["answers"] = views
    return view


async def owned_set(db: AsyncSession, user: User, set_id: int) -> tuple[CommerceMeasureSet, object, object]:
    row = await db.get(CommerceMeasureSet, set_id)
    if row is None:
        raise AppError("NOT_FOUND")
    shop, product = await service.owned_product(db, user, row.product_id)
    return row, shop, product


async def owned_run(db: AsyncSession, user: User, run_id: int) -> CommerceMeasureRun:
    row = await db.get(CommerceMeasureRun, run_id)
    if row is None:
        raise AppError("NOT_FOUND")
    await service.owned_product(db, user, row.product_id)
    return row


async def create_set(db: AsyncSession, user: User, product_id: int, body: schema.MeasureSetCreate) -> dict:
    shop, product = await service.owned_product(db, user, product_id)
    queries = [q.model_dump() for q in body.queries]
    targets = {
        "names": body.target_names or [product.name],
        "urls": body.target_urls,
    }
    rules.check_set(queries, targets)
    row = CommerceMeasureSet(
        product_id=product.id,
        name=body.name,
        common_suffix=body.common_suffix or rules.DEFAULT_SUFFIX,
        queries=queries,
        targets=targets,
        created_by=user.id,
    )
    db.add(row)
    await db.flush()
    service.event(db, user, "measure", shop.id, setId=row.id, queries=len(queries))
    await db.commit()
    return set_view(row)


async def request_run(db: AsyncSession, user: User, set_id: int, body: schema.MeasureRunCreate) -> dict:
    from seelo.services import commerce_jobs

    measure_set, shop, product = await owned_set(db, user, set_id)
    model = getattr(get_settings(), PROVIDERS[body.provider])
    if not model:
        raise AppError("COMMERCE_AI_UNAVAILABLE")
    # 측정 당시 상품 원본과 마지막으로 반영된 정비안을 함께 남겨 전후를 구분한다.
    latest_plan = await db.scalar(
        select(CommercePlan.id)
        .where(
            CommercePlan.product_id == product.id,
            CommercePlan.status.in_(["applied", "rolled_back", "manual_recorded"]),
        )
        .order_by(CommercePlan.applied_at.desc().nulls_last(), CommercePlan.id.desc())
        .limit(1)
    )
    run = CommerceMeasureRun(
        set_id=measure_set.id,
        product_id=product.id,
        label=body.label,
        condition={
            "provider": body.provider,
            "model": model,
            "toolOptions": MEASURE_TOOL_OPTIONS,
            "repeats": body.repeats,
            "suffixHash": hashlib.sha256(measure_set.common_suffix.encode()).hexdigest()[:16],
        },
        snapshot_hash=product.snapshot_hash,
        plan_id=latest_plan,
        created_by=user.id,
    )
    db.add(run)
    await db.flush()
    service.event(db, user, "measure", shop.id, runId=run.id, label=body.label, provider=body.provider)
    if commerce_jobs.worker_mode():
        await commerce_jobs.enqueue(
            db,
            user,
            shop,
            "measure",
            dedupe=f"measure:{run.id}",
            product_id=product.id,
            payload={"runId": run.id, "provider": body.provider},
        )
    else:
        await db.commit()
        await execute(db, run.id)
    return await run_view(db, await db.get(CommerceMeasureRun, run.id, populate_existing=True))


async def _ask(provider: str, model: str, prompt: str) -> tuple[dict | None, str | None]:
    client = getattr(get_clients(), provider)
    try:
        result = await client.web_answer(prompt, model=model)
    except LlmError as error:
        return None, error.reason
    return {"text": result.text, "sources": result.sources, "model_id": result.model_id}, None


async def execute(db: AsyncSession, run_id: int) -> dict:
    """질문 × 반복을 독립 요청으로 실행한다. 실패는 1회만 다시 실행하고 최초 실패도 남긴다."""
    run = await db.get(CommerceMeasureRun, run_id, with_for_update=True)
    if run is None or run.status != "queued":
        return {"skipped": True}
    measure_set = await db.get(CommerceMeasureSet, run.set_id)
    run.status, run.started_at = "running", now_utc()
    await db.commit()
    provider, model = run.condition["provider"], run.condition["model"]
    ok = failed = 0
    for query in measure_set.queries:
        # 자연 발견 질문: 고정 질문 + 공통 문구. 스토어 URL·이전 답변·프로젝트 맥락을 넣지 않는다.
        prompt = f"{query['question']} {measure_set.common_suffix}"
        for repeat in range(1, run.condition["repeats"] + 1):
            for attempt in (1, 2):
                answer, error = await _ask(provider, model, prompt)
                row = CommerceMeasureAnswer(
                    run_id=run.id,
                    query_id=query["id"],
                    repeat=repeat,
                    attempt=attempt,
                    prompt=prompt,
                    status="ok" if answer else "failed",
                    error_code=error,
                    sources=(answer or {}).get("sources", []),
                    raw_text=(answer or {}).get("text"),
                    model_id=(answer or {}).get("model_id"),
                    evaluation={},
                )
                if answer:
                    judged = rules.evaluate(answer["text"], answer["sources"], measure_set.targets)
                    row.identified, row.recommended = judged["identified"], judged["recommended"]
                    row.rank, row.target_url_cited = judged["rank"], judged["target_url_cited"]
                    row.evaluation = judged["evaluation"]
                db.add(row)
                await db.commit()
                if answer:
                    ok += 1
                    break
                if attempt == 2:
                    failed += 1
    run = await db.get(CommerceMeasureRun, run_id, with_for_update=True, populate_existing=True)
    # 모든 질문·반복에서 정상 응답을 얻어야 completed. 일부 실패는 partial로 남긴다.
    run.status = "completed" if failed == 0 else "partial" if ok else "failed"
    run.finished_at = now_utc()
    await db.commit()
    return {"runId": run.id, "status": run.status, "valid": ok, "missing": failed}


async def compare(db: AsyncSession, user: User, before_id: int, after_id: int) -> dict:
    before = await run_view(db, await owned_run(db, user, before_id))
    after = await run_view(db, await owned_run(db, user, after_id))
    if before["productId"] != after["productId"]:
        raise AppError("COMMERCE_INVALID", {"reason": "measure_product_mismatch"})
    rules.comparable(before, after)
    rows = []
    after_rows = {r["queryId"]: r for r in after["summary"]["queries"]}
    for row in before["summary"]["queries"]:
        other = after_rows[row["queryId"]]
        rows.append(
            {
                "queryId": row["queryId"],
                "family": row["family"],
                "before": row,
                "after": other,
                # 정상 응답 수가 다르면 비율로 비교한다. 정상 응답이 없으면 비교하지 않는다.
                "comparable": bool(row["valid"] and other["valid"]),
            }
        )
    return {
        "before": {
            k: before[k] for k in ("id", "label", "snapshotHash", "planId", "condition", "finishedAt")
        },
        "after": {k: after[k] for k in ("id", "label", "snapshotHash", "planId", "condition", "finishedAt")},
        "sameSnapshot": before["snapshotHash"] == after["snapshotHash"],
        "queries": rows,
        "totals": {"before": before["summary"]["totals"], "after": after["summary"]["totals"]},
    }
