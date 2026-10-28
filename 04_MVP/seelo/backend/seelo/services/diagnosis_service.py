"""무료 진단 결과 GET /api/diagnosis/{runId}(04 6장, S11).

- 진단(kind diagnosis)이고 completed인 측정만. 아니면 404. 남의 측정도 404(관리자는 볼 수 있음).
- 저장된 metrics 행으로만 만든다(외부 호출 없음). 고쳐야 할 점은 stage diagnosis 개수만 돌려준다.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.metrics import PROVIDERS, MetricRow, target_sources, top_sources
from seelo.domain.states import FindingStage, MetricName, RunKind, RunStatus, SubjectType
from seelo.errors import AppError
from seelo.models.finding import Finding
from seelo.models.measurement import AiExecution, MeasurementRun, Metric, Question
from seelo.models.store import Store
from seelo.models.user import User
from seelo.schemas.common import DomainCount, ProviderRates, RateSummary
from seelo.schemas.diagnosis import (
    Competitor,
    DiagnosisQuestion,
    DiagnosisResponse,
    DiagnosisSources,
    MeasureConditions,
    NamedRates,
    QuestionCount,
    QuestionProviders,
)

Key = tuple[str, str, str, int | None]  # (subject_type, subject_name, provider, question_id)


async def metric_rows(db: AsyncSession, run_id: int) -> list[MetricRow]:
    return [
        MetricRow(
            m.provider,
            m.question_id,
            m.subject_type,
            m.subject_name,
            m.metric_name,
            None if m.value is None else float(m.value),
            m.denominator,
            m.rank_order,
            m.display_name,
        )
        for m in await db.scalars(select(Metric).where(Metric.run_id == run_id))
    ]


def _index(rows: list[MetricRow]) -> dict[Key, dict[str, float | None]]:
    out: dict[Key, dict[str, float | None]] = defaultdict(dict)
    for r in rows:
        out[(r.subject_type, r.subject_name, r.provider, r.question_id)][r.metric_name] = r.value
    return out


def _rate(vals: dict[str, Any]) -> RateSummary:
    rate, avg = vals.get(MetricName.APPEARANCE_RATE), vals.get(MetricName.AVG_RANK)
    return RateSummary(
        success_count=int(vals.get(MetricName.SUCCESS_COUNT) or 0),
        appearance_count=int(vals.get(MetricName.APPEARANCE_COUNT) or 0),
        rate=None if rate is None else round(rate, 4),
        avg_rank=None if avg is None else round(avg, 1),
    )


def provider_rates(
    rows: list[MetricRow], subject_type: str = SubjectType.TARGET, name: str = "target"
) -> ProviderRates:
    """대상 하나의 공급자별 전체 지표(question_id 없음)."""
    idx = _index(rows)
    return ProviderRates(**{p: _rate(idx.get((subject_type, name, p, None), {})) for p in PROVIDERS})


def _question_providers(idx: dict[Key, dict[str, float | None]], qid: int) -> QuestionProviders:
    vals: dict[str, QuestionCount | None] = {}
    for p in PROVIDERS:
        v = idx.get((SubjectType.TARGET, "target", p, qid), {})
        success = int(v.get(MetricName.SUCCESS_COUNT) or 0)
        vals[p] = (
            QuestionCount(
                appearance_count=int(v.get(MetricName.APPEARANCE_COUNT) or 0), success_count=success
            )
            if success
            else None
        )
    return QuestionProviders(**vals)


async def findings_count(db: AsyncSession, run_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(Finding.run_id == run_id, Finding.stage == FindingStage.DIAGNOSIS)
        )
        or 0
    )


async def get(db: AsyncSession, user: User, run_id: int) -> DiagnosisResponse:
    row = (
        await db.execute(
            select(MeasurementRun, Store)
            .join(Store, Store.id == MeasurementRun.store_id)
            .where(MeasurementRun.id == run_id)
        )
    ).first()
    if row is None:
        raise AppError("NOT_FOUND")
    run, store = row
    if (store.owner_id != user.id and user.role != "admin") or (
        run.kind != RunKind.DIAGNOSIS or run.status != RunStatus.COMPLETED
    ):
        raise AppError("NOT_FOUND")
    rows = await metric_rows(db, run_id)
    idx = _index(rows)
    questions = (
        await db.scalars(
            select(Question)
            .where(Question.question_set_id == run.question_set_id)
            .order_by(Question.order_no)
        )
    ).all()
    repeat = await db.scalar(select(func.max(AiExecution.repeat_no)).where(AiExecution.run_id == run_id))
    comps = sorted(
        {
            (r.rank_order or 0, r.subject_name, r.display_name or r.subject_name)
            for r in rows
            if r.subject_type == SubjectType.COMPETITOR
        }
    )
    target = provider_rates(rows)
    measured_at = run.completed_at or run.updated_at
    return DiagnosisResponse(
        run_id=run.id,
        store_id=store.id,
        store_name=store.name,
        measured_at=measured_at,
        providers=target,
        target=NamedRates(name=store.name, providers=target),
        competitors=[
            Competitor(
                rank_order=order, name=display, providers=provider_rates(rows, SubjectType.COMPETITOR, norm)
            )
            for order, norm, display in comps
        ],
        questions=[
            DiagnosisQuestion(
                order_no=q.order_no,
                lang=q.lang,  # type: ignore[arg-type]
                text=q.text,
                text_ko=q.text_ko,
                providers=_question_providers(idx, q.id),
            )
            for q in questions
        ],
        sources=DiagnosisSources(
            top=[DomainCount(domain=d, count=n) for d, n in top_sources(rows)],
            target_sources=[DomainCount(domain=d, count=n) for d, n in target_sources(rows)],
        ),
        findings_count=await findings_count(db, run_id),
        conditions=MeasureConditions(
            question_count=len(questions),
            repeat_count=int(repeat or 0),
            providers=list(PROVIDERS),  # type: ignore[arg-type]
            measured_at=measured_at,
        ),
    )
