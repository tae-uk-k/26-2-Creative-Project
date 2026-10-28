"""정비안(09 6·7장, 04 7.3, 03 E13·E14·E15·E23, W-09-2·4).

- readCurrentValues(E13): 칸 사전의 그 지도 칸을 모두 읽어 `fix_plan_items.current_value`로.
  `AUTO_FIX_ENABLED=false`이거나 카카오이고 `KAKAO_FIX_ENABLED=false`면 읽지 않고 모두 null
  (그때 08 6.5 정비안 단계 판정은 건너뜀).
  읽지 않을 때는 브라우저가 필요 없으므로 기본 워커(plan 큐)에서 돈다. 읽을 때만 fix 큐(lock fix:{provider}).
- generateFixPlan(E14): 정비안 단계 판정 → 칸별 바꿀 값(사실만) → 글(LLM) → 사실 검사 → 글자 수 → 저장.
  외부 호출(LLM) 동안 트랜잭션을 열어 두지 않고, 저장은 한 트랜잭션에서 한다. 실패 2번이면 generation_failed.
- 승인(E15): 칸별 검사(확인 필요·민감 정보·형식) 뒤 한 트랜잭션에서 승인·신청 전이·fix_logs·작업 등록.
- 카카오 지금 값은 `current_value`로만 저장한다(evidence·LLM 입력은 사실 목록의 kakao_current로만).
"""

import asyncio
from dataclasses import replace
from typing import Any

import structlog
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain import fix_plan as fp
from seelo.domain.field_dictionary import (
    FieldSpec,
    field_label,
    is_incomplete,
    same_value,
    spec,
    specs,
    validate_value,
)
from seelo.domain.findings_rules import FindingDraft, FindingInputs, judge_plan, prioritize, title_for
from seelo.domain.labels import CATEGORY_LABEL, FIX_LOG_STATUS_LABEL
from seelo.domain.metrics import competitor_position
from seelo.domain.states import (
    ConnectionStatus,
    FixLogStatus,
    FixPlanStatus,
    FixRequestStatus,
    MatchStatus,
    transition,
)
from seelo.errors import AppError
from seelo.integrations import Clients, get_clients
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.integrations.llm import LlmError
from seelo.models.finding import Finding
from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Question, Recommendation
from seelo.models.store import SourceSnapshot, Store, StoreSource, WebEvidence
from seelo.models.user import User
from seelo.schemas.fix import (
    ApproveRequest,
    ApproveResponse,
    EvidenceAnswer,
    EvidenceQuestion,
    ItemConstraints,
    ItemResult,
    OwnerOnlyField,
    PlanDetail,
    PlanEvidence,
    PlanFinding,
    PlanItem,
    PlanList,
    PlanListItem,
    PlanSummary,
    Position,
)
from seelo.schemas.llm import PlanTextsOut
from seelo.services import audit, email_service, fix_apply_service, jobs
from seelo.services.collect_service import latest_snapshot
from seelo.services.diagnosis_service import metric_rows, provider_rates
from seelo.services.eligibility import current_store
from seelo.services.finalize_service import load_questions, response_views
from seelo.timeutil import now_utc

log = structlog.get_logger()

READ_ATTEMPTS = 2  # 일시 오류 1번 다시(06 4장)
GENERATE_ATTEMPTS = 2  # 09 6.3 9번
TEXT_TIMEOUT_S = 60.0
WRITABLE_REQUEST = {
    FixRequestStatus.CONNECTING,
    FixRequestStatus.FIXING,
    FixRequestStatus.REMEASURE_SCHEDULED,
}
HIDDEN_REQUEST = {FixRequestStatus.REQUESTED, FixRequestStatus.REJECTED}
PROVIDERS = ("google", "kakao")


class PlanGenerationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def reads_current_values(provider: str) -> bool:
    """관리 화면을 실제로 읽는가(아니면 current_value는 모두 null)."""
    s = get_settings()
    return s.auto_fix_enabled and (provider == "google" or s.kakao_fix_enabled)


async def defer_read(s: AsyncSession, plan_id: int, provider: str, *, store_id: int, request_id: int) -> None:
    """readCurrentValues 등록. 읽지 않는 모드는 브라우저가 필요 없어 plan 큐(기본 워커)."""
    from seelo.worker.tasks_fix import read_current_values

    browser = reads_current_values(provider)
    await jobs.defer(
        s,
        read_current_values,
        args={"fix_plan_id": plan_id},
        links=jobs.JobLinks(store_id=store_id, fix_request_id=request_id),
        queueing_lock=f"read:{plan_id}",
        lock=f"fix:{provider}" if browser else None,
        queue="fix" if browser else "plan",
    )


