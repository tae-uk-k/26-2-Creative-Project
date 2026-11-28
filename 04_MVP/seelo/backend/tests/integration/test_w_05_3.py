"""W-05-3·4 측정 마무리 finalizeRun(08 4·5장, 03 E4~E7): 우리 가게 판정·지표·주변 가게 저장과 상태 전이.

지표 계산 자체는 unit/test_metrics.py(손 계산 사례)가 본다. 여기서는 DB 흐름을 본다.
"""

from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.metrics import MetricRow, competitor_position
from seelo.models.fix import FixPlan, FixRequest, MapConnection
from seelo.models.measurement import AiExecution, AiResponse, MeasurementRun, Metric, Recommendation
from seelo.models.ops import EmailLog
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger
from seelo.services import extract_service, finalize_service, measure_service
from tests.map_world import g_detail, k, north, seed_google_snapshot, seed_measuring

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, settings_env: Any) -> None:
    monkeypatch.setattr(measure_service, "BACKOFF_S", (0.0, 0.0))
    settings_env(
        AI_REPEAT_COUNT="2",
        OPENAI_MEASURE_MODEL="m-openai",
        GEMINI_MEASURE_MODEL="m-gemini",
        OPENAI_CHEAP_MODEL="m-cheap",
    )


async def _measured(db: AsyncSession, *, google_name: str = "데모식당", **kw: Any) -> tuple[int, int]:
    """질문 3 × 공급자 2 × 반복 2 = 12번 부르고 모두 추출한 상태. 가짜 답변은 반복 1번째만 데모식당 2위."""
    kw.setdefault("name", "데모식당")
    store_id, run_id, _ = await seed_measuring(db, **kw)
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", google_name))
    await measure_service.run(run_id)
    for ex_id in (await db.scalars(select(AiExecution.id).where(AiExecution.run_id == run_id))).all():
        await measure_service.call_ai(ex_id)
    for rid in (await db.scalars(select(AiResponse.id))).all():
        await extract_service.extract(rid)
    db.expire_all()
    return store_id, run_id


async def _metric(db: AsyncSession, run_id: int, provider: str, name: str, **where: Any) -> Any:
    q = select(Metric.value).where(
        Metric.run_id == run_id, Metric.provider == provider, Metric.metric_name == name
    )
    for col, val in {"subject_type": "target", "question_id": None, **where}.items():
        c = getattr(Metric, col)
        q = q.where(c.is_(None) if val is None else c == val)
    v = await db.scalar(q)
    return None if v is None else float(v)


async def test_diagnosis_completed_e4(db: AsyncSession, ai: Any) -> None:
    store_id, run_id = await _measured(db)
    assert (
        await db.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'finalizeRun'")) == 1
    )
    await finalize_service.finalize(run_id)
    db.expire_all()

    run = await db.get(MeasurementRun, run_id)
    assert (run.status, run.stage, float(run.failure_rate)) == ("completed", "done", 0.0)
    assert run.completed_at is not None
    assert (await db.get(Store, store_id)).status == "diagnosed"
    # 우리 가게 판정: 데모식당 추천만 is_target
    targets = (await db.scalars(select(Recommendation.name).where(Recommendation.is_target))).all()
    assert set(targets) == {"데모식당"} and len(targets) == 6
    # 지표: 공급자마다 6개 응답 중 3개에 2위로 등장
    for p in ("openai", "gemini"):
        assert await _metric(db, run_id, p, "success_count") == 6
        assert await _metric(db, run_id, p, "appearance_rate") == 0.5
        assert await _metric(db, run_id, p, "avg_rank") == 2.0
    # 주변 가게 5곳(등장 수 → 평균 순위): 광장빈대떡은 반복 2번째에만 나와 마지막
    comps = (
        await db.execute(
            select(Metric.rank_order, Metric.display_name)
            .where(
                Metric.subject_type == "competitor",
                Metric.provider == "openai",
                Metric.metric_name == "avg_rank",
            )
            .order_by(Metric.rank_order)
        )
    ).all()
    assert [d for _, d in comps] == ["명동칼국수", "을지면옥", "남산돈까스", "명동할머니국수", "광장빈대떡"]
    rows = [
        MetricRow(
            m.provider, m.question_id, m.subject_type, m.subject_name, m.metric_name,
            None if m.value is None else float(m.value), m.denominator, m.rank_order, m.display_name,
        )
        for m in await db.scalars(select(Metric).where(Metric.run_id == run_id))
    ]  # fmt: skip
    assert competitor_position(rows) == (5, 6)
    # 출처: 우리 가게 추천에 붙은 도메인
    tsrc = await _metric(
        db,
        run_id,
        "openai",
        "target_citation_count",
        subject_type="source",
        subject_name="korean.visitkorea.or.kr",
    )
    assert tsrc == 3
    # 무료 사용 기록 1행, 결과 메일(완료, 등장률)
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 1
    mail = await db.scalar(select(EmailLog))
    assert mail.type == "diagnosis_result" and mail.template_params == {
        "result": "completed",
        "run_id": run_id,
        "openai_rate": 0.5,
        "gemini_rate": 0.5,
    }


