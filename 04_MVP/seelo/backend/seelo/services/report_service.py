"""보고서 생성·조회·새 버전 재생성(10 3장, 04 7.4, E22·E24)."""

import asyncio

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import session_scope
from seelo.domain import report_builder
from seelo.domain.field_dictionary import field_label
from seelo.domain.report_builder import QuestionView, RunMetricsView
from seelo.domain.states import transition
from seelo.errors import AppError
from seelo.models.fix import FixLog, FixPlanItem, FixRequest, RemeasureSchedule
from seelo.models.measurement import AiExecution, MeasurementRun, Question
from seelo.models.report import ComparisonReport
from seelo.models.store import Store
from seelo.models.user import User
from seelo.schemas.report import ChangeView, ReportContent, ReportResponse
from seelo.services import audit, diagnosis_service, email_service, finalize_service, jobs
from seelo.timeutil import now_utc

log = structlog.get_logger()
GENERATE_ATTEMPTS = 2


async def _defer(s: AsyncSession, report: ComparisonReport) -> None:
    from seelo.worker.tasks_report import generate_comparison_report

    await jobs.defer(
        s,
        generate_comparison_report,
        args={"report_id": report.id},
        links=jobs.JobLinks(
            store_id=report.store_id, run_id=report.after_run_id, fix_request_id=report.fix_request_id
        ),
        queueing_lock=f"report:{report.id}",
        lock=f"report:{report.id}",
    )


async def create(s: AsyncSession, req: FixRequest, run_id: int, *, interval_days: int) -> ComparisonReport:
    """호출자가 신청을 잠그고, 보고서와 다음 작업을 함께 커밋한다(E21·E24)."""
    version = (
        await s.scalar(
            select(func.max(ComparisonReport.version)).where(ComparisonReport.fix_request_id == req.id)
        )
    ) or 0
    report = ComparisonReport(
        fix_request_id=req.id,
        store_id=req.store_id,
        base_run_id=req.base_run_id,
        after_run_id=run_id,
        interval_days=interval_days,
        version=version + 1,
        status="generating",
    )
    s.add(report)
    await s.flush()
    await _defer(s, report)
    return report


async def _view(s: AsyncSession, run_id: int) -> RunMetricsView:
    run = await s.get(MeasurementRun, run_id)
    if run is None or run.status != "completed" or run.question_set_id is None or run.completed_at is None:
        raise ValueError("report_run_incomplete")
    executions = (
        await s.execute(
            select(AiExecution.provider, AiExecution.model_id, AiExecution.repeat_no)
            .where(AiExecution.run_id == run_id)
            .order_by(AiExecution.id)
        )
    ).all()
    models = {p: None for p in ("openai", "gemini")}
    transports: dict[str, set[str]] = {p: set() for p in models}
    for provider, model, _ in executions:
        if model:
            transports[provider].add(
                "local_cli" if model.startswith(("codex-cli/", "gemini-cli/")) else "api"
            )
            models[provider] = model
    if any(len(values) > 1 for values in transports.values()):
        raise ValueError("report_conditions_mismatch")
    return RunMetricsView(
        rows=await diagnosis_service.metric_rows(s, run_id),
        responses=await finalize_service.response_views(s, run_id),
        measured_at=run.completed_at,
        question_set_id=run.question_set_id,
        repeat_count=max((r.repeat_no for r in executions), default=0),
        models=models,
    )


async def _build(s: AsyncSession, report: ComparisonReport):
    req = await s.get(FixRequest, report.fix_request_id)
    before, after = await _view(s, report.base_run_id), await _view(s, report.after_run_id)
    if req.fix_completed_at is None or before.question_set_id != after.question_set_id:
        raise ValueError("report_conditions_mismatch")
    questions = [
        QuestionView(q.id, q.order_no, q.lang, q.text, q.text_ko)
        for q in await s.scalars(
            select(Question)
            .where(Question.question_set_id == before.question_set_id)
            .order_by(Question.order_no)
        )
    ]
    logs = (
        (
            await s.execute(
                select(FixLog)
                .join(FixPlanItem, FixPlanItem.id == FixLog.fix_plan_item_id)
                .where(FixLog.fix_request_id == req.id)
                .order_by(FixLog.provider, FixPlanItem.order_no, FixLog.id)
            )
        )
        .scalars()
        .all()
    )
    changes = [
        ChangeView(
            provider=r.provider,
            field=r.field,
            field_label=field_label(r.provider, r.field),
            before_value=r.before_value,
            applied_value=r.applied_value,
            status=r.status,
            method=r.method,
            verified_at=r.verified_at,
            remeasure_match=r.remeasure_match or "unknown",
        )
        for r in logs
    ]
    schedule = await s.scalar(
        select(RemeasureSchedule)
        .where(
            RemeasureSchedule.fix_request_id == req.id,
            RemeasureSchedule.status == "started",
        )
        .order_by(RemeasureSchedule.id.desc())
        .limit(1)
    )
    return report_builder.build_report(
        before=before,
        after=after,
        questions=questions,
        changes=changes,
        fix_completed_at=req.fix_completed_at,
        interval_days=report.interval_days or 0,
        early=bool(schedule and schedule.triggered_by == "admin"),
    )