async def _defer_generate(s: AsyncSession, plan_id: int, *, store_id: int, request_id: int) -> None:
    from seelo.worker.tasks_plan import generate_fix_plan

    await jobs.defer(
        s,
        generate_fix_plan,
        args={"fix_plan_id": plan_id},
        links=jobs.JobLinks(store_id=store_id, fix_request_id=request_id),
        queueing_lock=f"plan:{plan_id}",
    )


async def _fail(plan_id: int, reason: str) -> None:
    async with session_scope() as s:
        await transition(
            s,
            FixPlan,
            plan_id,
            from_={FixPlanStatus.GENERATING},
            to=FixPlanStatus.GENERATION_FAILED,
            values={"last_error": reason},
        )
        await s.commit()
    log.warning("fix_plan_failed", plan_id=plan_id, reason=reason)


# --- E13 지금 값 읽기 ------------------------------------------------------------------------


async def read_current_values(plan_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        plan = await s.get(FixPlan, plan_id)
        req = await s.get(FixRequest, plan.fix_request_id) if plan else None
        conn = (
            await s.scalar(
                select(MapConnection).where(
                    MapConnection.fix_request_id == req.id, MapConnection.provider == plan.provider
                )
            )
            if req
            else None
        )
        if (
            plan is None
            or plan.status != FixPlanStatus.GENERATING
            or conn is None
            or conn.status != "connected"
        ):
            log.info("read_current_values_skip", plan_id=plan_id)
            return
        provider, request_id, external_ref = plan.provider, req.id, conn.external_ref
        from seelo.services.connection_service import store_ref

        ref = await store_ref(s, req.store_id)
        store_id = req.store_id
        await s.commit()

    fields = [sp.key for sp in specs(provider)]
    values: dict[str, Any] = dict.fromkeys(fields)
    if reads_current_values(provider):
        for attempt in range(1, READ_ATTEMPTS + 1):
            try:
                async with clients.map_admin(provider) as admin:
                    await admin.open_store(ref, external_ref)
                    got = await admin.read_fields(fields)
                values = {f: (got[f].value if f in got else None) for f in fields}
                break
            except AutomationBlocked:
                await _fail(plan_id, "automation_blocked")
                return
            except AttentionNeeded as e:  # 인증 필요 등: 관리자가 연결 상태를 다시 확인해야 함
                await _fail(plan_id, e.reason)
                return
            except StoreNotVisible:
                from seelo.services import connection_service

                async with session_scope() as s:
                    await connection_service.revoke(s, request_id, provider)  # E18
                    await s.commit()
                await _fail(plan_id, "store_not_visible")
                return
            except TransientAutomationError:
                if attempt == READ_ATTEMPTS:
                    await _fail(plan_id, "read_failed")
                    return

    async with session_scope() as s:
        plan = await s.get(FixPlan, plan_id, with_for_update=True)
        if plan is None or plan.status != FixPlanStatus.GENERATING:
            return
        for sp in specs(provider):
            stmt = insert(FixPlanItem).values(
                fix_plan_id=plan_id, field=sp.key, order_no=sp.order, current_value=values.get(sp.key)
            )
            await s.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_plan_item_field", set_={"current_value": stmt.excluded.current_value}
                )
            )
        await _defer_generate(s, plan_id, store_id=store_id, request_id=request_id)
        await s.commit()
    log.info("current_values_read", plan_id=plan_id, provider=provider, read=reads_current_values(provider))


# --- E14 정비안 만들기 -----------------------------------------------------------------------


async def _diagnosis_refs(s: AsyncSession, run_id: int | None, provider: str) -> list[fp.FindingRef]:
    if run_id is None:
        return []
    rows = await s.scalars(
        select(Finding).where(
            Finding.run_id == run_id, Finding.stage == "diagnosis", Finding.provider == provider
        )
    )
    return [
        fp.FindingRef(f.id, f.provider, f.field, f.category, f.title_key, f.priority, f.evidence or {})
        for f in rows
    ]


