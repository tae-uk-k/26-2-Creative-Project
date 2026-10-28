"""W-02-3 가게 찾기(07 3장, 11 4장). 지도는 가짜 세계(maps fixture)."""

import json
import time
from datetime import timedelta
from typing import Any

import httpx
import pytest
import time_machine
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import MeasurementRun
from seelo.models.store import IdentifySession, Store, StoreSource
from seelo.services import identify_service
from seelo.timeutil import now_utc
from tests.map_world import LAT0, LNG0, g, k, n, north
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("maps")

GOOGLE_LINK = (
    "https://www.google.com/maps/place/%EB%AA%85%EB%8F%99%EA%B5%90%EC%9E%90/"
    f"@{LAT0},{LNG0},17z/data=!4m6!3m5!1s0x0:0x1!8m2!3d{LAT0}!4d{LNG0}"
)


async def _owner(client: httpx.AsyncClient, db: AsyncSession, email: str = "o@seelo.test") -> None:
    await make_user(db, email)
    assert (await login(client, email)).status_code == 200


async def _identify(c: httpx.AsyncClient, link: str, name: str = "명동교자", **kw: Any) -> httpx.Response:
    return await c.post("/api/stores/identify", json={"name": name, "link": link, "mode": "new", **kw})


async def _sources(db: AsyncSession) -> dict[str, tuple[str | None, str | None, str]]:
    db.expire_all()
    rows = (await db.scalars(select(StoreSource))).all()
    return {r.provider: (r.external_id, r.url, r.match_status) for r in rows}


async def _counts(db: AsyncSession) -> tuple[int, int, int, int]:
    db.expire_all()
    stores = await db.scalar(select(func.count()).select_from(Store))
    runs = await db.scalar(select(func.count()).select_from(MeasurementRun))
    sessions = await db.scalar(select(func.count()).select_from(IdentifySession))
    jobs = await db.scalar(text("SELECT count(*) FROM procrastinate_jobs"))
    return stores, runs, sessions, jobs


# --- Google 기준 -------------------------------------------------------------------


