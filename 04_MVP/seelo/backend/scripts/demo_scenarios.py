"""S07 카드별 정지 상태 시드(17 2장). 실제 호출·작업 등록·기존 행 수정 없음."""

from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.annotate import annotate_openai
from seelo.domain.extraction import ANSWER_END, ANSWER_START
from seelo.domain.metrics import RecView, ResponseView, compute_run_metrics
from seelo.domain.normalize import normalize_name
from seelo.domain.questions import template_questions
from seelo.domain.report_builder import ChangeView, QuestionView, RunMetricsView, build_report
from seelo.integrations.fake_maps import DEMO_GOOGLE
from seelo.integrations.fake_web import DEMO_NAME, demo_answer, demo_extraction
from seelo.models.finding import Finding
from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import (
    AiExecution,
    AiResponse,
    MeasurementRun,
    Metric,
    Question,
    QuestionSet,
    Recommendation,
)
from seelo.models.report import ComparisonReport
from seelo.models.store import SourceSnapshot, Store, StoreSource
from seelo.models.user import AuthIdentity, FreeUsageLedger, User
from seelo.security.passwords import verify_password
from seelo.security.tokens import email_hmac
from seelo.timeutil import now_utc

REPEAT_COUNT = 10
FINDING_FIELDS = ("description", "website", "phone", "menu", "attributes")
AFTER_FIX = {"remeasure_waiting", "remeasuring", "remeasure_failed", "report_ready"}
NEEDS_PLAN = {"plan_preparing", "plan_needs_approval", "fixing", "fixing+revoked", *AFTER_FIX}
REQUEST_STATUS = {
    "fix_requested": "requested",
    "fix_rejected": "rejected",
    "connect_needed": "connecting",
    "plan_preparing": "connecting",
    "plan_needs_approval": "connecting",
    "fixing": "fixing",
    "fixing+revoked": "fixing",
    "remeasure_waiting": "remeasure_scheduled",
    "remeasuring": "remeasuring",
    "remeasure_failed": "remeasure_failed",
    "report_ready": "report_ready",
}


async def _questions(s: AsyncSession, store_id: int) -> tuple[QuestionSet, list[Question]]:
    qset = QuestionSet(
        store_id=store_id,
        version=1,
        region_ko="명동",
        region_en="Myeongdong",
        category="restaurant",
        features=["vegetarian"],
        generated_by="template",
    )
    s.add(qset)
    await s.flush()
    generated = template_questions(
        region_ko="명동",
        region_en="Myeongdong",
        category="restaurant",
        cuisine=("Korean restaurants", "한식당"),
        feature="vegetarian",
    )
    questions = [
        Question(question_set_id=qset.id, order_no=i, **q.model_dump()) for i, q in enumerate(generated, 1)
    ]
    s.add_all(questions)
    await s.flush()
    return qset, questions


