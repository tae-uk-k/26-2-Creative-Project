"""측정 마무리 finalizeRun(08 4·5장, 03 E4~E7).

1. 측정 running → parsing(조건부, stage finalizing). 작업이 다시 돌면(RetryStrategy) parsing에서 이어 간다.
2. 실패율 30% 초과 → E5(진단)·E7(재측정)로 끝(run_failure.fail_run).
3. 저장 전 계산(트랜잭션 밖): 카카오·네이버 다시 부르기 1번(4.2 이름 후보·6장 출처 비교 공용) → 우리 가게
   판정(메모리) → 지표 → 진단이면 고쳐야 할 점(주변 가게 사실 조회·AI 주장 비교는 외부 호출).
4. 한 트랜잭션에서: 이 측정의 metrics·diagnosis findings를 먼저 지우고(다시 실행돼도 같게) → is_target·지표·
   고쳐야 할 점 저장 → failure_rate·completed → E4·E6.
- 측정이 parsing이면 callAi·추출 결과는 더 쓰이지 않는다(둘 다 running일 때만 씀). 3번 동안 그대로다.
- 카카오·네이버 값은 판정에만 쓰고 저장하지 않는다.
- E4로 신청이 connecting이 되면 이미 연결된 지도마다 정비안 만들기 단계(E12). compareFixValues(E6)는 14단계.
"""

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.findings_rules import FindingDraft, FindingInputs, TargetClaim
from seelo.domain.metrics import (
    MetricRow,
    RecView,
    ResponseView,
    competitors,
    compute_run_metrics,
    failure_rate,
    is_run_failed,
)
from seelo.domain.normalize import normalize_name
from seelo.domain.states import (
    ExecStatus,
    ExtractionStatus,
    FindingStage,
    FixRequestStatus,
    MatchStatus,
    MetricName,
    RunKind,
    RunStage,
    RunStatus,
    StoreStatus,
    SubjectType,
    transition,
)
from seelo.integrations import Clients, get_clients
from seelo.models.finding import Finding
from seelo.models.fix import FixRequest
from seelo.models.measurement import (
    AiExecution,
    AiResponse,
    MeasurementRun,
    Metric,
    Question,
    QuestionSet,
    Recommendation,
)
from seelo.models.store import Store, StoreSource, WebEvidence
from seelo.models.user import FreeUsageLedger, User
from seelo.security.tokens import email_hmac
from seelo.services import connection_service, email_service, findings_service
from seelo.services.collect_service import latest_snapshot
from seelo.services.refetch import name_candidates, refetch_basics
from seelo.services.run_failure import fail_run
from seelo.timeutil import now_utc

log = structlog.get_logger()

MIN_NAME_LEN = 2


def target_name_set(names: list[str]) -> set[str]:
    """4.2: 정규화하고 2자 미만·빈 값은 뺀다."""
    return {nn for n in names if len(nn := normalize_name(n)) >= MIN_NAME_LEN}


async def _start(run_id: int) -> dict[str, Any] | None:
    """1번. 측정 running → parsing. 이미 parsing이면(작업 다시 실행) 이어 간다."""
    async with session_scope() as s:
        moved = await transition(
            s,
            MeasurementRun,
            run_id,
            from_={RunStatus.RUNNING},
            to=RunStatus.PARSING,
            values={"stage": RunStage.FINALIZING},
        )
        run = await s.get(MeasurementRun, run_id)
        if run is None or (not moved and run.status != RunStatus.PARSING):
            log.info("finalize_skip", run_id=run_id, status=run.status if run else None)
            return None
        store = await s.get(Store, run.store_id)
        sources = {
            r.provider: r
            for r in await s.scalars(select(StoreSource).where(StoreSource.store_id == store.id))
        }
        google = await latest_snapshot(s, store.id, run_id, "google")
        info = {
            "store_id": store.id,
            "store_name": store.name,
            "category": store.category,
            "kind": run.kind,
            "question_set_id": run.question_set_id,
            "sources": sources,
            "google": google,
        }
        await s.commit()
    return info


