"""W-03-1 Google 상세 수집과 collectStore 흐름(07 6.1·6.2·6.6, 03 E2·E3, 11 4장)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import MeasurementRun
from seelo.models.ops import EmailLog
from seelo.models.store import SourceSnapshot, Store
from seelo.services import collect_service
from seelo.timeutil import now_utc
from tests.map_world import G_EN, g_detail, k, n, north, seed_store

pytestmark = pytest.mark.usefixtures("queue_app", "web")


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect_service, "GOOGLE_RETRY_DELAY_S", 0)


def _world(maps: Any, **google: Any) -> None:
    maps.places.world = [g_detail("G1", "명동교자", **google)]
    maps.places.english = {"G1": G_EN}
    maps.kakao.world = [k("K1", "명동교자", north(30))]
    maps.naver.world = [n("명동교자 본점", north(40))]


async def _snaps(db: AsyncSession) -> dict[str, SourceSnapshot]:
    db.expire_all()
    return {s.provider: s for s in (await db.scalars(select(SourceSnapshot)))}


async def _jobs(db: AsyncSession) -> list[tuple[str, dict]]:
    return [
        (r[0], r[1])
        for r in await db.execute(text("SELECT task_name, args FROM procrastinate_jobs ORDER BY id"))
    ]


async def test_google_snapshot_mapping_and_e2(db: AsyncSession, maps: Any) -> None:
    _world(maps)
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)

    snap = (await _snaps(db))["google"]
    assert snap.status == "ok" and snap.run_id == run_id and snap.error_code is None
    assert snap.payload["photoCount"] == 3
    assert "photos" not in snap.payload["ko"]  # 사진 목록은 저장하지 않는다
    assert snap.payload["ko"]["nationalPhoneNumber"] == "02-776-5348"
    assert snap.payload["ko"]["regularOpeningHours"]["periods"][0]["open"] == {
        "day": 0,
        "hour": 10,
        "minute": 30,
    }
    assert snap.payload["en"]["displayName"]["text"] == "Myeongdong Kyoja"
    assert timedelta(days=29, hours=23) < snap.expires_at - now_utc() <= timedelta(days=30)
    # 한국어는 상세 필드 전체, 영문은 이름·주소 구성요소만
    details = [c[1] for c in maps.places.calls if c[0] == "details"]
    assert {d["language"] for d in details} == {"ko", "en"}
    assert next(d for d in details if d["language"] == "en")["fields"] == "displayName,addressComponents"
    assert "servesVegetarianFood" in next(d for d in details if d["language"] == "ko")["fields"]

    # E2(진단): 가게 measuring, 단계 generating_questions, generateQuestions 등록
    store = await db.get(Store, store_id)
    run = await db.get(MeasurementRun, run_id)
    assert store.status == "measuring"
    assert (run.status, run.stage) == ("running", "generating_questions") and run.started_at is not None
    assert await _jobs(db) == [("generateQuestions", {"run_id": run_id})]


async def test_google_failure_retried_once_then_failed_others_saved(
    db: AsyncSession, maps: Any, web: Any
) -> None:
    _world(maps)
    maps.naver.world = [n("명동교자 본점", north(40)) | {"link": "https://kyoja.example/"}]
    web.server.robots("https://kyoja.example", "User-agent: *\nAllow: /")
    web.server.html("https://kyoja.example/", "<html><body><p>명동교자</p></body></html>")
    maps.places.fail_next(4, "5xx")  # 1번째 시도(한국어·영문) + 다시 시도(한국어·영문)
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)

    snaps = await _snaps(db)
    assert snaps["google"].status == "failed" and snaps["google"].error_code == "http_503"
    assert snaps["google"].payload is None
    assert len([c for c in maps.places.calls if c[0] == "details"]) == 4  # 정확히 1번 다시 시도
    # 웹사이트는 네이버 link로 계속 수집(나머지 출처는 저장)
    assert snaps["website"].status == "ok" and snaps["website"].payload["url"] == "https://kyoja.example/"
    # 지역은 카카오 다시 부르기 주소로 얻어 E2
    assert (await db.get(Store, store_id)).status == "measuring"


async def test_google_retry_succeeds(db: AsyncSession, maps: Any) -> None:
    _world(maps)
    maps.places.fail_next(2, "timeout")
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)
    assert (await _snaps(db))["google"].status == "ok"


async def test_google_not_found_makes_no_snapshot(db: AsyncSession, maps: Any) -> None:
    _world(maps)
    store_id, run_id = await seed_store(db, google_id=None)
    await collect_service.collect_store(store_id, run_id)
    assert "google" not in await _snaps(db)
    assert not [c for c in maps.places.calls if c[0] == "details"]


async def test_no_region_is_e3(db: AsyncSession, maps: Any) -> None:
    _world(maps, addressComponents=[{"longText": "대한민국", "types": ["country"]}])
    maps.places.english = {}
    maps.kakao.world = [k("K1", "명동교자", north(30)) | {"address_name": "서울"}]
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)

    run = await db.get(MeasurementRun, run_id)
    assert (run.status, run.failure_reason) == ("failed", "collect_insufficient")
    assert (await db.get(Store, store_id)).status == "measure_failed"
    mail = await db.scalar(select(EmailLog))
    assert (mail.type, mail.template_params, mail.dedupe_key) == (
        "diagnosis_result",
        {"result": "failed", "run_id": run_id},
        f"diagnosis_result:{run_id}",
    )
    assert [t for t, _ in await _jobs(db)] == ["sendEmail"]  # 질문 생성은 등록하지 않는다


async def test_region_from_kakao_when_google_missing(db: AsyncSession, maps: Any) -> None:
    _world(maps)
    store_id, run_id = await seed_store(db, google_id=None)
    await collect_service.collect_store(store_id, run_id)
    assert (await db.get(Store, store_id)).status == "measuring"


async def test_free_used_store_becomes_collected(db: AsyncSession, maps: Any) -> None:
    _world(maps)
    store_id, _ = await seed_store(db, with_run=False)
    await collect_service.collect_store(store_id, None)
    assert (await db.get(Store, store_id)).status == "collected"
    snap = (await _snaps(db))["google"]
    assert snap.status == "ok" and snap.run_id is None
    assert await _jobs(db) == []


async def test_remeasure_skips_region_and_registers_run_measurement(db: AsyncSession, maps: Any) -> None:
    _world(maps, addressComponents=[])
    store_id, run_id = await seed_store(db, kind="remeasure")
    await db.execute(text("UPDATE stores SET status = 'diagnosed' WHERE id = :i"), {"i": store_id})
    await db.commit()
    await collect_service.collect_store(store_id, run_id)
    run = await db.get(MeasurementRun, run_id)
    assert run.stage == "calling_ai"
    assert (await db.get(Store, store_id)).status == "diagnosed"  # 재측정은 가게 상태를 바꾸지 않는다
    assert await _jobs(db) == [("runMeasurement", {"run_id": run_id})]


@pytest.mark.parametrize("state", ["canceled", "archived"])
async def test_skips_canceled_run_or_archived_store(db: AsyncSession, maps: Any, state: str) -> None:
    _world(maps)
    store_id, run_id = await seed_store(db)
    if state == "canceled":
        await db.execute(text("UPDATE measurement_runs SET status = 'canceled' WHERE id = :i"), {"i": run_id})
    else:
        await db.execute(
            text("UPDATE stores SET status = 'archived', archived_at = now() WHERE id = :i"), {"i": store_id}
        )
    await db.commit()
    await collect_service.collect_store(store_id, run_id)
    assert maps.places.calls == []
    assert await _snaps(db) == {}


async def test_overall_timeout_moves_on_with_what_was_saved(
    db: AsyncSession, maps: Any, web: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collect_service, "COLLECT_TIMEOUT_S", 1.0)
    _world(maps, websiteUri="https://slow.example/")
    web.server.robots("https://slow.example", "")
    web.server.html("https://slow.example/", "<p>x</p>")
    web.server.delays["https://slow.example/"] = 5
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)
    snaps = await _snaps(db)
    assert snaps["google"].status == "ok"
    assert "website" not in snaps  # 끊긴 출처는 없음
    assert (await db.get(Store, store_id)).status == "measuring"  # 그래도 다음 단계로