async def _inputs(s: AsyncSession, plan: FixPlan) -> tuple[fp.PlanInputs, FindingInputs]:
    req = await s.get(FixRequest, plan.fix_request_id)
    store = await s.get(Store, req.store_id)
    base = await s.get(MeasurementRun, plan.base_run_id) if plan.base_run_id else None
    run_id = base.id if base else None
    items = (await s.scalars(select(FixPlanItem).where(FixPlanItem.fix_plan_id == plan.id))).all()
    current = {i.field: i.current_value for i in items}
    other = "kakao" if plan.provider == "google" else "google"
    other_plan = await s.scalar(
        select(FixPlan)
        .where(FixPlan.fix_request_id == req.id, FixPlan.provider == other)
        .order_by(FixPlan.version.desc())
        .limit(1)
    )
    other_current = (
        {
            i.field: i.current_value
            for i in await s.scalars(select(FixPlanItem).where(FixPlanItem.fix_plan_id == other_plan.id))
        }
        if other_plan
        else {}
    )
    google = await latest_snapshot(s, store.id, run_id, "google") if run_id else None
    website = await latest_snapshot(s, store.id, run_id, "website") if run_id else None
    insta_src = await s.scalar(
        select(StoreSource).where(StoreSource.store_id == store.id, StoreSource.provider == "instagram")
    )
    insta = await s.scalar(
        select(SourceSnapshot.payload)
        .where(
            SourceSnapshot.store_id == store.id,
            SourceSnapshot.provider == "instagram",
            SourceSnapshot.status == "ok",
        )
        .order_by(SourceSnapshot.collected_at.desc())
        .limit(1)
    )
    web_sites = (
        list((await s.scalars(select(WebEvidence.fields).where(WebEvidence.run_id == run_id))).all())
        if run_id
        else []
    )
    question_ids, features, region = await load_questions(s, base.question_set_id if base else None)
    views = await response_views(s, run_id) if run_id else []
    comps = sorted(
        {r.subject_name for r in await metric_rows(s, run_id) if r.subject_type == "competitor"}
        if run_id
        else set()
    )
    findings = await _diagnosis_refs(s, run_id, plan.provider)
    ko = (google or {}).get("ko")
    plan_in = fp.PlanInputs(
        provider=plan.provider,
        category=store.category,
        region_ko=region,
        current=current,
        findings=findings,
        website=(website or {}).get("extract"),
        website_url=(website or {}).get("url"),
        google=ko,
        other_current=other_current,
        instagram_url=insta_src.url if insta_src and insta_src.match_status == MatchStatus.FOUND else None,
        instagram_bio=(insta or {}).get("biography"),
        web_sites=web_sites,
    )
    rule_in = FindingInputs(
        category=store.category,
        google_found=True,
        kakao_found=True,
        google=ko,
        kakao_basic=None,
        naver_basic=None,
        website=(website or {}).get("extract"),
        web_sites=web_sites,
        question_ids=question_ids,
        question_features=features,
        responses=views,
        claims=[],
        competitors=comps,
        competitor_facts={},
        plan_values=current if any(v is not None for v in current.values()) else None,
    )
    return plan_in, rule_in


async def _texts(clients: Clients, prompt: str) -> PlanTextsOut:
    model = get_settings().openai_plan_model
    try:
        async with asyncio.timeout(TEXT_TIMEOUT_S):
            res = await clients.openai.structured(prompt, PlanTextsOut, model=model)
    except TimeoutError as e:
        raise PlanGenerationError("timeout") from e
    except LlmError as e:
        raise PlanGenerationError(e.reason) from e
    return res.parsed  # type: ignore[return-value]