async def _counts(s: AsyncSession, run_id: int) -> tuple[int, int]:
    """(실패 실행 수, 전체 실행 수). 끝나지 않은 실행도 실패로 센다(성공만 성공)."""
    total = await s.scalar(select(func.count()).select_from(AiExecution).where(AiExecution.run_id == run_id))
    succeeded = await s.scalar(
        select(func.count())
        .select_from(AiExecution)
        .where(AiExecution.run_id == run_id, AiExecution.status == ExecStatus.SUCCEEDED)
    )
    return (total or 0) - (succeeded or 0), total or 0


async def _mark_targets(s: AsyncSession, run_id: int, names: set[str]) -> None:
    response_ids = (
        select(AiResponse.id)
        .join(AiExecution, AiExecution.id == AiResponse.execution_id)
        .where(AiExecution.run_id == run_id)
    )
    await s.execute(
        update(Recommendation)
        .where(Recommendation.response_id.in_(response_ids))
        .values(is_target=Recommendation.normalized_name.in_(list(names)) if names else False)
    )


async def response_views(s: AsyncSession, run_id: int, names: set[str] | None = None) -> list[ResponseView]:
    """성공 실행의 응답(추출 실패는 extraction_ok=False). 실패 실행은 넣지 않는다(5.1).

    names를 주면 is_target을 그 이름 후보로 정한다(마무리 계산용). 없으면 DB 값.
    """
    rows = (
        await s.execute(
            select(
                AiResponse.id,
                AiExecution.provider,
                AiExecution.question_id,
                AiResponse.extraction_status,
                AiResponse.source_urls,
            )
            .join(AiExecution, AiExecution.id == AiResponse.execution_id)
            .where(AiExecution.run_id == run_id, AiExecution.status == ExecStatus.SUCCEEDED)
            .order_by(AiResponse.id)
        )
    ).all()
    recs: dict[int, list[RecView]] = {}
    for rec in await s.scalars(
        select(Recommendation)
        .where(Recommendation.response_id.in_([r[0] for r in rows]))
        .order_by(Recommendation.response_id, Recommendation.rank)
    ):
        recs.setdefault(rec.response_id, []).append(
            RecView(
                normalized_name=rec.normalized_name,
                name=rec.name,
                rank=rec.rank,
                is_target=rec.is_target if names is None else rec.normalized_name in names,
                source_domains=list(
                    dict.fromkeys(u.get("domain") or "unknown" for u in rec.source_urls or [])
                ),
                mentioned_attributes=list(rec.mentioned_attributes or []),
            )
        )
    return [
        ResponseView(
            response_id=rid,
            provider=provider,
            question_id=qid,
            extraction_ok=status == ExtractionStatus.SUCCEEDED,
            recs=recs.get(rid, []),
            source_domains=list(dict.fromkeys(u.get("domain") or "unknown" for u in sources or [])),
        )
        for rid, provider, qid, status, sources in rows
    ]


async def load_questions(
    s: AsyncSession, question_set_id: int | None
) -> tuple[list[int], dict[int, list[str]], str | None]:
    """(질문 id 순서대로, 질문별 조건 키, 한글 지역). 조건 키는 conditional 질문에만 붙는다."""
    if question_set_id is None:
        return [], {}, None
    qset = await s.get(QuestionSet, question_set_id)
    rows = (
        await s.scalars(
            select(Question).where(Question.question_set_id == question_set_id).order_by(Question.order_no)
        )
    ).all()
    feats = list(qset.features or []) if qset else []
    features = {q.id: (feats if q.intent_type == "conditional" else []) for q in rows}
    return [q.id for q in rows], features, qset.region_ko if qset else None


async def _claims(s: AsyncSession, run_id: int) -> list[TargetClaim]:
    rows = (
        await s.execute(
            select(AiResponse.id, AiExecution.provider, AiExecution.question_id, AiResponse.target_claims)
            .join(AiExecution, AiExecution.id == AiResponse.execution_id)
            .where(AiExecution.run_id == run_id, AiResponse.extraction_status == ExtractionStatus.SUCCEEDED)
        )
    ).all()
    return [
        TargetClaim(rid, provider, qid, c.get("field", ""), c.get("value") or "")
        for rid, provider, qid, claims in rows
        for c in claims or []
    ]


