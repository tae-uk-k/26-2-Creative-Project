"""fix 큐 작업(06 4장, 13 12장). 정비 워커(worker-fix, Playwright 이미지)가 돈다. lock은 fix:{provider}.

verifyConnection(10단계), readCurrentValues(11단계), finalizeFix(12단계), applyFix·verifyFix(13단계).
readCurrentValues는 관리 화면을 읽지 않는 모드면 plan 큐로 등록된다(defer_read).
finalizeFix는 DB만 쓰므로 plan 큐(기본 워커)에서 돈다(lock request:{id}).
"""

import structlog
from procrastinate import RetryStrategy

from seelo.services import connection_service, fix_apply_service, fix_plan_service
from seelo.worker.app import app

log = structlog.get_logger()


@app.task(name="verifyConnection", queue="fix")
async def verify_connection(connection_id: int, requested_by: int | None = None) -> None:
    await connection_service.verify(connection_id, requested_by)


@app.task(name="readCurrentValues", queue="fix")
async def read_current_values(fix_plan_id: int) -> None:
    await fix_plan_service.read_current_values(fix_plan_id)


@app.task(name="applyFix", queue="fix")
async def apply_fix(fix_plan_id: int) -> None:
    await fix_apply_service.apply(fix_plan_id)


@app.task(name="verifyFix", queue="fix")
async def verify_fix(fix_log_id: int, round: int) -> None:  # noqa: A002 (06 4장 인자 이름)
    await fix_apply_service.verify(fix_log_id, round)


@app.task(name="finalizeFix", queue="plan", retry=RetryStrategy(max_attempts=1, wait=10))
async def finalize_fix(fix_request_id: int) -> None:
    await fix_apply_service.finalize(fix_request_id)