async def test_google_link_confirmed_with_other_maps(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.places.world = [g("G1", "명동교자 본점"), g("G9", "명동칼국수", north(30))]
    maps.kakao.world = [k("111", "명동교자 본점", north(40))]
    maps.naver.world = [n("명동교자", north(60))]

    r = await _identify(client, GOOGLE_LINK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "confirmed" and body["next"] == f"/runs/{body['runId']}"

    store = await db.get(Store, body["storeId"])
    store_id = store.id
    assert (store.name, store.status, store.category, store.input_provider) == (
        "명동교자",
        "collecting",
        "restaurant",
        "google",
    )
    assert await _sources(db) == {
        "google": ("G1", "https://maps.google.com/?cid=G1", "found"),
        "kakao": ("111", "http://place.map.kakao.com/111", "found"),
        "naver": (None, None, "found"),  # 네이버 검색 값은 저장하지 않는다
    }
    run = await db.get(MeasurementRun, body["runId"])
    assert (run.kind, run.is_free, run.trigger, run.status) == ("diagnosis", True, "initial", "queued")
    job = (await db.execute(text("SELECT task_name, queue_name, args, lock FROM procrastinate_jobs"))).one()
    assert job.task_name == "collectStore" and job.queue_name == "collect"
    assert job.args == {"store_id": store_id, "run_id": body["runId"]} and job.lock == f"store:{store_id}"
    # 가게 찾기 Text Search는 링크 이름·좌표·200m로
    assert maps.places.calls[0] == (
        "search_text",
        {"query": "명동교자", "lat": LAT0, "lng": LNG0, "radius_m": 200.0},
    )


async def test_google_place_id_link_uses_details(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.places.world = [g("ChIJ123", "명동교자")]
    link = "https://www.google.com/maps/search/?api=1&query=x&query_place_id=ChIJ123"
    r = await _identify(client, link)
    assert r.json()["result"] == "confirmed"
    assert maps.places.calls[0][0] == "details"
    assert maps.places.calls[0][1]["fields"] == (
        "id,displayName,formattedAddress,location,types,primaryType,googleMapsUri"
    )
    r = await _identify(client, "https://www.google.com/maps/search/?api=1&query=x&query_place_id=NOPE")
    assert r.status_code == 409  # 이미 가게가 있으면 변경 확인부터


async def test_google_candidates_and_select(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    await _owner(client, db)
    maps.places.world = [
        g("G1", "명동교자", north(20)),
        g("G2", "명동교자 별관", north(80), address="명동8길 1"),
    ]
    r = await _identify(client, GOOGLE_LINK)
    body = r.json()
    assert body["result"] == "candidates" and len(body["candidateToken"]) >= 40
    assert [c["candidateId"] for c in body["candidates"]] == ["google:G1", "google:G2"]
    assert body["candidates"][0] == {
        "candidateId": "google:G1",
        "name": "명동교자",
        "address": "대한민국 서울특별시 중구 명동10길 29",
        "category": "restaurant",
        "providers": ["google"],
    }
    assert await _counts(db) == (0, 0, 1, 0)

    r = await client.post(
        "/api/stores/identify/select",
        json={"candidateToken": body["candidateToken"], "candidateId": "google:G2"},
    )
    assert r.status_code == 200 and r.json()["result"] == "confirmed"
    assert (await _sources(db))["google"][0] == "G2"
    assert await _counts(db) == (1, 1, 0, 1)  # 세션은 지운다


async def test_google_outside_200m_or_other_name_not_found(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.places.world = [g("G1", "명동교자", north(250)), g("G2", "을지로 국수", north(10))]
    r = await _identify(client, GOOGLE_LINK)
    assert r.status_code == 422 and r.json()["error"]["code"] == "STORE_NOT_FOUND"
    assert await _counts(db) == (0, 0, 0, 0)


# --- 카카오 기준 ------------------------------------------------------------------


async def test_kakao_id_match_confirmed(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    await _owner(client, db)
    maps.kakao.world = [k(str(i), f"다른식당{i}", north(i)) for i in range(1, 20)] + [
        k("10332413", "명동교자")
    ]
    maps.places.world = [g("G1", "명동교자", north(50))]
    r = await _identify(client, "https://place.map.kakao.com/10332413", name="명동교자")
    assert r.json()["result"] == "confirmed", r.text
    assert (await _sources(db))["kakao"] == ("10332413", "http://place.map.kakao.com/10332413", "found")
    assert (await _sources(db))["google"][2] == "found"
    pages = [c[1]["page"] for c in maps.kakao.calls if c[1]["x"] is None]
    assert pages == [1]  # 이름이 비슷한 결과만 오므로 1쪽에서 찾음


async def test_kakao_without_id_match_gives_candidates(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.kakao.world = [
        k("1", "명동교자 본점", north(0), road="서울 중구 명동10길 29"),
        k("2", "명동교자 분점", north(500), road="서울 중구 명동길 1"),
    ]
    r = await _identify(client, "https://place.map.kakao.com/999")
    body = r.json()
    assert body["result"] == "candidates"
    assert [c["candidateId"] for c in body["candidates"]] == ["kakao:1", "kakao:2"]
    # identify_sessions에는 카카오 이름·주소를 저장하지 않는다
    sess = await db.scalar(select(IdentifySession))
    stored = json.dumps(sess.candidates, ensure_ascii=False)
    for forbidden in ("명동교자 본점", "명동교자 분점", "명동10길", "명동길 1", "02-776-5348"):
        assert forbidden not in stored
    assert sess.candidates[0] == {
        "candidateId": "kakao:1",
        "provider": "kakao",
        "externalId": "1",
        "fingerprint": None,
    }

    r = await client.post(
        "/api/stores/identify/select",
        json={"candidateToken": body["candidateToken"], "candidateId": "kakao:2"},
    )
    assert r.status_code == 200
    assert (await _sources(db))["kakao"][0] == "2"


async def test_kakao_nothing_is_store_not_found(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.kakao.world = [k("1", "을지로 국수")]
    r = await _identify(client, "https://place.map.kakao.com/999")
    assert r.status_code == 422 and r.json()["error"]["code"] == "STORE_NOT_FOUND"


# --- 네이버 기준 ------------------------------------------------------------------


async def test_naver_exact_one_confirmed_keeps_link_number(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.naver.world = [n("명동교자"), n("명동교자칼국수", north(300))]
    link = "https://map.naver.com/p/entry/place/11679241?c=15.00"
    r = await _identify(client, link)
    assert r.json()["result"] == "confirmed", r.text
    assert (await _sources(db))["naver"] == ("11679241", link, "found")


async def test_naver_two_exact_gives_candidates_by_fingerprint(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.naver.world = [
        n("명동교자", road="서울특별시 중구 명동10길 29"),
        n("명동교자", north(400), road="서울 중구 명동길 1"),
    ]
    r = await _identify(client, "https://m.place.naver.com/restaurant/11679241/home")
    body = r.json()
    assert body["result"] == "candidates"
    assert [c["candidateId"] for c in body["candidates"]] == ["naver:0", "naver:1"]
    sess = await db.scalar(select(IdentifySession))
    assert all(c["externalId"] is None and len(c["fingerprint"]) == 64 for c in sess.candidates)
    assert "명동10길" not in json.dumps(sess.candidates, ensure_ascii=False)
    r = await client.post(
        "/api/stores/identify/select",
        json={"candidateToken": body["candidateToken"], "candidateId": "naver:1"},
    )
    assert r.status_code == 200
    store = await db.scalar(select(Store))
    assert store.input_provider == "naver"


async def test_naver_none_is_store_not_found(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    await _owner(client, db)
    r = await _identify(client, "https://map.naver.com/p/entry/place/1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "STORE_NOT_FOUND"


# --- 다른 지도 판정(100m·이름) ------------------------------------------------------


@pytest.mark.parametrize(("meters", "status"), [(99, "found"), (101, "not_found")])
async def test_other_map_100m_rule(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, meters: int, status: str
) -> None:
    await _owner(client, db)
    maps.places.world = [g("G1", "명동교자")]
    maps.kakao.world = [k("1", "명동교자", north(meters))]
    maps.naver.world = [n("명동칼국수", north(5))]  # 가깝지만 이름이 다름
    await _identify(client, GOOGLE_LINK)
    sources = await _sources(db)
    assert sources["kakao"][2] == status
    assert sources["naver"][2] == "not_found"


async def test_other_map_retries_with_input_name(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.places.world = [g("G1", "Myeongdong Kyoja")]
    maps.kakao.world = [k("1", "명동교자", north(10))]
    link = (
        "https://www.google.com/maps/place/Myeongdong+Kyoja/" + f"@{LAT0},{LNG0},17z/data=!3d{LAT0}!4d{LNG0}"
    )
    r = await _identify(client, link, name="명동교자")
    assert r.json()["result"] == "confirmed", r.text
    assert (await _sources(db))["kakao"][2] == "found"
    queries = [c[1]["query"] for c in maps.kakao.calls]
    assert queries == ["Myeongdong Kyoja", "명동교자"]


async def test_other_map_error_is_not_found_and_continues(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.places.world = [g("G1", "명동교자")]
    maps.kakao.world = [k("1", "명동교자", north(10))]
    maps.naver.world = [n("명동교자", north(10))]
    maps.kakao.fail_next(1, "5xx")
    maps.naver.fail_next(2, "timeout")
    r = await _identify(client, GOOGLE_LINK)
    assert r.json()["result"] == "confirmed"
    sources = await _sources(db)
    assert sources["kakao"][2] == "not_found"  # 오류는 로그만 남기고 not_found(07 3.3)
    assert sources["naver"][2] == "not_found"


# --- 시간 초과·오류 → 503, 저장 0건 ----------------------------------------------------


async def test_base_map_hang_is_503_within_limit_and_saves_nothing(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _owner(client, db)
    monkeypatch.setattr(identify_service, "IDENTIFY_TIMEOUT_S", 1.0)  # 운영 10초를 1초로 줄여 시험
    maps.places.fail_next(1, "hang")
    started = time.monotonic()
    r = await _identify(client, GOOGLE_LINK)
    assert time.monotonic() - started < 3
    assert r.status_code == 503 and r.json()["error"]["code"] == "TRY_LATER"
    assert await _counts(db) == (0, 0, 0, 0)


async def test_other_map_hang_is_cut_at_5s_per_map(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _owner(client, db)
    monkeypatch.setattr(identify_service, "MAP_API_TIMEOUT_S", 0.5)
    maps.places.world = [g("G1", "명동교자")]
    maps.naver.world = [n("명동교자", north(10))]
    maps.kakao.fail_next(1, "hang")
    r = await _identify(client, GOOGLE_LINK)
    assert r.json()["result"] == "confirmed"
    assert (await _sources(db))["kakao"][2] == "not_found"


@pytest.mark.parametrize("kind", ["5xx", "timeout"])
async def test_base_map_error_is_503(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, kind: str
) -> None:
    await _owner(client, db)
    maps.kakao.fail_next(1, kind)
    r = await _identify(client, "https://place.map.kakao.com/1")
    assert r.status_code == 503
    assert await _counts(db) == (0, 0, 0, 0)


# --- 링크·업종·후보 만료 --------------------------------------------------------------


async def test_short_link_is_resolved_then_identified(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.short_links.mapping = {"https://kko.to/AbC": "https://place.map.kakao.com/77"}
    maps.kakao.world = [k("77", "명동교자")]
    r = await _identify(client, "[카카오맵] 명동교자\nkko.to/AbC")
    assert r.json()["result"] == "confirmed", r.text
    assert maps.short_links.calls == ["https://kko.to/AbC"]
    r2 = await _identify(client, "https://naver.me/unknown", confirmReplace=True)
    assert r2.status_code == 422 and r2.json()["error"]["code"] == "LINK_UNRESOLVED"


@pytest.mark.parametrize(
    ("link", "code"),
    [("가게 이름만", "NO_LINK"), ("https://www.instagram.com/myeongdongkyoja", "UNSUPPORTED_LINK")],
)
async def test_link_errors(client: httpx.AsyncClient, db: AsyncSession, link: str, code: str) -> None:
    await _owner(client, db)
    r = await _identify(client, link)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


async def test_not_target_category(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    await _owner(client, db)
    maps.kakao.world = [k("5", "명동헤어", code="", category="미용 > 미용실")]
    r = await _identify(client, "https://place.map.kakao.com/5", name="명동헤어")
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_TARGET_CATEGORY"
    assert await _counts(db) == (0, 0, 0, 0)


async def test_candidate_expired_after_30_minutes(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.kakao.world = [k("1", "명동교자 본점"), k("2", "명동교자 분점", north(500))]
    body = (await _identify(client, "https://place.map.kakao.com/999")).json()
    payload = {"candidateToken": body["candidateToken"], "candidateId": "kakao:1"}
    with time_machine.travel(now_utc() + timedelta(minutes=31), tick=True):
        r = await client.post("/api/stores/identify/select", json=payload)
    assert r.status_code == 410 and r.json()["error"]["code"] == "CANDIDATE_EXPIRED"
    r = await client.post("/api/stores/identify/select", json={**payload, "candidateId": "kakao:9"})
    assert r.status_code == 410
    r = await client.post("/api/stores/identify/select", json={**payload, "candidateToken": "x" * 43})
    assert r.status_code == 410


async def test_candidate_gone_on_reload_is_410(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    await _owner(client, db)
    maps.kakao.world = [k("1", "명동교자 본점"), k("2", "명동교자 분점", north(500))]
    body = (await _identify(client, "https://place.map.kakao.com/999")).json()
    maps.kakao.world = [k("1", "명동교자 본점")]  # 그 사이 2번이 사라짐
    r = await client.post(
        "/api/stores/identify/select",
        json={"candidateToken": body["candidateToken"], "candidateId": "kakao:2"},
    )
    assert r.status_code == 410


async def test_identify_rate_limit_per_user(
    client: httpx.AsyncClient, db: AsyncSession, frozen_time: Any
) -> None:
    await _owner(client, db)
    for _ in range(10):
        assert (await _identify(client, "가게 이름만")).status_code == 422
    r = await _identify(client, "가게 이름만")
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