async def test_failure_rate_over_30_percent_is_e5(db: AsyncSession, ai: Any) -> None:
    ai.openai.fail_next(4, "bad_request", only="web_answer")  # 12개 중 4개 바로 실패 = 33%
    store_id, run_id = await _measured(db)
    await finalize_service.finalize(run_id)
    db.expire_all()
    run = await db.get(MeasurementRun, run_id)
    assert (run.status, run.failure_reason, float(run.failure_rate)) == ("failed", "failure_rate", 0.3333)
    assert (await db.get(Store, store_id)).status == "measure_failed"
    assert await db.scalar(select(func.count()).select_from(Metric)) == 0
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 0  # 무료 차감 없음
    mail = await db.scalar(select(EmailLog))
    assert mail.template_params == {"result": "failed", "run_id": run_id}


async def test_exactly_30_percent_passes(db: AsyncSession, ai: Any, settings_env: Any) -> None:
    settings_env(AI_REPEAT_COUNT="5")  # 30개 중 9개 실패 = 30%
    ai.gemini.fail_next(9, "bad_request", only="web_answer")
    _, run_id = await _measured(db)
    await finalize_service.finalize(run_id)
    db.expire_all()
    run = await db.get(MeasurementRun, run_id)
    assert (run.status, float(run.failure_rate)) == ("completed", 0.3)
    assert await _metric(db, run_id, "gemini", "success_count") == 6


async def test_remeasure_completed_e6_keeps_store_and_request(db: AsyncSession, ai: Any) -> None:
    store_id, run_id, _ = await seed_measuring(db, name="데모식당", kind="remeasure")
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="remeasuring"))
    await db.flush()
    req_id = await db.scalar(select(FixRequest.id))
    await db.execute(update(MeasurementRun).where(MeasurementRun.id == run_id).values(fix_request_id=req_id))
    await db.execute(text("UPDATE stores SET status = 'diagnosed' WHERE id = :i"), {"i": store_id})
    await db.commit()
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    await measure_service.run(run_id)
    for ex_id in (await db.scalars(select(AiExecution.id))).all():
        await measure_service.call_ai(ex_id)
    for rid in (await db.scalars(select(AiResponse.id))).all():
        await extract_service.extract(rid)
    await finalize_service.finalize(run_id)
    db.expire_all()
    assert (await db.get(MeasurementRun, run_id)).status == "completed"
    assert (await db.get(Store, store_id)).status == "diagnosed"
    assert (await db.get(FixRequest, req_id)).status == "remeasuring"  # 보고서(14단계)에서 바뀐다
    assert await db.scalar(select(func.count()).select_from(EmailLog)) == 0
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 0
    assert await _metric(db, run_id, "openai", "appearance_rate") == 0.5