async def generate(report_id: int) -> None:
    async with session_scope() as s:
        report = await s.get(ComparisonReport, report_id, with_for_update=True)
        req = await s.get(FixRequest, report.fix_request_id) if report else None
        if report is None or report.status != "generating" or req is None or req.status != "remeasuring":
            return
        report.generation_attempts += 1
        await s.commit()
    try:
        async with asyncio.timeout(180):
            async with session_scope() as s:
                report = await s.get(ComparisonReport, report_id)
                if report is None or report.status != "generating":
                    return
                content = await _build(s, report)
                report_builder.assert_no_banned_terms(content)
            async with session_scope() as s:
                # 신청 → 보고서 순으로 잠가 E24와 잠금 순서를 맞춘다.
                req_id = await s.scalar(
                    select(ComparisonReport.fix_request_id).where(ComparisonReport.id == report_id)
                )
                req = await s.get(FixRequest, req_id, with_for_update=True) if req_id else None
                report = await s.get(ComparisonReport, report_id, with_for_update=True)
                if (
                    req is None
                    or req.status != "remeasuring"
                    or report is None
                    or report.status != "generating"
                ):
                    return
                await transition(
                    s,
                    ComparisonReport,
                    report_id,
                    from_={"generating"},
                    to="completed",
                    values={
                        "content": _storage_content(content),
                        "completed_at": now_utc(),
                        "last_error": None,
                    },
                )
                await transition(s, FixRequest, req.id, from_={"remeasuring"}, to="report_ready")
                await email_service.queue(
                    s,
                    "report_ready",
                    user=await s.get(User, req.user_id),
                    params={"report_id": report_id},
                    dedupe_key=f"report_ready:{report_id}",
                )
                await s.commit()
        log.info("report_completed", report_id=report_id)
    except Exception as e:
        # 원문·값·외부 오류 본문은 저장하지 않는다.
        reason = (
            "banned_term"
            if isinstance(e, ValueError) and str(e) == "report_banned_term"
            else type(e).__name__
        )
        async with session_scope() as s:
            report = await s.get(ComparisonReport, report_id, with_for_update=True)
            if report is None or report.status != "generating":
                return
            report.last_error = reason
            if report.generation_attempts < GENERATE_ATTEMPTS:
                await _defer(s, report)
            else:
                await transition(s, ComparisonReport, report_id, from_={"generating"}, to="generation_failed")
            await s.commit()
        log.warning("report_generation_failed", report_id=report_id, error=reason)


def _storage_content(content: ReportContent) -> dict:
    """카카오 칸 값은 허용된 fix_logs에만 저장한다(00 4장, 10 3장)."""
    data = content.model_dump(mode="json", by_alias=True)
    for change in data["changes"]:
        if change["provider"] == "kakao":
            change["beforeValue"] = None
            change["appliedValue"] = None
    return data


async def _response(db: AsyncSession, report: ComparisonReport) -> ReportResponse:
    """권한 검사 뒤 카카오 칸 값만 fix_logs에서 읽어 응답한다. 보고서에 복제하지 않는다."""
    from collections import defaultdict, deque

    content = ReportContent.model_validate(report.content)
    values = defaultdict(deque)
    logs = await db.scalars(
        select(FixLog)
        .join(FixPlanItem, FixPlanItem.id == FixLog.fix_plan_item_id)
        .where(FixLog.fix_request_id == report.fix_request_id, FixLog.provider == "kakao")
        .order_by(FixPlanItem.order_no, FixLog.id)
    )
    for lg in logs:
        values[lg.field].append((lg.before_value, lg.applied_value))
    for change in content.changes:
        if change.provider == "kakao":
            before, applied = values[change.field].popleft() if values[change.field] else (None, None)
            change.before_value = report_builder.UNKNOWN_VALUE if before is None else before
            change.applied_value = report_builder.UNKNOWN_VALUE if applied is None else applied
    return ReportResponse(
        report_id=report.id,
        fix_request_id=report.fix_request_id,
        version=report.version,
        created_at=report.created_at,
        content=content,
    )


async def get(db: AsyncSession, user: User, report_id: int) -> ReportResponse:
    row = (
        await db.execute(
            select(ComparisonReport, Store)
            .join(Store, Store.id == ComparisonReport.store_id)
            .where(ComparisonReport.id == report_id)
        )
    ).first()
    if row is None or row[0].status != "completed" or (row[1].owner_id != user.id and user.role != "admin"):
        raise AppError("NOT_FOUND")
    return await _response(db, row[0])


async def current(db: AsyncSession, user: User) -> ReportResponse:
    report = await db.scalar(
        select(ComparisonReport)
        .join(Store, Store.id == ComparisonReport.store_id)
        .join(FixRequest, FixRequest.id == ComparisonReport.fix_request_id)
        .where(
            Store.owner_id == user.id,
            Store.status != "archived",
            FixRequest.status == "report_ready",
            ComparisonReport.status == "completed",
        )
        .order_by(ComparisonReport.id.desc())
        .limit(1)
    )
    if report is None:
        raise AppError("REPORT_NOT_READY")
    return await _response(db, report)


async def regenerate(db: AsyncSession, admin: User, request_id: int) -> dict:
    req = await db.get(FixRequest, request_id, with_for_update=True)
    if req is None:
        raise AppError("NOT_FOUND")
    latest = await db.scalar(
        select(ComparisonReport)
        .where(ComparisonReport.fix_request_id == request_id)
        .order_by(ComparisonReport.version.desc())
        .limit(1)
    )
    if req.status != "remeasuring" or latest is None or latest.status != "generation_failed":
        raise AppError("INVALID_STATE", {"currentStatus": latest.status if latest else "no_report"})
    report = await create(db, req, latest.after_run_id, interval_days=latest.interval_days or 0)
    audit.record(
        db, actor_id=admin.id, action="report.regenerate", target_type="fix_request", target_id=request_id
    )
    report_id = report.id
    await db.commit()
    return {"reportId": report_id}
