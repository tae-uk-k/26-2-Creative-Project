"""W-02-5 가게 1개·변경(03 E1·E27·E28, 07 3.1, 11 4장)."""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import AuditLog
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger, User
from seelo.security.tokens import email_hmac
from seelo.services import jobs
from seelo.worker.tasks_email import send_email
from tests.map_world import g, k, n, north
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("maps")

KAKAO_A = "https://place.map.kakao.com/100"
KAKAO_B = "https://place.map.kakao.com/200"


def _world(maps: Any) -> None:
    maps.kakao.world = [k("100", "가게에이"), k("200", "가게비", north(2000))]
    maps.places.world = [g("GA", "가게에이", north(20))]
    maps.naver.world = [n("가게에이", north(30))]


async def _owner(client: httpx.AsyncClient, db: AsyncSession, email: str = "o@seelo.test") -> int:
    user = await make_user(db, email)
    user_id = user.id
    assert (await login(client, email)).status_code == 200
    return user_id


async def _identify(c: httpx.AsyncClient, link: str, name: str, **kw: Any) -> httpx.Response:
    return await c.post("/api/stores/identify", json={"name": name, "link": link, "mode": "change", **kw})


def _store(owner_id: int, name: str, status: str = "diagnosed", archived: bool = False) -> Store:
    from seelo.timeutil import now_utc

    return Store(
        owner_id=owner_id,
        name=name,
        input_url=KAKAO_A,
        input_provider="kakao",
        category="restaurant",
        status="archived" if archived else status,
        archived_at=now_utc() if archived else None,
    )


async def test_two_active_stores_violate_partial_unique_index(db: AsyncSession) -> None:
    owner = await make_user(db, "u@seelo.test")
    owner_id = owner.id
    db.add_all([_store(owner_id, "보관1", archived=True), _store(owner_id, "보관2", archived=True)])
    db.add(_store(owner_id, "지금"))
    await db.commit()  # 보관한 가게는 여러 개여도 된다
    db.add(_store(owner_id, "하나 더"))
    with pytest.raises(IntegrityError) as e:
        await db.flush()
    assert "uq_store_owner_active" in str(e.value)
    await db.rollback()


