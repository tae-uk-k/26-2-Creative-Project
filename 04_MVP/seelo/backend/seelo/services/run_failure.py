"""측정 실패 공용 처리(03 E3·E5·E7·E33). 무료 진단은 차감하지 않는다(free_usage_ledger 그대로).

- 측정 → failed(failure_reason, completed_at).
- 진단: 가게 collecting·measuring → measure_failed, 메일 diagnosis_result(failed).
- 재측정: 신청 remeasuring → remeasure_failed.
커밋은 부르는 쪽(같은 트랜잭션에서 다른 변경과 함께).
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.states import FixRequestStatus, RunKind, RunStatus, StoreStatus, transition
from seelo.models.fix import FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.store import Store
from seelo.models.user import User
from seelo.services import email_service
from seelo.timeutil import now_utc

log = structlog.get_logger()

ACTIVE_RUN = {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING}


async def fail_run(s: AsyncSession, run: MeasurementRun, reason: str) -> bool:
    """진행 중인 측정을 실패로 끝낸다. 이미 끝났으면 False(아무것도 바꾸지 않음)."""
    run_id, store_id, kind, request_id = run.id, run.store_id, run.kind, run.fix_request_id
    ok = await transition(
        s,
        MeasurementRun,
        run_id,
        from_=ACTIVE_RUN,
        to=RunStatus.FAILED,
        values={"failure_reason": reason, "completed_at": now_utc()},
    )
    if not ok:
        return False
    if kind == RunKind.DIAGNOSIS:
        await transition(
            s,
            Store,
            store_id,
            from_={StoreStatus.COLLECTING, StoreStatus.MEASURING},
            to=StoreStatus.MEASURE_FAILED,
        )
        store = await s.get(Store, store_id)
        owner = await s.get(User, store.owner_id) if store else None
        if owner is not None:
            await email_service.queue(
                s,
                "diagnosis_result",
                user=owner,
                params={"result": "failed", "run_id": run_id},
                dedupe_key=f"diagnosis_result:{run_id}",
            )
    elif request_id is not None:
        await transition(
            s,
            FixRequest,
            request_id,
            from_={FixRequestStatus.REMEASURING},
            to=FixRequestStatus.REMEASURE_FAILED,
        )
    log.info("run_failed", run_id=run_id, reason=reason, kind=kind)
    return True
