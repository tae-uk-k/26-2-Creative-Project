"""주기 작업(06 5장). 워커가 등록하고, 워커가 여러 개여도 주기마다 한 번만 등록된다."""

import structlog

from seelo.db import session_scope
from seelo.services import maintenance
from seelo.timeutil import now_utc
from seelo.worker.app import app

log = structlog.get_logger()


@app.periodic(cron="5 * * * *")
@app.task(name="cleanupUnverified", queue="periodic", queueing_lock="cleanupUnverified")
async def cleanup_unverified(timestamp: int) -> None:
    async with session_scope() as s:
        counts = await maintenance.cleanup_unverified(s, now_utc())
        await s.commit()
    log.info("cleanup_unverified", **counts)


FINISHED_JOB_KEEP_HOURS = 7 * 24


@app.periodic(cron="30 18 * * *")  # UTC 18:30 = KST 03:30
@app.task(name="purgeSnapshots", queue="periodic", queueing_lock="purgeSnapshots")
async def purge_snapshots(timestamp: int) -> None:
    """보관 기한 지난 스냅샷·웹 근거, 7일 지난 끝난 작업 행과 그 job_links 삭제(06 5장, 02 9장)."""
    from seelo.services import collect_service

    await app.job_manager.delete_old_jobs(
        nb_hours=FINISHED_JOB_KEEP_HOURS, include_failed=True, include_cancelled=True, include_aborted=True
    )
    async with session_scope() as s:
        counts = await collect_service.purge_expired(s)
        await s.commit()
    log.info("purge_snapshots", **counts)


@app.periodic(cron="*/10 * * * *")
@app.task(name="retryStalledJobs", queue="periodic", queueing_lock="retryStalledJobs")
async def retry_stalled_jobs(timestamp: int) -> None:
    """워커가 죽어 doing으로 남은 작업(하트비트 30초 끊김)을 다시 시도한다(06 5장)."""
    n = 0
    for job in await app.job_manager.get_stalled_jobs():
        await app.job_manager.retry_job(job)
        n += 1
    if n:
        log.warning("stalled_jobs_retried", count=n)


@app.periodic(cron="*/10 * * * *")
@app.task(name="failStuckWork", queue="periodic", queueing_lock="failStuckWork")
async def fail_stuck_work(timestamp: int) -> None:
    """마지막 안전장치(06 5장): 30분 넘게 멈춘 측정, 20분 넘게 generating인 정비안·보고서를 실패로."""
    async with session_scope() as s:
        counts = await maintenance.fail_stuck_work(s)
        await s.commit()
    if any(counts.values()):
        log.warning("stuck_work_failed", **counts)


@app.periodic(cron="15 * * * *")
@app.task(name="checkPendingInvites", queue="periodic", queueing_lock="checkPendingInvites")
async def check_pending_invites(timestamp: int) -> None:
    """E31: 초대하고 3일 지나도 연결되지 않으면 사장님에게 안내 메일 1번."""
    from seelo.services import connection_service

    async with session_scope() as s:
        n = await connection_service.check_pending_invites(s)
        await s.commit()
    if n:
        log.info("invite_reminders", count=n)


@app.periodic(cron="25 * * * *")
@app.task(name="recheckPendingFixes", queue="periodic", queueing_lock="recheckPendingFixes")
async def recheck_pending_fixes(timestamp: int) -> None:
    """E32: 반영 대기 칸을 매시간 확인(verifyFix 등록), 24시간 지나면 manual_required(09 10장)."""
    from seelo.services import fix_apply_service

    async with session_scope() as s:
        counts = await fix_apply_service.recheck_pending(s)
        await s.commit()
    if any(counts.values()):
        log.info("recheck_pending_fixes", **counts)


@app.periodic(cron="*/10 * * * *")
@app.task(name="dispatchRemeasures", queue="periodic", queueing_lock="dispatchRemeasures")
async def dispatch_remeasures(timestamp: int) -> None:
    """지난 예약을 DB에서 다시 읽으므로 워커 재시작과 무관하다(10 1장)."""
    from seelo.services import remeasure_service

    runs = await remeasure_service.dispatch()
    log.info("remeasures_dispatched", count=len(runs))