async def test_case_free_unused_creates_free_run(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    _world(maps)
    await _owner(client, db)
    r = await _identify(client, KAKAO_A, "가게에이")
    body = r.json()
    assert body["runId"] is not None and body["next"] == f"/runs/{body['runId']}"
    run = await db.get(MeasurementRun, body["runId"])
    assert run.is_free is True


async def test_case_free_used_creates_no_run(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    _world(maps)
    await _owner(client, db)
    db.add(FreeUsageLedger(email_hash=email_hmac("o@seelo.test")))
    await db.commit()
    r = await _identify(client, KAKAO_A, "가게에이")
    body = r.json()
    assert body == {"result": "confirmed", "storeId": body["storeId"], "runId": None, "next": "/home"}
    assert await db.scalar(select(func.count()).select_from(MeasurementRun)) == 0
    args = await db.scalar(text("SELECT args FROM procrastinate_jobs"))
    assert args == {"store_id": body["storeId"], "run_id": None}


async def test_case_measuring_change_needs_confirm_then_archives_and_cancels(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    _world(maps)
    user_id = await _owner(client, db)
    first = (await _identify(client, KAKAO_A, "가게에이")).json()
    old_store, old_run = first["storeId"], first["runId"]
    await db.execute(text("UPDATE stores SET status = 'measuring' WHERE id = :i"), {"i": old_store})
    await db.execute(text("UPDATE measurement_runs SET status = 'running' WHERE id = :i"), {"i": old_run})
    # 진행 중인 다른 작업 하나(가게에 연결)
    extra_job = await jobs.defer(
        db, send_email, args={"email_log_id": 0}, links=jobs.JobLinks(store_id=old_store), queueing_lock="x"
    )
    await db.commit()

    r = await _identify(client, KAKAO_B, "가게비")
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "CONFIRM_REPLACE_REQUIRED",
        "message": "가게를 바꾸면 지금 가게의 결과는 지난 기록으로 옮겨져요",
        "details": {"usedFree": False},
    }
    r = await _identify(client, KAKAO_B, "가게비", confirmReplace=True)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["runId"] is not None  # 무료를 다 쓰지 않았으니(측정 중 취소) 새 가게도 무료 측정

    db.expire_all()
    old = await db.get(Store, old_store)
    assert old.status == "archived" and old.archived_at is not None
    assert (await db.get(MeasurementRun, old_run)).status == "canceled"
    statuses = dict((await db.execute(text("SELECT id, status FROM procrastinate_jobs"))).all())
    assert statuses[extra_job] == "cancelled"
    active = (
        await db.scalars(select(Store.id).where(Store.owner_id == user_id, Store.archived_at.is_(None)))
    ).all()
    assert active == [new["storeId"]]
    audit = await db.scalar(select(AuditLog))
    assert (audit.action, audit.actor_id, audit.target_id, audit.detail) == (
        "store.change",
        user_id,
        old_store,
        {"newStoreId": new["storeId"]},
    )

    hist = (await client.get("/api/stores/history")).json()["stores"]
    assert [(h["storeId"], h["name"], h["diagnosisRunId"], h["reportId"]) for h in hist] == [
        (old_store, "가게에이", None, None)
    ]
    assert hist[0]["archivedAt"].endswith("Z") or "+" in hist[0]["archivedAt"]


async def test_used_free_flag_on_confirm_replace(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    _world(maps)
    await _owner(client, db)
    await _identify(client, KAKAO_A, "가게에이")
    db.add(FreeUsageLedger(email_hash=email_hmac("o@seelo.test")))
    await db.commit()
    r = await _identify(client, KAKAO_B, "가게비")
    assert r.json()["error"]["details"] == {"usedFree": True}


@pytest.mark.parametrize("status", ["requested", "approved", "fixing", "remeasure_scheduled"])
async def test_case_active_request_blocks_change(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any, status: str
) -> None:
    _world(maps)
    user_id = await _owner(client, db)
    store_id = (await _identify(client, KAKAO_A, "가게에이")).json()["storeId"]
    db.add(FixRequest(user_id=user_id, store_id=store_id, status=status))
    await db.commit()
    r = await _identify(client, KAKAO_B, "가게비", confirmReplace=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "FIX_IN_PROGRESS"
    db.expire_all()
    assert (await db.get(Store, store_id)).archived_at is None


async def test_finished_request_allows_change(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    _world(maps)
    user_id = await _owner(client, db)
    store_id = (await _identify(client, KAKAO_A, "가게에이")).json()["storeId"]
    db.add(FixRequest(user_id=user_id, store_id=store_id, status="rejected", reject_reason="확인 필요"))
    await db.commit()
    r = await _identify(client, KAKAO_B, "가게비", confirmReplace=True)
    assert r.status_code == 200


async def test_select_also_blocked_by_active_request(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    _world(maps)
    maps.kakao.world += [k("301", "가게씨 본점", north(5000)), k("302", "가게씨 분점", north(6000))]
    user_id = await _owner(client, db)
    store_id = (await _identify(client, KAKAO_A, "가게에이")).json()["storeId"]
    body = (await _identify(client, "https://place.map.kakao.com/999", "가게씨", confirmReplace=True)).json()
    assert body["result"] == "candidates"
    db.add(FixRequest(user_id=user_id, store_id=store_id, status="requested"))
    await db.commit()
    r = await client.post(
        "/api/stores/identify/select",
        json={"candidateToken": body["candidateToken"], "candidateId": "kakao:301"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "FIX_IN_PROGRESS"


# --- 현재 가게·[내 가게가 아니에요] ---------------------------------------------------------


async def test_current_store_summary(client: httpx.AsyncClient, db: AsyncSession, maps: Any) -> None:
    _world(maps)
    await _owner(client, db)
    assert (await client.get("/api/stores/current")).json() == {"store": None}
    store_id = (await _identify(client, KAKAO_A, "가게에이")).json()["storeId"]
    r = await client.get("/api/stores/current")
    assert r.json() == {
        "store": {
            "id": store_id,
            "name": "가게에이",
            "address": "서울 중구 명동10길 29",  # Google 스냅샷이 없으니 카카오를 다시 불러온 값(저장 안 함)
            "category": "restaurant",
            "status": "collecting",
            "sources": {
                "google": "found",
                "kakao": "found",
                "naver": "found",
                "website": "not_found",
                "instagram": "not_found",
            },
        }
    }
    maps.kakao.fail_next(1, "5xx")
    assert (await client.get("/api/stores/current")).json()["store"]["address"] is None  # 불러오지 못함


async def test_not_mine_deletes_store_and_cancels_jobs(make_client: Any, db: AsyncSession, maps: Any) -> None:
    _world(maps)
    c = await make_client()
    await _owner(c, db)
    body = (await _identify(c, KAKAO_A, "가게에이")).json()

    other = await make_client()
    await _owner(other, db, "other@seelo.test")
    r = await other.post("/api/stores/current/not-mine", json={"runId": body["runId"]})
    assert r.status_code == 404  # 남의 측정

    r = await c.post("/api/stores/current/not-mine", json={"runId": body["runId"]})
    assert r.status_code == 204
    db.expire_all()
    assert await db.scalar(select(func.count()).select_from(Store)) == 0
    assert await db.scalar(select(func.count()).select_from(MeasurementRun)) == 0
    assert await db.scalar(text("SELECT status FROM procrastinate_jobs")) == "cancelled"
    assert (await c.get("/api/stores/current")).json() == {"store": None}


async def test_not_mine_refused_after_completed_run(
    client: httpx.AsyncClient, db: AsyncSession, maps: Any
) -> None:
    _world(maps)
    await _owner(client, db)
    body = (await _identify(client, KAKAO_A, "가게에이")).json()
    await db.execute(
        text("UPDATE measurement_runs SET status = 'completed' WHERE id = :i"), {"i": body["runId"]}
    )
    await db.commit()
    r = await client.post("/api/stores/current/not-mine", json={"runId": body["runId"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    assert await db.scalar(select(func.count()).select_from(User)) == 1
