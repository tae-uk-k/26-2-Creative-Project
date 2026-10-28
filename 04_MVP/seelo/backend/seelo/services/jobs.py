"""작업 등록·취소(06 3·7장).

- defer(): 열린 트랜잭션 안에서만 부른다. 작업 행(procrastinate_jobs)과 job_links 행이
  서비스 데이터와 같은 트랜잭션으로 커밋된다. 커밋되면 NOTIFY로 워커가 깨어난다.
- cancel_jobs(): 가게에 딸린 대기 작업은 취소, 실행 중 작업은 중단 요청.
"""

from dataclasses import dataclass
from typing import Any

import structlog
from procrastinate import PsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import JobLink

log = structlog.get_logger()


@dataclass
class JobLinks:
    store_id: int | None = None
    run_id: int | None = None
    fix_request_id: int | None = None


async def defer(
    session: AsyncSession,
    task: Any,
    *,
    args: dict[str, Any],
    links: JobLinks,
    queueing_lock: str | None = None,
    lock: str | None = None,
    schedule_in: dict[str, int] | None = None,
    queue: str | None = None,
) -> int | None:
    """작업을 같은 트랜잭션에 등록한다. 같은 queueing_lock 대기 작업이 있으면 None."""
    opts: dict[str, Any] = {
        k: v
        for k, v in {
            "queueing_lock": queueing_lock,
            "lock": lock,
            "schedule_in": schedule_in,
            "queue": queue,
        }.items()
        if v is not None
    }
    try:
        # SAVEPOINT: 중복 등록 오류가 바깥 트랜잭션을 깨지 않게 한다
        async with session.begin_nested():
            # 작업은 자기 앱을 task.blueprint로 가진다. 테스트용 InMemoryConnector는 외부 연결을 받지 않는다.
            if isinstance(getattr(task.blueprint, "connector", None), PsycopgConnector):
                # SQLAlchemy는 SAVEPOINT를 연결을 처음 요청할 때 보낸다. 그래서 연결을 이 블록 안에서 꺼낸다.
                sa_conn = await session.connection()
                raw = await sa_conn.get_raw_connection()
                opts["connection"] = raw.driver_connection  # psycopg.AsyncConnection
            job_id = await task.configure(**opts).defer_async(**args)
    except AlreadyEnqueued:
        log.info("job_already_enqueued", task=task.name, queueing_lock=queueing_lock)
        return None
    session.add(
        JobLink(
            procrastinate_job_id=job_id,
            task_name=task.name,
            store_id=links.store_id,
            run_id=links.run_id,
            fix_request_id=links.fix_request_id,
        )
    )
    return job_id


async def cancel_jobs(session: AsyncSession, *, store_ids: list[int]) -> int:
    """가게에 딸린 작업을 취소·중단 요청한다. 실패해도 계속한다(작업은 대상 행을 다시 읽어 스스로 끝난다).

    취소는 Procrastinate 자기 연결로 바로 반영된다. DB 정리 트랜잭션을 커밋하기 전에 부른다.
    """
    from seelo.worker.app import app  # 순환 import 방지

    if not store_ids:
        return 0
    job_ids = (
        await session.scalars(
            select(JobLink.procrastinate_job_id).where(JobLink.store_id.in_(store_ids)).distinct()
        )
    ).all()
    cancelled = 0
    for job_id in job_ids:
        try:
            if await app.job_manager.cancel_job_by_id_async(job_id, abort=True):
                cancelled += 1
        except Exception:  # 이미 끝난 작업 등은 무시
            log.warning("job_cancel_failed", job_id=job_id)
    return cancelled