async def _measurement(
    s: AsyncSession,
    store: Store,
    qset: QuestionSet,
    questions: list[Question],
    *,
    status="completed",
    kind="diagnosis",
    request_id=None,
    before=False,
) -> tuple[MeasurementRun, RunMetricsView]:
    now = now_utc()
    measured = now - timedelta(days=28) if before else now
    done = 23 if status == "running" else 60
    run = MeasurementRun(
        store_id=store.id,
        question_set_id=qset.id,
        kind=kind,
        fix_request_id=request_id,
        is_free=kind == "diagnosis",
        trigger="initial" if kind == "diagnosis" else "scheduler",
        status=status,
        stage="calling_ai" if status == "running" else "done",
        progress_done=done,
        progress_total=60,
        started_at=measured - timedelta(minutes=2),
        completed_at=measured if status == "completed" else None,
        failure_reason="failure_rate" if status == "failed" else None,
        failure_rate=0.5 if status == "failed" else 0,
    )
    s.add(run)
    await s.flush()
    executions = []
    for provider in ("openai", "gemini"):
        for q in questions:
            for repeat in range(1, REPEAT_COUNT + 1):
                state = "succeeded" if len(executions) < done else "pending"
                if status == "failed" and provider == "openai":
                    state = "failed"
                executions.append(
                    AiExecution(
                        run_id=run.id,
                        question_id=q.id,
                        provider=provider,
                        repeat_no=repeat,
                        model_id=f"demo-{provider}",
                        status=state,
                        attempt=int(state != "pending"),
                        error_code="demo_outage" if state == "failed" else None,
                        finished_at=measured if state != "pending" else None,
                    )
                )
    s.add_all(executions)
    await s.flush()
    views = []
    responses = []
    extracted = []
    for ex in executions:
        if ex.status != "succeeded":
            continue
        sample_no = 0 if kind == "remeasure" and ex.repeat_no in {1, 2} else ex.repeat_no
        raw, citations = demo_answer("", sample_no)
        annotated, sources = annotate_openai(raw, citations)
        result = demo_extraction(f"{ANSWER_START}{annotated}{ANSWER_END}")
        response = AiResponse(
            execution_id=ex.id,
            raw_text=raw,
            raw_json={"demo": True},
            annotated_text=annotated,
            source_urls=sources,
            extraction_status="succeeded",
            extraction_json=result.model_dump(),
            target_claims=[],
        )
        responses.append(response)
        extracted.append((ex, response, result, sources))
    s.add_all(responses)
    await s.flush()
    for ex, response, result, sources in extracted:
        recs = []
        for rec in result.recommendations:
            urls = [u for u in sources if u["n"] in rec.source_numbers]
            target = normalize_name(rec.name) == normalize_name(DEMO_NAME)
            s.add(
                Recommendation(
                    response_id=response.id,
                    name=rec.name,
                    normalized_name=normalize_name(rec.name),
                    rank=rec.order,
                    source_urls=urls,
                    mentioned_attributes=[],
                    is_target=target,
                )
            )
            recs.append(
                RecView(
                    normalize_name(rec.name), rec.name, rec.order, target, [u["domain"] for u in urls], []
                )
            )
        views.append(
            ResponseView(
                response.id,
                ex.provider,
                ex.question_id,
                True,
                recs,
                list(dict.fromkeys(u["domain"] for u in sources)),
                [u["url"] for u in sources],
            )
        )
    metrics = compute_run_metrics(
        views, question_ids=[q.id for q in questions], failed=30 if status == "failed" else 0, total=60
    )
    if status == "completed":
        s.add_all(Metric(run_id=run.id, **asdict(row)) for row in metrics.rows)
    return run, RunMetricsView(
        metrics.rows, views, measured, qset.id, REPEAT_COUNT, {p: f"demo-{p}" for p in ("openai", "gemini")}
    )


async def _findings(s: AsyncSession, run_id: int) -> list[Finding]:
    rows = [
        Finding(
            run_id=run_id,
            stage="diagnosis",
            category="map_missing",
            title_key=f"map_missing.{field}",
            provider="google",
            field=field,
            priority=i,
            competitor_count=5,
            question_count=3,
            evidence={"demo": True, "insufficient": True},
        )
        for i, field in enumerate(FINDING_FIELDS, 1)
    ]
    s.add_all(rows)
    await s.flush()
    return rows