async def _findings(
    clients: Clients,
    info: dict[str, Any],
    run_id: int,
    views: list[ResponseView],
    kakao: Any,
    naver: Any,
) -> tuple[list[FindingDraft], float]:
    """진단 단계 고쳐야 할 점(08 6장). 외부 호출이 있으므로 트랜잭션 밖에서."""
    async with session_scope() as s:
        question_ids, features, region = await load_questions(s, info["question_set_id"])
        claims = await _claims(s, run_id)
        website = await latest_snapshot(s, info["store_id"], run_id, "website")
        web_sites = list(
            (await s.scalars(select(WebEvidence.fields).where(WebEvidence.run_id == run_id))).all()
        )
        await s.commit()
    ko = (info["google"] or {}).get("ko") or None
    loc = (ko or {}).get("location") or {}
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        coords: tuple[float, float] | None = (loc["latitude"], loc["longitude"])
    elif kakao is not None and kakao.lat is not None and kakao.lng is not None:
        coords = (kakao.lat, kakao.lng)
    else:
        coords = None
    comps = competitors(views)
    facts = await findings_service.lookup_competitor_facts(clients, comps, region=region, coords=coords)
    sources = info["sources"]
    inp = FindingInputs(
        category=info["category"],
        google_found=getattr(sources.get("google"), "match_status", None) == MatchStatus.FOUND,
        kakao_found=getattr(sources.get("kakao"), "match_status", None) == MatchStatus.FOUND,
        google=ko,
        kakao_basic=kakao,
        naver_basic=naver,
        website=(website or {}).get("extract"),
        web_sites=web_sites,
        question_ids=question_ids,
        question_features=features,
        responses=views,
        claims=claims,
        competitors=[n for n, _ in comps],
        competitor_facts=facts,
        name_threshold=get_settings().name_similarity_threshold,
    )
    return await findings_service.judge_for_run(clients, inp)


def _finding(run_id: int, d: FindingDraft) -> Finding:
    return Finding(
        run_id=run_id,
        stage=d.stage,
        category=d.category,
        title_key=d.title_key,
        provider=d.provider,
        field=d.field,
        competitor_count=d.competitor_count,
        question_count=d.question_count,
        priority=d.priority,
        evidence=d.evidence,
    )


def _metric(run_id: int, m: MetricRow) -> Metric:
    return Metric(
        run_id=run_id,
        provider=m.provider,
        question_id=m.question_id,
        subject_type=m.subject_type,
        subject_name=m.subject_name,
        metric_name=m.metric_name,
        value=None if m.value is None else Decimal(str(round(m.value, 6))),
        denominator=m.denominator,
        rank_order=m.rank_order,
        display_name=m.display_name,
    )


def target_rate(rows: list[MetricRow], provider: str) -> float | None:
    """공급자별 우리 가게 전체 등장률(메일·화면용). 측정하지 못했으면 None."""
    for m in rows:
        if (
            m.subject_type == SubjectType.TARGET
            and m.provider == provider
            and m.question_id is None
            and m.metric_name == MetricName.APPEARANCE_RATE
        ):
            return m.value
    return None


