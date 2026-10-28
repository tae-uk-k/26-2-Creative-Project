"""질문 만들기 generateQuestions(08 1장, W-04-1).

흐름(1.4): 지역·업종 확인 → 같은 지역·업종의 기존 세트가 있으면 다시 씀 → 없으면 LLM 생성·검증(최대 3번)
→ 그래도 실패면 템플릿(이것도 검증, 실패하면 측정 failed collect_insufficient) → 한 트랜잭션으로
question_sets·questions 저장, 측정 stage calling_ai, runMeasurement 등록.
- 가게 이름 후보(target_names)는 검증에만 쓰고 LLM에 보내지 않는다.
- 카카오·네이버 이름은 이 판정에만 쓰고 저장하지 않는다.
"""

from typing import Any

import structlog
from sqlalchemy import func, select

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.questions import (
    cuisine_for,
    generation_prompt,
    pick_feature,
    template_questions,
    validate_questions,
)
from seelo.domain.region import from_google, from_kakao_address
from seelo.domain.states import MatchStatus, RunStage, RunStatus
from seelo.integrations import Clients, get_clients
from seelo.integrations.llm import LlmError, cost_usd
from seelo.models.measurement import MeasurementRun, Question, QuestionSet
from seelo.models.store import Store, StoreSource
from seelo.schemas.llm import GeneratedQuestionOut, GeneratedQuestionsOut
from seelo.services import jobs
from seelo.services.collect_service import add_run_cost, latest_snapshot
from seelo.services.refetch import name_candidates, refetch_basics, refetch_kakao
from seelo.services.run_failure import fail_run

log = structlog.get_logger()

MAX_GENERATIONS = 3


async def target_names(
    clients: Clients,
    store_name: str,
    google: dict[str, Any] | None,
    sources: dict[str, StoreSource],
) -> list[str]:
    """우리 가게 이름 후보(08 4.2): 입력 이름, Google ko·en, 카카오·네이버 다시 부르기 이름."""
    kakao, naver = await refetch_basics(clients, store_name, google, sources)
    return name_candidates(store_name, google, kakao, naver)


async def _region(
    clients: Clients, store_name: str, google: dict[str, Any] | None, sources: dict[str, StoreSource]
) -> tuple[str | None, str | None]:
    ko, en = from_google((google or {}).get("ko"), (google or {}).get("en"))
    if ko:
        return ko, en
    kakao = sources.get("kakao")
    if kakao is None or kakao.match_status != MatchStatus.FOUND:
        return None, None
    place = await refetch_kakao(clients, kakao.external_id, [store_name])
    return (from_kakao_address(place.raw.get("address_name")) if place else None), None


async def _generate(
    clients: Clients,
    run_id: int,
    *,
    names: list[str],
    region_ko: str,
    region_en: str | None,
    category: str,
    cuisine: tuple[str, str],
    feature: str,
) -> tuple[list[GeneratedQuestionOut], str, str]:
    """(질문 3개, region_en, generated_by). 실패하면 빈 목록."""
    model = get_settings().openai_cheap_model
    prompt = generation_prompt(region_ko=region_ko, region_en=region_en, cuisine=cuisine, feature=feature)
    for attempt in range(1, MAX_GENERATIONS + 1):
        try:
            res = await clients.openai.structured(prompt, GeneratedQuestionsOut, model=model)
        except LlmError as e:
            log.warning("question_generation_failed", run_id=run_id, attempt=attempt, reason=e.reason)
            continue
        await add_run_cost(
            run_id,
            cost_usd("openai", res.model_id, input_tokens=res.input_tokens, output_tokens=res.output_tokens),
        )
        out: GeneratedQuestionsOut = res.parsed  # type: ignore[assignment]
        reg_en = region_en or (out.region_en or "").strip() or None
        errors = (
            validate_questions(
                out.questions,
                target_names=names,
                region_ko=region_ko,
                region_en=reg_en,
                category=category,
                cuisine=cuisine,
                feature=feature,
            )
            if reg_en
            else ["missing_region"]
        )
        if not errors:
            return out.questions, reg_en, "llm"  # type: ignore[return-value]
        log.info("questions_rejected", run_id=run_id, attempt=attempt, errors=errors)
    # 템플릿: 영어 지역 이름을 끝내 못 얻으면 한글 이름을 그대로 쓴다(추론: 드문 경우)
    reg_en = region_en or region_ko
    qs = template_questions(
        region_ko=region_ko, region_en=reg_en, category=category, cuisine=cuisine, feature=feature
    )
    errors = validate_questions(
        qs,
        target_names=names,
        region_ko=region_ko,
        region_en=reg_en,
        category=category,
        cuisine=cuisine,
        feature=feature,
    )
    if errors:
        log.warning("template_questions_rejected", run_id=run_id, errors=errors)
        return [], reg_en, "template"
    return qs, reg_en, "template"


