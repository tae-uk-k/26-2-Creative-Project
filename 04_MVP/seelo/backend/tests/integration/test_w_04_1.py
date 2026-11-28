"""W-04-1 질문 만들기 흐름(08 1.4): 생성·검증·3번 실패 뒤 템플릿·세트 재사용·저장과 다음 작업 등록."""

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import MeasurementRun, Question, QuestionSet
from seelo.models.store import Store
from seelo.schemas.llm import GeneratedQuestionOut, GeneratedQuestionsOut
from seelo.services import question_service
from tests.map_world import g_detail, k, n, north, seed_google_snapshot, seed_measuring

pytestmark = pytest.mark.usefixtures("queue_app")


async def _ready(db: AsyncSession, maps: Any, **google: Any) -> tuple[int, int]:
    maps.kakao.world = [k("K1", "명동교자 카카오", north(30))]
    maps.naver.world = [n("명동교자 네이버", north(40))]
    store_id, run_id, _ = await seed_measuring(db, with_questions=False)
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "명동교자", **google))
    return store_id, run_id


async def _jobs(db: AsyncSession) -> list[tuple[str, dict]]:
    return [
        (r[0], r[1])
        for r in await db.execute(text("SELECT task_name, args FROM procrastinate_jobs ORDER BY id"))
    ]


def _bad_with_name(prompt: str) -> GeneratedQuestionsOut:
    """가게 이름이 들어간 질문(검증 실패)."""
    return GeneratedQuestionsOut(
        questions=[
            GeneratedQuestionOut(
                lang="en", intent_type="basic", text="Is 명동교자 good near Myeong-dong?", text_ko=None
            ),
            GeneratedQuestionOut(
                lang="en",
                intent_type="conditional",
                text="Korean restaurants with takeout near Myeong-dong?",
                text_ko=None,
            ),
            GeneratedQuestionOut(
                lang="ko", intent_type="basic", text="명동 근처 한식당 추천해줘", text_ko=None
            ),
        ],
        region_en="Myeong-dong",
    )


async def test_llm_questions_saved_and_measurement_registered(db: AsyncSession, maps: Any, ai: Any) -> None:
    store_id, run_id = await _ready(db, maps)
    await question_service.generate(run_id)

    run = await db.get(MeasurementRun, run_id)
    qset = await db.get(QuestionSet, run.question_set_id)
    assert (qset.version, qset.region_ko, qset.region_en, qset.category, qset.generated_by) == (
        1,
        "명동",
        "Myeong-dong",
        "restaurant",
        "llm",
    )
    assert qset.features == ["budget"]  # 조건 순서: 채식(없음) → 가격(저렴, 참) → …
    qs = (
        await db.scalars(
            select(Question).where(Question.question_set_id == qset.id).order_by(Question.order_no)
        )
    ).all()
    assert [(q.order_no, q.lang, q.intent_type) for q in qs] == [
        (1, "en", "basic"),
        (2, "en", "conditional"),
        (3, "ko", "basic"),
    ]
    assert qs[2].text_ko is None and qs[0].text_ko
    assert run.stage == "calling_ai"
    assert await _jobs(db) == [("runMeasurement", {"run_id": run_id})]
    # LLM에는 가게 이름 후보(입력·Google·카카오·네이버 이름)를 보내지 않는다
    prompt = ai.openai.calls[0]["prompt"]
    for name in ("명동교자", "Myeongdong Kyoja", "카카오", "네이버"):
        assert name not in prompt


async def test_three_failures_then_template(db: AsyncSession, maps: Any, ai: Any) -> None:
    store_id, run_id = await _ready(db, maps)
    ai.openai.results["GeneratedQuestionsOut"] = _bad_with_name
    await question_service.generate(run_id)
    assert len([c for c in ai.openai.calls if c["schema"] == "GeneratedQuestionsOut"]) == 3
    run = await db.get(MeasurementRun, run_id)
    qset = await db.get(QuestionSet, run.question_set_id)
    assert qset.generated_by == "template"
    first = await db.scalar(
        select(Question.text).where(Question.question_set_id == qset.id, Question.order_no == 1)
    )
    assert first == "What are good Korean restaurants near Myeong-dong?"