async def test_approved_request_gets_base_run_and_connecting(db: AsyncSession, ai: Any) -> None:
    """E9로 만든 진단(신청 있음, 무료 아님)이 끝나면 신청 approved → connecting, base_run_id."""
    store_id, run_id, _ = await seed_measuring(db, name="데모식당")
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="approved"))
    await db.flush()
    req_id = await db.scalar(select(FixRequest.id))
    await db.execute(
        update(MeasurementRun).where(MeasurementRun.id == run_id).values(fix_request_id=req_id, is_free=False)
    )
    db.add(MapConnection(fix_request_id=req_id, provider="google", status="connected"))  # 측정 중 먼저 연결됨
    db.add(MapConnection(fix_request_id=req_id, provider="kakao", status="invited"))
    await db.commit()
    await measure_service.run(run_id)
    for ex_id in (await db.scalars(select(AiExecution.id))).all():
        await measure_service.call_ai(ex_id)
    for rid in (await db.scalars(select(AiResponse.id))).all():
        await extract_service.extract(rid)
    await finalize_service.finalize(run_id)
    db.expire_all()
    req = await db.get(FixRequest, req_id)
    assert (req.status, req.base_run_id) == ("connecting", run_id)
    plans = (await db.scalars(select(FixPlan))).all()  # 이미 연결된 Google만 정비안 만들기(E12)
    assert [(p.provider, p.status, p.base_run_id) for p in plans] == [("google", "generating", run_id)]
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 0


async def test_kakao_name_counts_as_target_without_storing_it(db: AsyncSession, maps: Any, ai: Any) -> None:
    """우리 가게 이름 후보에 카카오 다시 부르기 이름도 넣는다(코드 비교만, 저장·AI 전송 없음)."""
    maps.kakao.extras = {"명동교자": [k("K1", "교자하우스", north(10))]}
    for llm in (ai.openai, ai.gemini):
        llm.answers = lambda prompt, n: "1. 교자하우스 - famous dumplings.\n2. 을지면옥 - cold noodles."
    _, run_id = await _measured(db, name="명동교자", google_name="명동교자")
    await finalize_service.finalize(run_id)
    db.expire_all()
    assert await _metric(db, run_id, "openai", "appearance_rate") == 1.0
    target_lines = [
        line
        for c in ai.openai.calls
        if c.get("schema") == "ExtractionOut"
        for line in c["prompt"].splitlines()
        if "target places:" in line
    ]
    assert target_lines and all("교자하우스" not in line for line in target_lines)  # 답변 원문에만 있음
    comps = (await db.scalars(select(Metric.subject_name).where(Metric.subject_type == "competitor"))).all()
    assert set(comps) == {"을지면옥"}


async def test_rerun_while_parsing_replaces_metrics(db: AsyncSession, ai: Any) -> None:
    """작업이 다시 돌아도(RetryStrategy) parsing에서 이어 가고, 지표를 먼저 지워 같은 결과가 된다."""
    _, run_id = await _measured(db)
    await db.execute(text("UPDATE measurement_runs SET status = 'parsing' WHERE id = :i"), {"i": run_id})
    db.add(
        Metric(
            run_id=run_id, provider="openai", subject_type="target", subject_name="target",
            metric_name="success_count", value=999,
        )
    )  # fmt: skip
    await db.commit()
    await finalize_service.finalize(run_id)
    db.expire_all()
    assert (await db.get(MeasurementRun, run_id)).status == "completed"
    assert await _metric(db, run_id, "openai", "success_count") == 6
    count = await db.scalar(select(func.count()).select_from(Metric))
    await finalize_service.finalize(run_id)  # 끝난 측정은 다시 하지 않음
    assert await db.scalar(select(func.count()).select_from(Metric)) == count
