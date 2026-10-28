"""정리 작업 본체(06 5장 cleanupUnverified, 05 4.5)."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.store import IdentifySession
from seelo.models.user import AuthToken, PendingSignup, RateLimit, User
from seelo.models.user import Session as SessionRow
from seelo.timeutil import now_utc

UNVERIFIED_TTL = timedelta(hours=24)
RATE_LIMIT_TTL = timedelta(hours=1)
TOKEN_KEEP_AFTER_DONE = timedelta(days=7)


async def cleanup_unverified(session: AsyncSession, now: datetime) -> dict[str, int]:
    """만료·미인증 데이터를 지운다. 지운 행 수를 돌려준다(커밋은 부르는 쪽)."""

    async def _delete(stmt) -> int:  # noqa: ANN001
        return (await session.execute(stmt)).rowcount or 0

    return {
        "users": await _delete(
            delete(User).where(User.email_verified_at.is_(None), User.created_at < now - UNVERIFIED_TTL)
        ),
        "sessions": await _delete(delete(SessionRow).where(SessionRow.expires_at <= now)),
        "pending_signups": await _delete(delete(PendingSignup).where(PendingSignup.expires_at <= now)),
        "identify_sessions": await _delete(delete(IdentifySession).where(IdentifySession.expires_at <= now)),
        "rate_limits": await _delete(delete(RateLimit).where(RateLimit.window_start < now - RATE_LIMIT_TTL)),
        # 키 이름에 token이 들어가면 로그 가림 처리기가 값을 가리므로 links로 부른다
        "auth_links": await _delete(
            delete(AuthToken).where(
                or_(
                    AuthToken.used_at < now - TOKEN_KEEP_AFTER_DONE,
                    AuthToken.expires_at < now - TOKEN_KEEP_AFTER_DONE,
                )
            )
        ),
    }


STUCK_RUN = timedelta(minutes=30)
STUCK_GENERATION = timedelta(minutes=20)
_LIVE_JOB = (
    "EXISTS (SELECT 1 FROM job_links jl JOIN procrastinate_jobs j ON j.id = jl.procrastinate_job_id "
    "WHERE {cond} AND j.status IN ('todo', 'doing'))"
)


async def fail_stuck_work(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """06 5장 failStuckWork. 커밋은 부르는 쪽.

    - 측정: 진행 중 상태로 30분 넘게 바뀌지 않았고, 비용 대기가 아니며, 살아 있는 작업(todo·doing)이 없음
      → failed(stuck). 진단이면 가게 measure_failed + 메일, 재측정이면 신청 remeasure_failed. 무료 차감 없음.
    - 정비안·보고서: generating이 20분 넘음 + 그 신청의 살아 있는 작업 없음 → generation_failed(stuck).
    """
    from sqlalchemy import select, text

    from seelo.models.measurement import MeasurementRun
    from seelo.services.run_failure import fail_run

    now = now or now_utc()
    not_live = text("NOT " + _LIVE_JOB.format(cond="jl.run_id = measurement_runs.id"))
    stuck_ids = (
        await session.scalars(
            select(MeasurementRun.id).where(
                MeasurementRun.status.in_(["queued", "running", "parsing"]),
                MeasurementRun.updated_at < now - STUCK_RUN,
                MeasurementRun.waiting_reason.is_(None),
                not_live,
            )
        )
    ).all()
    runs = 0
    for run_id in stuck_ids:
        run = await session.get(MeasurementRun, run_id, with_for_update=True)
        if run is not None and await fail_run(session, run, "stuck"):
            runs += 1
    cut = now - STUCK_GENERATION
    done = {}
    for table in ("fix_plans", "comparison_reports"):
        sql = (
            f"UPDATE {table} x SET status = 'generation_failed', last_error = 'stuck' "
            "WHERE x.status = 'generating' AND x.created_at < :cut AND NOT "
            + _LIVE_JOB.format(cond="jl.fix_request_id = x.fix_request_id")
        )
        done[table] = (await session.execute(text(sql), {"cut": cut})).rowcount or 0
    return {"runs": runs, "fix_plans": done["fix_plans"], "reports": done["comparison_reports"]}