async def _plan(
    s: AsyncSession, req: FixRequest, owner: User, card: str, findings: list[Finding]
) -> FixLog | None:
    now = now_utc()
    approved = card not in {"plan_preparing", "plan_needs_approval"}
    plan = FixPlan(
        fix_request_id=req.id,
        provider="google",
        base_run_id=req.base_run_id,
        version=1,
        status="approved"
        if approved
        else ("generating" if card == "plan_preparing" else "awaiting_approval"),
        approved_at=now - timedelta(days=14) if approved else None,
        approved_by=owner.id if approved else None,
    )
    s.add(plan)
    await s.flush()
    if card == "plan_preparing":
        return None
    # 확인 필요·민감 칸은 계획서 17 2장의 화면 예시다. 사실처럼 자동 승인하지 않는다.
    items = [
        FixPlanItem(
            fix_plan_id=plan.id,
            order_no=1,
            field="description",
            current_value="이전 소개",
            proposed_value="Korean dishes in Myeongdong.\n명동에서 한식을 준비해요.",
            approved_value="Korean dishes in Myeongdong.\n명동에서 한식을 준비해요." if approved else None,
            reason="시연용 정비안",
            finding_ids=[findings[0].id],
            evidence={"demo": True},
        )
    ]
    if not approved:
        items += [
            FixPlanItem(
                fix_plan_id=plan.id,
                order_no=4,
                field="phone",
                proposed_value="[ ]",
                needs_owner_input=True,
                finding_ids=[findings[2].id],
            ),
            FixPlanItem(
                fix_plan_id=plan.id,
                order_no=5,
                field="menu",
                sensitive=True,
                proposed_value=[
                    {
                        "name": "시연 메뉴",
                        "nameEn": "Demo dish",
                        "price": 11000,
                        "description": "알레르기 정보는 사장님 확인이 필요해요.",
                    }
                ],
                finding_ids=[findings[3].id],
            ),
        ]
    s.add_all(items)
    await s.flush()
    if not approved:
        return None
    status = (
        "disconnected"
        if card == "fixing+revoked"
        else ("manual_done" if card in AFTER_FIX else "manual_required")
    )
    handler_id = (
        await s.scalar(select(User.id).where(User.email == "admin@seelo.test", User.role == "admin"))
        if status == "manual_done"
        else None
    )
    lg = FixLog(
        fix_request_id=req.id,
        fix_plan_item_id=items[0].id,
        provider="google",
        field="description",
        method="manual",
        before_value="이전 소개",
        applied_value=items[0].approved_value,
        status=status,
        manual_reason="automation_disabled" if status == "manual_required" else None,
        handled_by=handler_id,
        handled_at=req.fix_completed_at if status == "manual_done" else None,
        remeasure_match="unknown" if card == "report_ready" else None,
    )
    s.add(lg)
    await s.flush()
    return lg


async def _changed_store(s: AsyncSession, owner: User, current: Store) -> None:
    """이전 가게에서 무료 진단을 썼고 새 가게는 수집만 끝난 상태(17 2장)."""
    now = now_utc()
    archived = Store(
        owner_id=owner.id,
        name="이전 시연 가게",
        category="restaurant",
        status="archived",
        archived_at=now - timedelta(days=1),
        input_provider="google",
        input_url=current.input_url,
    )
    s.add(archived)
    await s.flush()
    qset, questions = await _questions(s, archived.id)
    await _measurement(s, archived, qset, questions)
    await s.execute(
        insert(FreeUsageLedger).values(email_hash=email_hmac(owner.email)).on_conflict_do_nothing()
    )


