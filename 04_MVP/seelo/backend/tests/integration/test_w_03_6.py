"""W-03-6 모은 정보 표 GET /api/runs/{runId}/collected(07 7장)와 purgeSnapshots(06 5장)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import JobLink
from seelo.models.store import SourceSnapshot, StoreSource
from seelo.services import collect_service
from seelo.timeutil import now_utc
from tests.map_world import G_EN, g_detail, k, n, north, seed_store
from tests.support import login

pytestmark = pytest.mark.usefixtures("queue_app")

SITE = "https://kyoja.example"


async def _collected_store(db: AsyncSession, maps: Any, web: Any) -> tuple[int, int]:
    maps.places.world = [g_detail("G1", "명동교자", websiteUri=f"{SITE}/")]
    maps.places.english = {"G1": G_EN}
    maps.kakao.world = [k("K1", "명동교자", north(30), category="음식점 > 한식 > 국수")]
    maps.naver.world = [
        n("명동교자 본점", north(40), category="한식>칼국수,만두") | {"link": "https://naver.example/"}
    ]
    web.server.robots(SITE, "")
    web.server.html(f"{SITE}/", '<html lang="en"><body><a href="/menu">메뉴</a></body></html>')
    web.server.html(f"{SITE}/menu", "<p>메뉴</p>")
    store_id, run_id = await seed_store(db)
    await collect_service.collect_store(store_id, run_id)
    return store_id, run_id


async def test_collected_table(client: httpx.AsyncClient, db: AsyncSession, maps: Any, web: Any) -> None:
    _, run_id = await _collected_store(db, maps, web)
    assert (await login(client, "owner@seelo.test")).status_code == 200
    r = await client.get(f"/api/runs/{run_id}/collected")
    assert r.status_code == 200, r.text
    rows = {row["key"]: (row["label"], row["values"]) for row in r.json()["rows"]}
    assert list(rows) == [
        "name",
        "address",
        "phone",
        "hours",
        "website",
        "price",
        "category",
        "menu",
        "intro",
        "amenities",
    ]  # fmt: skip  — 인스타그램 없음 → 행 없음
    assert rows["name"] == (
        "가게 이름",
        {
            "google": "명동교자",
            "kakao": "명동교자",
            "naver": "명동교자 본점",
            "website": None,
            "instagram": None,
        },
    )
    assert rows["address"][1] == {
        "google": "대한민국 서울특별시 중구 명동10길 29",
        "kakao": "서울 중구 명동10길 29",
        "naver": "서울특별시 중구 명동10길 29",
        "website": "서울 중구 명동10길 29",
        "instagram": None,
    }
    assert rows["phone"][1]["naver"] is None  # 네이버 API는 전화번호를 주지 않는다
    assert rows["hours"][1]["google"] == "월요일: 오전 10:30~오후 9:00"
    assert rows["hours"][1]["website"] == "매일 11:00~21:00 (브레이크 15:00~17:00)"
    assert rows["website"][1] == {
        "google": f"{SITE}/",
        "kakao": None,
        "naver": "https://naver.example/",
        "website": f"{SITE}/",
        "instagram": None,
    }
    assert rows["price"][1]["google"] == "저렴" and rows["price"][1]["website"] == "10,000원~11,000원"
    assert rows["category"][1] == {
        "google": "한식당",
        "kakao": "국수",
        "naver": "한식>칼국수,만두",
        "website": None,
        "instagram": None,
    }
    assert rows["menu"][1]["website"] == "칼국수 11,000원, 만두 10,000원"
    assert rows["amenities"][1]["google"] == "포장 가능"
    assert rows["amenities"][1]["website"] == "영문 페이지 있음"

    # 카카오·네이버가 실패하면 그 열만 빈다
    maps.kakao.fail_next(1, "5xx")
    maps.naver.fail_next(1, "5xx")
    rows2 = {
        row["key"]: row["values"]
        for row in (await client.get(f"/api/runs/{run_id}/collected")).json()["rows"]
    }
    assert rows2["name"]["kakao"] is None and rows2["name"]["naver"] is None
    assert rows2["name"]["google"] == "명동교자"


async def test_store_summary_address_from_google_snapshot(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, web: Any
) -> None:
    """수집 뒤 가게 요약 주소는 Google 스냅샷(ko.formattedAddress). 카카오를 다시 부르지 않는다."""
    await _collected_store(db, maps, web)
    await login(client, "owner@seelo.test")
    calls_before = len(maps.kakao.calls)
    store = (await client.get("/api/stores/current")).json()["store"]
    assert store["address"] == "대한민국 서울특별시 중구 명동10길 29"
    assert store["status"] == "measuring"
    assert store["sources"]["website"] == "found"
    assert len(maps.kakao.calls) == calls_before


async def test_collected_is_owner_only(make_client: Any, db: AsyncSession, maps: Any, web: Any) -> None:
    from tests.support import make_user

    _, run_id = await _collected_store(db, maps, web)
    other = await make_client()
    await make_user(db, "other@seelo.test")
    await login(other, "other@seelo.test")
    assert (await other.get(f"/api/runs/{run_id}/collected")).status_code == 404
    assert (await other.get("/api/runs/999999/collected")).status_code == 404
    anon = await make_client()
    assert (await anon.get(f"/api/runs/{run_id}/collected")).status_code == 401


async def test_purge_expired_snapshots_and_orphan_links(db: AsyncSession, maps: Any) -> None:
    store_id, run_id = await seed_store(db)
    source_id = await db.scalar(select(StoreSource.id).where(StoreSource.provider == "google"))
    now = now_utc()
    db.add_all(
        [
            SourceSnapshot(source_id=source_id, store_id=store_id, provider="google", status="ok", payload={},
                           expires_at=now - timedelta(seconds=1)),
            SourceSnapshot(source_id=source_id, store_id=store_id, provider="google", status="ok", payload={},
                           expires_at=now + timedelta(days=1)),
            JobLink(procrastinate_job_id=987654, task_name="collectStore", store_id=store_id),
        ]
    )  # fmt: skip
    await db.execute(
        text(
            "INSERT INTO web_evidence (store_id, run_id, provider, site_url, fields, expires_at) "
            "VALUES (:s, :r, 'openai', 'https://x.example', '{}', now() - interval '1 day')"
        ),
        {"s": store_id, "r": run_id},
    )
    await db.commit()
    counts = await collect_service.purge_expired(db)
    await db.commit()
    assert counts == {"snapshots": 1, "web_evidence": 1, "job_links": 1}
    assert await db.scalar(select(func.count()).select_from(SourceSnapshot)) == 1


def test_purge_task_registered_daily_kst_0330() -> None:
    import seelo.worker.periodic  # noqa: F401  작업 모듈을 불러야 주기 작업이 등록된다
    from seelo.worker.app import app

    periodic = {t.task.name: t.cron for t in app.periodic_registry.periodic_tasks.values()}
    assert periodic["purgeSnapshots"] == "30 18 * * *"