async def finalize(run_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    info = await _start(run_id)
    if info is None:
        return

    # 2. 실패율
    async with session_scope() as s:
        failed, total = await _counts(s, run_id)
        if is_run_failed(failed, total):
            run = await s.get(MeasurementRun, run_id, with_for_update=True)
            run.failure_rate = Decimal(str(round(failure_rate(failed, total), 4)))
            await fail_run(s, run, "failure_rate")  # E5·E7
            await s.commit()
            log.info("finalize_failure_rate", run_id=run_id, failed=failed, total=total)
            return
        await s.commit()

    # 3. 저장 전 계산(외부 호출이 있으므로 트랜잭션 밖에서)
    kakao, naver = await refetch_basics(clients, info["store_name"], info["google"], info["sources"])
    names = target_name_set(name_candidates(info["store_name"], info["google"], kakao, naver))
    async with session_scope() as s:
        views = await response_views(s, run_id, names)
        question_ids, _, _ = await load_questions(s, info["question_set_id"])
        await s.commit()
    result = compute_run_metrics(views, question_ids=question_ids, failed=failed, total=total)
    drafts: list[FindingDraft] = []
    extra_cost = 0.0
    if info["kind"] == RunKind.DIAGNOSIS:
        drafts, extra_cost = await _findings(clients, info, run_id, views, kakao, naver)

    # 4. 한 트랜잭션
    async with session_scope() as s:
        run = await s.get(MeasurementRun, run_id, with_for_update=True)
        if run is None or run.status != RunStatus.PARSING:
            log.info("finalize_skip_locked", run_id=run_id)
            return
        await s.execute(delete(Metric).where(Metric.run_id == run_id))
        await s.execute(
            delete(Finding).where(Finding.run_id == run_id, Finding.stage == FindingStage.DIAGNOSIS)
        )
        await _mark_targets(s, run_id, names)
        s.add_all(_metric(run_id, m) for m in result.rows)
        s.add_all(_finding(run_id, d) for d in drafts)
        if extra_cost > 0:  # AI 주장 비교 비용(06 6장)
            run.cost_usd = run.cost_usd + Decimal(str(round(extra_cost, 6)))
        await s.flush()
        await transition(
            s,
            MeasurementRun,
            run_id,
            from_={RunStatus.PARSING},
            to=RunStatus.COMPLETED,
            values={
                "failure_rate": Decimal(str(round(result.failure_rate, 4))),
                "stage": RunStage.DONE,
                "completed_at": now_utc(),
            },
        )
        if run.kind == RunKind.DIAGNOSIS:
            await _diagnosis_completed(s, run, result.rows)
        else:
            log.info("remeasure_completed", run_id=run_id, next="compareFixValues(14단계)")  # E6
        await s.commit()
    log.info(
        "run_completed",
        run_id=run_id,
        kind=info["kind"],
        responses=len(views),
        competitors=len(result.competitors),
        findings=len(drafts),
        failure_rate=round(result.failure_rate, 4),
    )


async def _diagnosis_completed(s: AsyncSession, run: MeasurementRun, rows: list[MetricRow]) -> None:
    """E4: 가게 → diagnosed, 무료면 무료 사용 기록, 승인된 신청이면 기준 측정·connecting, 결과 메일."""
    run_id, store_id = run.id, run.store_id
    await transition(s, Store, store_id, from_={StoreStatus.MEASURING}, to=StoreStatus.DIAGNOSED)
    store = await s.get(Store, store_id)
    owner = await s.get(User, store.owner_id) if store else None
    if run.is_free and owner is not None:
        await s.execute(
            insert(FreeUsageLedger).values(email_hash=email_hmac(owner.email)).on_conflict_do_nothing()
        )
    if run.fix_request_id is not None:
        moved = await transition(
            s,
            FixRequest,
            run.fix_request_id,
            from_={FixRequestStatus.APPROVED},
            to=FixRequestStatus.CONNECTING,
            values={"base_run_id": run_id},
        )
        if moved:  # 이미 연결된 지도가 있으면 정비안 만들기 단계(E12)
            req = await s.get(FixRequest, run.fix_request_id)
            await s.refresh(req)
            plans = await connection_service.plans_for_connected(s, req)
            log.info("fix_request_connecting", request_id=req.id, base_run_id=run_id, plans=plans)
    if owner is not None:
        await email_service.queue(
            s,
            "diagnosis_result",
            user=owner,
            params={
                "result": "completed",
                "run_id": run_id,
                "openai_rate": target_rate(rows, "openai"),
                "gemini_rate": target_rate(rows, "gemini"),
            },
            dedupe_key=f"diagnosis_result:{run_id}",
        )