async def _scenario(s: AsyncSession, owner: User, card: str) -> None:
    now = now_utc()
    state = {
        "measuring": "measuring",
        "measure_failed": "measure_failed",
        "free_used_store_changed": "collected",
    }.get(card, "diagnosed")
    store = Store(
        owner_id=owner.id,
        name=DEMO_NAME,
        category="restaurant",
        status=state,
        input_provider="google",
        input_url="https://www.google.com/maps/place/demo",
    )
    s.add(store)
    await s.flush()
    sources = [
        StoreSource(store_id=store.id, provider=p, external_id=ext, url=url, match_status="found")
        for p, ext, url in (
            ("google", "demo-place", "https://www.google.com/maps/place/demo"),
            ("kakao", "1", "https://place.map.kakao.com/1"),
        )
    ]
    s.add_all(sources)
    await s.flush()
    if card == "free_used_store_changed":
        await _changed_store(s, owner, store)
        return
    qset, questions = await _questions(s, store.id)
    status = {"measuring": "running", "measure_failed": "failed"}.get(card, "completed")
    base, before = await _measurement(s, store, qset, questions, status=status, before=card in AFTER_FIX)
    s.add(
        SourceSnapshot(
            store_id=store.id,
            source_id=sources[0].id,
            run_id=base.id,
            provider="google",
            status="ok",
            payload={"ko": DEMO_GOOGLE, "en": None, "photoCount": 0},
            expires_at=now + timedelta(days=30),
        )
    )
    if status == "completed":
        await s.execute(
            insert(FreeUsageLedger).values(email_hash=email_hmac(owner.email)).on_conflict_do_nothing()
        )
    findings = await _findings(s, base.id) if status == "completed" else []
    if card not in REQUEST_STATUS:
        return
    req = FixRequest(
        user_id=owner.id,
        store_id=store.id,
        base_run_id=base.id,
        status=REQUEST_STATUS[card],
        reject_reason="시연 범위 밖의 가게예요." if card == "fix_rejected" else None,
        fix_completed_at=(now - timedelta(days=2 if card == "remeasure_waiting" else 14))
        if card in AFTER_FIX
        else None,
    )
    s.add(req)
    await s.flush()
    for provider in ("google", "kakao"):
        connected = card in NEEDS_PLAN and provider == "google"
        s.add(
            MapConnection(
                fix_request_id=req.id,
                provider=provider,
                status="revoked"
                if card == "fixing+revoked" and connected
                else ("connected" if connected else "not_connected"),
                connected_at=now - timedelta(days=15) if connected else None,
                revoked_at=now if card == "fixing+revoked" and connected else None,
                external_ref=f"demo-{store.id}" if connected else None,
            )
        )
    lg = await _plan(s, req, owner, card, findings) if card in NEEDS_PLAN else None
    if card not in AFTER_FIX:
        return
    after = None
    if card != "remeasure_waiting":
        after_status = {"remeasuring": "running", "remeasure_failed": "failed", "report_ready": "completed"}[
            card
        ]
        after, after_view = await _measurement(
            s, store, qset, questions, status=after_status, kind="remeasure", request_id=req.id
        )
    s.add(
        RemeasureSchedule(
            fix_request_id=req.id,
            due_at=req.fix_completed_at + timedelta(days=14),
            status="scheduled" if after is None else "started",
            triggered_by="scheduler",
            run_id=after.id if after else None,
            started_at=now if after else None,
        )
    )
    if card == "report_ready":
        from seelo.services.report_service import _storage_content

        content = build_report(
            before=before,
            after=after_view,
            questions=[QuestionView(q.id, q.order_no, q.lang, q.text, q.text_ko) for q in questions],
            changes=[
                ChangeView(
                    provider="google",
                    field="description",
                    field_label="가게 소개",
                    before_value=lg.before_value,
                    applied_value=lg.applied_value,
                    method=lg.method,
                    status=lg.status,
                    verified_at=None,
                    remeasure_match="unknown",
                )
            ],
            fix_completed_at=req.fix_completed_at,
            interval_days=14,
            early=False,
        )
        s.add(
            ComparisonReport(
                fix_request_id=req.id,
                store_id=store.id,
                base_run_id=base.id,
                after_run_id=after.id,
                status="completed",
                version=1,
                interval_days=14,
                generation_attempts=1,
                content=_storage_content(content),
                completed_at=now,
            )
        )


async def seed_scenarios() -> dict[str, int]:
    """기존 가게가 있는 계정은 건너뛴다. 사용자 행 잠금으로 동시 실행을 막는다(17 2장)."""
    from scripts.seed_demo import ACCOUNTS, DEMO_PASSWORD

    settings = get_settings()
    if settings.app_env == "prod" or not settings.fake_externals:
        raise ValueError("demo_scenarios_require_fake_non_production")
    result = {"created": 0, "skipped": 0, "protected": 0}
    for email, role, card in ACCOUNTS:
        if role == "admin" or card == "no_store":
            continue
        async with session_scope() as s:
            owner = await s.scalar(select(User).where(User.email == email).with_for_update())
            if owner is None or owner.role != role or not verify_password(owner.password_hash, DEMO_PASSWORD):
                result["protected"] += 1
                continue
            identity = await s.scalar(
                select(AuthIdentity.id).where(
                    AuthIdentity.user_id == owner.id, AuthIdentity.provider == "email"
                )
            )
            if identity is None or await s.scalar(
                select(Store.id).where(Store.owner_id == owner.id).limit(1)
            ):
                result["skipped"] += 1
                continue
            await _scenario(s, owner, card)
            await s.commit()
            result["created"] += 1
    return result