async def test_llm_errors_count_as_failures(db: AsyncSession, maps: Any, ai: Any) -> None:
    _, run_id = await _ready(db, maps)
    ai.openai.fail_next(3, "server_error")
    await question_service.generate(run_id)
    run = await db.get(MeasurementRun, run_id)
    assert (await db.get(QuestionSet, run.question_set_id)).generated_by == "template"


async def test_template_also_invalid_fails_run(db: AsyncSession, maps: Any, ai: Any) -> None:
    """가게 이름이 지역 이름과 같은 드문 경우: 템플릿도 실패 → 측정 failed(collect_insufficient)."""
    maps.kakao.world = []
    store_id, run_id, _ = await seed_measuring(db, with_questions=False, name="명동")
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "명동"))
    ai.openai.results["GeneratedQuestionsOut"] = _bad_with_name
    await question_service.generate(run_id)
    run = await db.get(MeasurementRun, run_id)
    assert (run.status, run.failure_reason, run.question_set_id) == ("failed", "collect_insufficient", None)
    assert (await db.get(Store, store_id)).status == "measure_failed"
    assert [t for t, _ in await _jobs(db)] == ["sendEmail"]  # 결과(실패) 메일만


async def test_region_en_from_llm_when_google_has_none(db: AsyncSession, maps: Any, ai: Any) -> None:
    maps.kakao.world = [k("K1", "명동교자", north(30))]
    store_id, run_id, _ = await seed_measuring(db, with_questions=False)
    ko = g_detail("G1", "명동교자")
    await seed_google_snapshot(db, store_id, run_id, ko)
    await db.execute(
        text(
            "UPDATE source_snapshots SET payload = jsonb_set(payload, '{en}', 'null'::jsonb) "
            "WHERE store_id = :s"
        ),
        {"s": store_id},
    )
    await db.commit()

    def gen(prompt: str) -> GeneratedQuestionsOut:
        assert "return it as region_en" in prompt
        return GeneratedQuestionsOut(
            questions=[
                GeneratedQuestionOut(
                    lang="en",
                    intent_type="basic",
                    text="Good Korean restaurants near Myeongdong?",
                    text_ko=None,
                ),
                GeneratedQuestionOut(
                    lang="en",
                    intent_type="conditional",
                    text="Affordable Korean restaurants near Myeongdong?",
                    text_ko=None,
                ),
                GeneratedQuestionOut(
                    lang="ko", intent_type="basic", text="명동 근처 한식당 추천해줘", text_ko=None
                ),
            ],
            region_en="Myeongdong",
        )

    ai.openai.results["GeneratedQuestionsOut"] = gen
    await question_service.generate(run_id)
    run = await db.get(MeasurementRun, run_id)
    assert (await db.get(QuestionSet, run.question_set_id)).region_en == "Myeongdong"


async def test_retry_run_reuses_same_region_question_set(db: AsyncSession, maps: Any, ai: Any) -> None:
    store_id, run_id = await _ready(db, maps)
    await question_service.generate(run_id)
    first_set = (await db.get(MeasurementRun, run_id)).question_set_id
    # 측정 실패 뒤 다시 시도한 진단
    retry = MeasurementRun(
        store_id=store_id,
        kind="diagnosis",
        is_free=False,
        trigger="retry",
        status="running",
        stage="generating_questions",
    )
    db.add(retry)
    await db.commit()
    retry_id = retry.id
    calls_before = len(ai.openai.calls)
    await question_service.generate(retry_id)
    db.expire_all()
    assert (await db.get(MeasurementRun, retry_id)).question_set_id == first_set
    assert len(ai.openai.calls) == calls_before  # 새로 만들지 않음


async def test_not_running_or_already_has_questions_is_skipped(db: AsyncSession, maps: Any, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db, with_questions=True)
    await question_service.generate(run_id)
    assert ai.openai.calls == [] and await _jobs(db) == []