async def generate(run_id: int, *, clients: Clients | None = None) -> None:
    clients = clients or get_clients()
    async with session_scope() as s:
        run = await s.get(MeasurementRun, run_id)
        if run is None or run.status != RunStatus.RUNNING or run.question_set_id is not None:
            log.info("generate_questions_skip", run_id=run_id)
            return
        store = await s.get(Store, run.store_id)
        google = await latest_snapshot(s, store.id, run_id, "google")
        sources = {
            r.provider: r
            for r in await s.scalars(select(StoreSource).where(StoreSource.store_id == store.id))
        }
        last_set = await s.scalar(
            select(QuestionSet)
            .where(QuestionSet.store_id == store.id)
            .order_by(QuestionSet.version.desc())
            .limit(1)
        )
        store_id, store_name, category = store.id, store.name, store.category
        reuse = (last_set.id, last_set.region_ko, last_set.category) if last_set else None
        await s.commit()

    region_ko, region_en = await _region(clients, store_name, google, sources)
    if not region_ko:
        await _fail(run_id, "collect_insufficient")
        return
    if reuse and reuse[1] == region_ko and reuse[2] == category:  # 다시 시도한 진단: 같은 질문으로
        await _attach(run_id, reuse[0])
        return

    ko = (google or {}).get("ko") or {}
    cuisine = cuisine_for(ko.get("primaryType"), category)
    feature = pick_feature(ko)
    names = await target_names(clients, store_name, google, sources)
    questions, region_en, generated_by = await _generate(
        clients,
        run_id,
        names=names,
        region_ko=region_ko,
        region_en=region_en,
        category=category,
        cuisine=cuisine,
        feature=feature,
    )
    if not questions:
        await _fail(run_id, "collect_insufficient")
        return
    async with session_scope() as s:
        version = (
            await s.scalar(select(func.max(QuestionSet.version)).where(QuestionSet.store_id == store_id))
        ) or 0
        qset = QuestionSet(
            store_id=store_id,
            version=version + 1,
            region_ko=region_ko,
            region_en=region_en,
            category=category,
            features=[feature],
            generated_by=generated_by,
        )
        s.add(qset)
        await s.flush()
        for order, q in enumerate(questions, start=1):
            s.add(
                Question(
                    question_set_id=qset.id,
                    order_no=order,
                    lang=q.lang,
                    intent_type=q.intent_type,
                    text=q.text,
                    text_ko=q.text_ko if q.lang == "en" else None,
                )
            )
        await _attach_in(s, run_id, qset.id)
        await s.commit()
    log.info("questions_saved", run_id=run_id, generated_by=generated_by, version=version + 1)


async def _attach(run_id: int, question_set_id: int) -> None:
    async with session_scope() as s:
        await _attach_in(s, run_id, question_set_id)
        await s.commit()


async def _attach_in(s: Any, run_id: int, question_set_id: int) -> None:
    """측정에 질문 세트를 붙이고 stage calling_ai, runMeasurement 등록(같은 트랜잭션)."""
    run = await s.get(MeasurementRun, run_id, with_for_update=True)
    if run is None or run.status != RunStatus.RUNNING or run.question_set_id is not None:
        await s.rollback()
        return
    run.question_set_id = question_set_id
    run.stage = RunStage.CALLING_AI
    from seelo.worker.tasks_measure import run_measurement

    await jobs.defer(
        s,
        run_measurement,
        args={"run_id": run_id},
        links=jobs.JobLinks(store_id=run.store_id, run_id=run_id),
        queueing_lock=f"measure:{run_id}",
    )


async def _fail(run_id: int, reason: str) -> None:
    async with session_scope() as s:
        run = await s.get(MeasurementRun, run_id, with_for_update=True)
        if run is not None and await fail_run(s, run, reason):
            await s.commit()