async def generate(plan_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        plan = await s.get(FixPlan, plan_id, with_for_update=True)
        if plan is None or plan.status != FixPlanStatus.GENERATING:
            log.info("generate_fix_plan_skip", plan_id=plan_id)
            return
        plan.generation_attempts += 1
        attempts, provider = plan.generation_attempts, plan.provider
        req = await s.get(FixRequest, plan.fix_request_id)
        store_id, request_id = req.store_id, req.id
        await s.commit()
    try:
        async with session_scope() as s:
            plan = await s.get(FixPlan, plan_id)
            plan_in, rule_in = await _inputs(s, plan)
            await s.commit()
        drafts_plan = _plan_findings(plan_in, rule_in)
        plan_in = replace(
            plan_in, findings=plan_in.findings + [_ref(i, d) for i, d in enumerate(drafts_plan)]
        )
        facts = fp.build_facts(plan_in)
        sp = {x.key: x for x in specs(provider)}
        drafts = fp.draft_items(plan_in, facts, list(sp.values()))
        if any(fp.needs_texts(provider, drafts).values()):
            texts = await _texts(clients, fp.plan_prompt(plan_in, facts, drafts, sp))
            fp.apply_texts(plan_in, facts, drafts, texts)
            long_fields = fp.over_limit(drafts, sp)
            if long_fields:  # 09 6.7 1번: 그 칸만 짧게 1번 더
                again = await _texts(clients, fp.plan_prompt(plan_in, facts, drafts, sp, shorter=long_fields))
                fp.apply_texts(plan_in, facts, drafts, again, only=set(long_fields))
            fp.fit_all(drafts, sp)
        for d in drafts:
            if sp[d.field].type in ("text", "tags") and not d.proposed:
                d.needs_owner_input = True  # LLM이 글을 못 만들었거나 사실 검사로 모두 지워짐
        await _save(
            plan_id, provider, plan_in, drafts_plan, drafts, facts, store_id=store_id, request_id=request_id
        )
    except PlanGenerationError as e:
        if attempts < GENERATE_ATTEMPTS:
            async with session_scope() as s:
                await _defer_generate(s, plan_id, store_id=store_id, request_id=request_id)
                await s.commit()
            log.warning("fix_plan_retry", plan_id=plan_id, reason=e.reason, attempts=attempts)
        else:
            await _fail(plan_id, e.reason)


def _plan_findings(plan_in: fp.PlanInputs, rule_in: FindingInputs) -> list[FindingDraft]:
    """08 6.5 정비안 단계 판정. 순서는 진단 단계 finding 뒤에 이어 붙인다."""
    existing = [
        FindingDraft("diagnosis", f.category, f.title_key, f.provider, f.field) for f in plan_in.findings
    ]
    drafts = prioritize(
        judge_plan(rule_in, plan_in.provider, existing), replace(rule_in, competitor_facts={})
    )
    offset = max((f.priority for f in plan_in.findings), default=0)
    for d in drafts:
        d.priority += offset
    return drafts


def _ref(i: int, d: FindingDraft) -> fp.FindingRef:
    """저장 전 정비안 단계 finding은 음수 임시 id(-1, -2, ...). 저장 뒤 실제 id로 바꾼다."""
    return fp.FindingRef(-(i + 1), d.provider, d.field, d.category, d.title_key, d.priority, d.evidence)


async def _save(
    plan_id: int,
    provider: str,
    plan_in: fp.PlanInputs,
    drafts_plan: list[FindingDraft],
    drafts: list[fp.ItemDraft],
    facts: list[Any],
    *,
    store_id: int,
    request_id: int,
) -> None:
    async with session_scope() as s:
        plan = await s.get(FixPlan, plan_id, with_for_update=True)
        if plan is None or plan.status != FixPlanStatus.GENERATING:
            return
        await s.execute(delete(Finding).where(Finding.fix_plan_id == plan_id, Finding.stage == "plan"))
        real: dict[int, int] = {}
        for i, d in enumerate(drafts_plan):
            row = Finding(
                run_id=plan.base_run_id,
                fix_plan_id=plan_id,
                stage="plan",
                category=d.category,
                title_key=d.title_key,
                provider=d.provider,
                field=d.field,
                competitor_count=d.competitor_count,
                question_count=d.question_count,
                priority=d.priority,
                evidence=d.evidence,
            )
            s.add(row)
            await s.flush()
            real[-(i + 1)] = row.id
        rows = {
            i.field: i for i in await s.scalars(select(FixPlanItem).where(FixPlanItem.fix_plan_id == plan_id))
        }
        sp = {x.key: x for x in specs(provider)}

        def unchanged(d: fp.ItemDraft) -> bool:
            current = rows[d.field].current_value if d.field in rows else None
            return same_value(sp[d.field].type, current, d.proposed) and not d.needs_owner_input

        kept = [d for d in drafts if not d.delete and not unchanged(d)]
        kept.sort(key=lambda d: d.order_key)
        keep_fields = {d.field for d in kept}
        await s.execute(
            delete(FixPlanItem).where(
                FixPlanItem.fix_plan_id == plan_id, FixPlanItem.field.not_in(keep_fields)
            )
        )
        for order, d in enumerate(kept, 1):
            values = {
                "order_no": order,
                "proposed_value": d.proposed,
                "reason": d.reason,
                "finding_ids": [real.get(i, i) for i in d.finding_ids],
                "evidence": {"factIds": d.fact_ids, "responseIds": d.response_ids},
                "needs_owner_input": d.needs_owner_input,
                "sensitive": d.sensitive,
            }
            if d.field in rows:
                await s.execute(
                    update(FixPlanItem).where(FixPlanItem.id == rows[d.field].id).values(**values)
                )
            else:
                s.add(FixPlanItem(fix_plan_id=plan_id, field=d.field, current_value=None, **values))
        await transition(
            s,
            FixPlan,
            plan_id,
            from_={FixPlanStatus.GENERATING},
            to=FixPlanStatus.AWAITING_APPROVAL,
            values={"last_error": None},
        )
        owner_id = await s.scalar(select(FixRequest.user_id).where(FixRequest.id == request_id))
        await email_service.queue(
            s,
            "fix_plan_ready",
            user=await s.get(User, owner_id),
            params={"plan_id": plan_id, "provider": provider, "item_count": len(kept)},
            dedupe_key=f"fix_plan_ready:{plan_id}",
        )
        await s.commit()
    log.info(
        "fix_plan_ready", plan_id=plan_id, provider=provider, items=len(kept), plan_findings=len(drafts_plan)
    )


# --- S13 조회 -----------------------------------------------------------------------------


async def _owned(db: AsyncSession, user: User, plan_id: int) -> tuple[FixPlan, FixRequest, Store]:
    """소유(또는 관리자), 승인된 신청, 그 지도가 한 번이라도 연결됐을 때만. 아니면 404(04 7.3)."""
    plan = await db.get(FixPlan, plan_id)
    req = await db.get(FixRequest, plan.fix_request_id) if plan else None
    store = await db.get(Store, req.store_id) if req else None
    if plan is None or store is None or (store.owner_id != user.id and user.role != "admin"):
        raise AppError("NOT_FOUND")
    connected_once = await db.scalar(
        select(
            exists().where(
                MapConnection.fix_request_id == req.id,
                MapConnection.provider == plan.provider,
                MapConnection.connected_at.is_not(None),
            )
        )
    )
    if req.status in HIDDEN_REQUEST or not connected_once:
        raise AppError("NOT_FOUND")
    return plan, req, store


async def _latest_plans(db: AsyncSession, request_id: int) -> dict[str, FixPlan]:
    out: dict[str, FixPlan] = {}
    for p in await db.scalars(select(FixPlan).where(FixPlan.fix_request_id == request_id)):
        if p.provider not in out or p.version > out[p.provider].version:
            out[p.provider] = p
    return out


async def list_plans(db: AsyncSession, user: User) -> PlanList:
    store = await current_store(db, user.id)
    req = (
        await db.scalar(
            select(FixRequest).where(FixRequest.store_id == store.id).order_by(FixRequest.id.desc()).limit(1)
        )
        if store
        else None
    )
    if req is None or req.status in HIDDEN_REQUEST:
        return PlanList(plans=[])
    plans = await _latest_plans(db, req.id)
    return PlanList(
        plans=[
            PlanListItem(plan_id=p.id, provider=p.provider, status=p.status, version=p.version)  # type: ignore[arg-type]
            for p in sorted(plans.values(), key=lambda p: PROVIDERS.index(p.provider))
        ]
    )


def _constraints(sp: FieldSpec | None) -> ItemConstraints:
    if sp is None:
        return ItemConstraints(type="text")
    return ItemConstraints(type=sp.type, max_length=sp.max_length, max_items=sp.max_items)  # type: ignore[arg-type]


async def detail(db: AsyncSession, user: User, plan_id: int) -> PlanDetail:
    plan, req, store = await _owned(db, user, plan_id)
    rows = await metric_rows(db, plan.base_run_id) if plan.base_run_id else []
    position, total = competitor_position(rows) if rows else (0, 0)
    latest = await _latest_plans(db, req.id)
    counts = {
        p: int(
            await db.scalar(
                select(func.count()).select_from(FixPlanItem).where(FixPlanItem.fix_plan_id == latest[p].id)
            )
            or 0
        )
        if p in latest
        else 0
        for p in PROVIDERS
    }
    conns = {
        c.provider: c.status
        for c in await db.scalars(select(MapConnection).where(MapConnection.fix_request_id == req.id))
    }
    refs = await _diagnosis_refs(db, plan.base_run_id, plan.provider)
    ready = plan.status in (FixPlanStatus.AWAITING_APPROVAL, FixPlanStatus.APPROVED)
    items_rows = (
        list(
            (
                await db.scalars(
                    select(FixPlanItem)
                    .where(FixPlanItem.fix_plan_id == plan.id)
                    .order_by(FixPlanItem.order_no)
                )
            ).all()
        )
        if ready
        else []
    )
    logs = {
        lg.fix_plan_item_id: lg
        for lg in await db.scalars(
            select(FixLog).where(FixLog.fix_plan_item_id.in_([i.id for i in items_rows]))
        )
    }
    plan_findings = (
        list(
            (
                await db.scalars(
                    select(Finding).where(Finding.fix_plan_id == plan.id, Finding.stage == "plan")
                )
            ).all()
        )
        if ready
        else []
    )
    diag_rows = (
        list((await db.scalars(select(Finding).where(Finding.id.in_([r.id for r in refs])))).all())
        if ready
        else []
    )
    item_of = {fid: i.id for i in items_rows for fid in i.finding_ids}
    findings = [
        PlanFinding(
            finding_id=f.id,
            category=f.category,
            category_label=CATEGORY_LABEL.get(f.category, f.category),
            title=title_for(f.title_key, f.provider, f.evidence or {}),
            provider=f.provider,  # type: ignore[arg-type]
            field=f.field,
            question_count=f.question_count,
            competitor_count=f.competitor_count,
            priority=f.priority,
            related_response_ids=list((f.evidence or {}).get("responseIds", [])),
            item_id=item_of.get(f.id),
        )
        for f in sorted(diag_rows + plan_findings, key=lambda f: (f.priority, f.id))
    ]
    items = []
    for i in items_rows:
        lg = logs.get(i.id)
        items.append(
            PlanItem(
                item_id=i.id,
                order_no=i.order_no,
                field=i.field,
                field_label=field_label(plan.provider, i.field),
                current_value=i.current_value,
                proposed_value=i.proposed_value,
                approved_value=i.approved_value,
                reason=i.reason,
                finding_ids=list(i.finding_ids),
                needs_owner_input=i.needs_owner_input,
                sensitive=i.sensitive,
                owner_confirmed=i.owner_confirmed,
                owner_edited=i.owner_edited,
                excluded=i.excluded,
                constraints=_constraints(spec(plan.provider, i.field)),
                result=ItemResult(
                    status=lg.status,  # type: ignore[arg-type]
                    status_label=FIX_LOG_STATUS_LABEL.get(lg.status, lg.status),
                    applied_at=lg.applied_at,
                    verified_at=lg.verified_at,
                )
                if lg
                else None,
            )
        )
    read_only = (
        user.role == "admin"
        or store.owner_id != user.id
        or plan.status != FixPlanStatus.AWAITING_APPROVAL
        or req.status not in WRITABLE_REQUEST
    )
    return PlanDetail(
        plan_id=plan.id,
        provider=plan.provider,  # type: ignore[arg-type]
        status=plan.status,
        version=plan.version,
        created_at=plan.created_at,
        approved_at=plan.approved_at,
        read_only=read_only,
        summary=PlanSummary(
            providers=provider_rates(rows),
            competitor_position=Position(position=position, total=total),
            item_counts=counts,  # type: ignore[arg-type]
            connections={p: conns.get(p, ConnectionStatus.NOT_CONNECTED) for p in PROVIDERS},  # type: ignore[misc]
        ),
        findings=findings,
        items=items,
        owner_only_fields=[
            OwnerOnlyField(field=f, guide=g) for f, g in fp.owner_only_fields(plan.provider, refs)
        ],  # type: ignore[arg-type]
        map_not_found=fp.map_not_found(plan.provider, refs),
    )


async def evidence(db: AsyncSession, user: User, plan_id: int) -> PlanEvidence:
    """기준 측정의 질문별 AI 답변 원문.

    강조 이름: 우리 가게 이름 후보(입력·Google·우리 가게로 판정된 추천)와 주변 가게.
    """
    plan, _, store = await _owned(db, user, plan_id)
    if plan.base_run_id is None:
        return PlanEvidence(questions=[])
    base = await db.get(MeasurementRun, plan.base_run_id)
    google = (await latest_snapshot(db, store.id, base.id, "google") or {}).get("ko") or {}
    targets = [store.name, (google.get("displayName") or {}).get("text")]
    rows = await metric_rows(db, base.id)
    comps = [
        r.display_name
        for r in rows
        if r.subject_type == "competitor" and r.metric_name == "success_count" and r.provider == "openai"
    ]
    recs = (
        (
            await db.execute(
                select(Recommendation.name)
                .join(AiResponse, AiResponse.id == Recommendation.response_id)
                .join(AiExecution, AiExecution.id == AiResponse.execution_id)
                .where(AiExecution.run_id == base.id, Recommendation.is_target.is_(True))
            )
        )
        .scalars()
        .all()
    )
    names = [n for n in dict.fromkeys([*targets, *recs, *comps]) if n]
    questions = (
        await db.scalars(
            select(Question)
            .where(Question.question_set_id == base.question_set_id)
            .order_by(Question.order_no)
        )
    ).all()
    answers = (
        await db.execute(
            select(
                AiResponse.id,
                AiResponse.raw_text,
                AiExecution.provider,
                AiExecution.repeat_no,
                AiExecution.question_id,
            )
            .join(AiExecution, AiExecution.id == AiResponse.execution_id)
            .where(AiExecution.run_id == base.id)
            .order_by(AiExecution.question_id, AiExecution.provider, AiExecution.repeat_no)
        )
    ).all()
    return PlanEvidence(
        questions=[
            EvidenceQuestion(
                order_no=q.order_no,
                text=q.text,
                answers=[
                    EvidenceAnswer(
                        response_id=rid,
                        provider=prov,
                        repeat_no=rep,
                        raw_text=text,
                        highlight_names=[n for n in names if n in text],
                    )  # type: ignore[arg-type]
                    for rid, text, prov, rep, qid in answers
                    if qid == q.id
                ],
            )
            for q in questions
        ]
    )


# --- E15 승인 ------------------------------------------------------------------------------


def _log_mode(provider: str, sp: FieldSpec | None) -> tuple[str, str, str | None]:
    """(fix_logs 상태, method, manual_reason)."""
    s = get_settings()
    if not s.auto_fix_enabled:
        return FixLogStatus.MANUAL_REQUIRED, "manual", "automation_disabled"
    if provider == "kakao" and not s.kakao_fix_enabled:
        return FixLogStatus.MANUAL_REQUIRED, "manual", "kakao_fix_disabled"
    if provider == "google" and s.google_fix_mode == "api":
        if sp is None or not sp.api:
            return FixLogStatus.MANUAL_REQUIRED, "manual", "api_unsupported"
        return FixLogStatus.QUEUED, "api", None
    return FixLogStatus.QUEUED, "browser", None


async def approve(db: AsyncSession, user: User, plan_id: int, body: ApproveRequest) -> ApproveResponse:
    plan, req, store = await _owned(db, user, plan_id)
    if store.owner_id != user.id:
        raise AppError("NOT_FOUND")  # 승인은 사장님만
    plan = await db.get(
        FixPlan, plan_id, with_for_update=True
    )  # 같은 정비안 승인을 한 줄로(두 번 누름·동시 요청)
    await db.refresh(plan)
    req = await db.get(FixRequest, req.id, with_for_update=True)
    await db.refresh(req)
    if req.status not in WRITABLE_REQUEST or plan.status != FixPlanStatus.AWAITING_APPROVAL:
        raise AppError(
            "INVALID_STATE", {"currentStatus": plan.status if req.status in WRITABLE_REQUEST else req.status}
        )
    conn = await db.scalar(
        select(MapConnection).where(
            MapConnection.fix_request_id == req.id, MapConnection.provider == plan.provider
        )
    )
    if conn is None or conn.status != ConnectionStatus.CONNECTED:
        raise AppError("CONNECTION_NOT_CONNECTED", {"provider": plan.provider})
    rows = {i.id: i for i in await db.scalars(select(FixPlanItem).where(FixPlanItem.fix_plan_id == plan_id))}
    sent = [i.item_id for i in body.items]
    if len(sent) != len(set(sent)) or set(sent) != set(rows):
        raise AppError("ITEMS_MISMATCH")
    needs_input, unconfirmed, invalid = [], [], None
    decided: list[tuple[FixPlanItem, Any, bool, bool, bool]] = []  # (행, 값, 제외, 고침, 확인)
    for it in body.items:
        row, sp = rows[it.item_id], spec(plan.provider, rows[it.item_id].field)
        given = "approved_value" in it.model_fields_set
        value = it.approved_value if given else row.proposed_value
        edited = given and not same_value(sp.type if sp else "text", value, row.proposed_value)
        confirmed = bool(it.owner_confirmed)
        decided.append((row, value, it.excluded, edited, confirmed))
        if it.excluded:
            continue
        if sp is not None and is_incomplete(sp, value):
            if row.needs_owner_input:
                needs_input.append(row.id)
            else:
                invalid = invalid or {"itemId": row.id, "reason": "placeholder_left"}
            continue
        if row.sensitive and not confirmed:
            unconfirmed.append(row.id)
        reason = validate_value(sp, value) if sp else "bad_format"  # 사장님이 고친 값도 형식만 검사
        if reason:
            invalid = invalid or {"itemId": row.id, "reason": reason}
    if needs_input:
        raise AppError("NEEDS_OWNER_INPUT", {"itemIds": needs_input})
    if unconfirmed:
        raise AppError("SENSITIVE_NOT_CONFIRMED", {"itemIds": unconfirmed})
    if invalid:
        raise AppError("FIELD_INVALID", invalid)

    for row, value, excluded, edited, confirmed in decided:
        row.approved_value = None if excluded else value
        row.excluded, row.owner_edited, row.owner_confirmed = excluded, edited and not excluded, confirmed
    await transition(
        db,
        FixPlan,
        plan_id,
        from_={FixPlanStatus.AWAITING_APPROVAL},
        to=FixPlanStatus.APPROVED,
        values={"approved_at": now_utc(), "approved_by": user.id},
    )
    if req.status == FixRequestStatus.REMEASURE_SCHEDULED:  # D-16: 재측정 전 다른 지도 승인 → 예약 취소
        await db.execute(
            update(RemeasureSchedule)
            .where(RemeasureSchedule.fix_request_id == req.id, RemeasureSchedule.status == "scheduled")
            .values(status="canceled")
        )
    if req.status != FixRequestStatus.FIXING:
        await transition(
            db,
            FixRequest,
            req.id,
            from_={FixRequestStatus.CONNECTING, FixRequestStatus.REMEASURE_SCHEDULED},
            to=FixRequestStatus.FIXING,
        )
    queued, manual = 0, []
    for row, value, excluded, _, _ in decided:
        if excluded:
            continue
        status, method, reason = _log_mode(plan.provider, spec(plan.provider, row.field))
        db.add(
            FixLog(
                fix_plan_item_id=row.id,
                fix_request_id=req.id,
                provider=plan.provider,
                field=row.field,
                method=method,
                applied_value=value,
                status=status,
                manual_reason=reason,
            )
        )
        if status == FixLogStatus.QUEUED:
            queued += 1
        else:
            manual.append(
                {
                    "provider": plan.provider,
                    "field_label": field_label(plan.provider, row.field),
                    "reason": reason,
                }
            )
    excluded_count = sum(1 for d in decided if d[2])
    audit.record(
        db,
        actor_id=user.id,
        action="fix_plan.approve",
        target_type="fix_plan",
        target_id=plan_id,
        detail={
            "itemCount": len(decided) - excluded_count,
            "excludedCount": excluded_count,
            "editedCount": sum(1 for d in decided if d[3] and not d[2]),
        },
    )
    from seelo.worker.tasks_fix import apply_fix

    if queued:
        await jobs.defer(
            db, apply_fix, args={"fix_plan_id": plan_id},
            links=jobs.JobLinks(store_id=store.id, fix_request_id=req.id),
            queueing_lock=f"apply:{plan_id}", lock=f"fix:{plan.provider}",
        )  # fmt: skip
    else:
        await fix_apply_service.defer_finalize(db, req.id, store_id=store.id)
    if manual:
        await email_service.queue(
            db,
            "manual_required",
            params={"request_id": req.id, "items": manual},
            dedupe_key=f"manual_required:plan:{plan_id}",
        )
    await db.commit()
    log.info("fix_plan_approved", plan_id=plan_id, queued=queued, manual=len(manual), excluded=excluded_count)
    return ApproveResponse(plan_id=plan_id, status="approved")


# --- E23 관리자 다시 생성 -------------------------------------------------------------------


async def regenerate(db: AsyncSession, admin: User, plan_id: int) -> None:
    plan = await db.get(FixPlan, plan_id, with_for_update=True)
    if plan is None:
        raise AppError("NOT_FOUND")
    moved = await transition(
        db,
        FixPlan,
        plan_id,
        from_={FixPlanStatus.GENERATION_FAILED},
        to=FixPlanStatus.GENERATING,
        values={"generation_attempts": 0, "last_error": None},
    )
    if not moved:
        raise AppError("INVALID_STATE", {"currentStatus": plan.status})
    req = await db.get(FixRequest, plan.fix_request_id)
    has_items = await db.scalar(select(exists().where(FixPlanItem.fix_plan_id == plan_id)))
    if has_items:
        await _defer_generate(db, plan_id, store_id=req.store_id, request_id=req.id)
    else:
        await defer_read(db, plan_id, plan.provider, store_id=req.store_id, request_id=req.id)
    audit.record(
        db, actor_id=admin.id, action="fix_plan.regenerate", target_type="fix_plan", target_id=plan_id
    )
    await db.commit()
