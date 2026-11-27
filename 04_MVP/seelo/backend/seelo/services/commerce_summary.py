"""상품 목록에 붙이는 진행 요약. 화면이 상품마다 다음 할 일을 고를 수 있게 한다.

읽기 전용이다. 상품마다 최신 정비안·AI 준비 작업·측정 회차를 한 번에 모아 N+1 조회를 피한다.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.commerce import CommerceJob, CommerceMeasureRun, CommercePlan
from seelo.services.commerce_jobs import is_stale

FINISHED_RUNS = ("completed", "partial")


def _condition_key(run: CommerceMeasureRun) -> tuple:
    # 화면의 보고서(src/commerce/report.ts)와 같은 기준이다. 같은 세트·같은 조건끼리만 비교한다.
    condition = run.condition or {}
    return (
        run.set_id,
        *(str(condition.get(key)) for key in ("provider", "model", "toolOptions", "repeats")),
    )


async def product_summaries(db: AsyncSession, product_ids: list[int]) -> dict[int, dict]:
    if not product_ids:
        return {}
    latest_plan = (
        select(func.max(CommercePlan.id))
        .where(CommercePlan.product_id.in_(product_ids))
        .group_by(CommercePlan.product_id)
    )
    plans = {
        plan.product_id: plan
        for plan in await db.scalars(select(CommercePlan).where(CommercePlan.id.in_(latest_plan)))
    }
    latest_prepare = (
        select(func.max(CommerceJob.id))
        .where(CommerceJob.product_id.in_(product_ids), CommerceJob.kind == "prepare")
        .group_by(CommerceJob.product_id)
    )
    prepares = {
        job.product_id: job
        for job in await db.scalars(select(CommerceJob).where(CommerceJob.id.in_(latest_prepare)))
    }
    runs: dict[int, list[CommerceMeasureRun]] = {}
    for run in await db.scalars(
        select(CommerceMeasureRun)
        .where(CommerceMeasureRun.product_id.in_(product_ids))
        .order_by(CommerceMeasureRun.id.desc())
    ):
        runs.setdefault(run.product_id, []).append(run)
    result = {}
    for product_id in product_ids:
        plan = plans.get(product_id)
        job = prepares.get(product_id)
        measured = runs.get(product_id, [])
        finished = [run for run in measured if run.status in FINISHED_RUNS]
        baselines = {_condition_key(run) for run in finished if run.plan_id is None}
        publication = (plan.publication or {}) if plan else {}
        checks = ("pc_matches", "mobile_matches", "checked_at")
        result[product_id] = {
            "planId": plan.id if plan else None,
            "planStatus": plan.status if plan else None,
            "questions": len(plan.questions or []) if plan else 0,
            "published": all(publication.get(key) for key in checks),
            "prepare": {"status": job.status, "stale": is_stale(job)} if job else None,
            "measure": {
                "runs": len(measured),
                "latestStatus": measured[0].status if measured else None,
                # 정비 전 기준 회차(반영한 정비안 없음)와 같은 조건의 정비 후 회차가
                # 모두 끝나야 보고서를 만든다.
                "baseline": bool(baselines),
                "followUp": any(
                    run.plan_id is not None and _condition_key(run) in baselines for run in finished
                ),
            },
        }
    return result
