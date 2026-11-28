"""W-08-1 정비 신청(09 1장, 03 E8·E26, 04 7.1).

진행 중·완료 신청이 있는 가게 새 신청 409, 거절 뒤 새 신청 허용, 동시 신청 2개 중 1개만,
허용되지 않는 전이 409, S12 상태(steps), 재측정 다시 시도(E26).
"""

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import EmailLog
from tests.map_world import seed_store
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
OWNER = "owner@seelo.test"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(ADMIN_NOTIFY_EMAILS="ops@seelo.test")


async def _store(
    db: AsyncSession, status: str = "diagnosed", *, completed_run: bool = True
) -> tuple[int, int]:
    store_id, run_id = await seed_store(db)
    await db.execute(text("UPDATE stores SET status = :s WHERE id = :i"), {"s": status, "i": store_id})
    if completed_run:
        await db.execute(
            text("UPDATE measurement_runs SET status = 'completed' WHERE id = :i"), {"i": run_id}
        )
    await db.commit()
    return store_id, run_id


async def _requests(db: AsyncSession) -> list[FixRequest]:
    db.expire_all()
    return list((await db.scalars(select(FixRequest).order_by(FixRequest.id))).all())


async def test_no_store_and_not_eligible(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "nostore@seelo.test")
    await login(client, "nostore@seelo.test")
    r = await client.post("/api/fix/requests")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_STORE"
    await _store(db, "measuring", completed_run=False)
    await login(client, OWNER)
    r = await client.post("/api/fix/requests")
    assert r.status_code == 409 and r.json()["error"] == {
        "code": "NOT_ELIGIBLE",
        "message": "지금은 자동 정비를 신청할 수 없어요",
        "details": {"reason": "store_not_ready"},
    }


async def test_request_sets_base_run_and_mails_admin(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, run_id = await _store(db)
    await login(client, OWNER)
    state = (await client.get("/api/fix/requests/current")).json()
    assert state == {"request": None, "canRequest": True, "needsMeasurementFirst": False}
    r = await client.post("/api/fix/requests")
    assert r.status_code == 201, r.text
    (req,) = await _requests(db)
    assert r.json() == {"requestId": req.id}
    assert (req.status, req.store_id, req.base_run_id) == ("requested", store_id, run_id)
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "fix_requested"))
    assert mail.to_email == "ops@seelo.test" and mail.template_params == {
        "request_id": req.id,
        "store_name": "명동교자",
    }
    state = (await client.get("/api/fix/requests/current")).json()
    assert state["canRequest"] is False and state["request"]["status"] == "requested"
    assert state["request"]["hasBaseRun"] is True
    assert [s["state"] for s in state["request"]["steps"]][:2] == ["done", "current"]


async def test_collected_store_has_no_base_run(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _store(db, "collected", completed_run=False)
    await login(client, OWNER)
    assert (await client.get("/api/fix/requests/current")).json()["needsMeasurementFirst"] is True
    assert (await client.post("/api/fix/requests")).status_code == 201
    (req,) = await _requests(db)
    assert req.base_run_id is None
    state = (await client.get("/api/fix/requests/current")).json()
    assert state["request"]["hasBaseRun"] is False


@pytest.mark.parametrize("status", ["requested", "approved", "connecting", "report_ready"])
async def test_open_or_done_request_blocks_new(
    client: httpx.AsyncClient, db: AsyncSession, status: str
) -> None:
    store_id, _ = await _store(db)
    owner_id = await db.scalar(text("SELECT owner_id FROM stores WHERE id = :i"), {"i": store_id})
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status=status))
    await db.commit()
    await login(client, OWNER)
    r = await client.post("/api/fix/requests")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_REQUESTED"


async def test_new_request_allowed_after_rejection(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, _ = await _store(db)
    owner_id = await db.scalar(text("SELECT owner_id FROM stores WHERE id = :i"), {"i": store_id})
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="rejected", reject_reason="지역 밖"))
    await db.commit()
    await login(client, OWNER)
    state = (await client.get("/api/fix/requests/current")).json()
    assert state["canRequest"] is True and state["request"]["status"] == "rejected"
    assert state["request"]["rejectReason"] == "지역 밖"
    assert (await client.post("/api/fix/requests")).status_code == 201
    assert [r.status for r in await _requests(db)] == ["rejected", "requested"]


async def test_concurrent_requests_only_one(make_client: Any, db: AsyncSession) -> None:
    await _store(db)
    c1, c2 = await make_client(), await make_client()
    await login(c1, OWNER)
    await login(c2, OWNER)
    r1, r2 = await asyncio.gather(c1.post("/api/fix/requests"), c2.post("/api/fix/requests"))
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]
    assert len(await _requests(db)) == 1


async def test_partial_unique_index_blocks_second_active(db: AsyncSession) -> None:
    store_id, _ = await _store(db)
    owner_id = await db.scalar(text("SELECT owner_id FROM stores WHERE id = :i"), {"i": store_id})
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="requested"))
    await db.commit()
    db.add(FixRequest(user_id=owner_id, store_id=store_id, status="connecting"))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def _remeasure_failed(db: AsyncSession) -> tuple[int, int, int]:
    store_id, base_run = await _store(db)
    await db.execute(
        text("UPDATE measurement_runs SET question_set_id = NULL WHERE id = :i"), {"i": base_run}
    )
    owner_id = await db.scalar(text("SELECT owner_id FROM stores WHERE id = :i"), {"i": store_id})
    req = FixRequest(user_id=owner_id, store_id=store_id, status="remeasure_failed", base_run_id=base_run)
    db.add(req)
    await db.flush()
    req_id = req.id
    await db.commit()
    return store_id, base_run, req_id


async def test_retry_remeasure_e26(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, _, req_id = await _remeasure_failed(db)
    await login(client, OWNER)
    for _ in range(3):
        r = await client.post("/api/fix/requests/current/remeasure/retry")
        assert r.status_code == 202, r.text
        run_id = r.json()["runId"]
        run = await db.get(MeasurementRun, run_id)
        assert (run.kind, run.trigger, run.status, run.fix_request_id, run.is_free) == (
            "remeasure", "retry", "queued", req_id, False,
        )  # fmt: skip
        db.expire_all()
        assert (await db.get(FixRequest, req_id)).status == "remeasuring"
        await db.execute(
            text("UPDATE fix_requests SET status = 'remeasure_failed' WHERE id = :i"), {"i": req_id}
        )
        await db.execute(text("UPDATE measurement_runs SET status = 'failed' WHERE id = :i"), {"i": run_id})
        await db.commit()
    r = await client.post("/api/fix/requests/current/remeasure/retry")
    assert r.status_code == 429 and r.json()["error"]["code"] == "RETRY_LIMIT"
    jobs = await db.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'collectStore'"))
    assert jobs == 3


async def test_retry_remeasure_only_when_failed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, _ = await _store(db)
    await login(client, OWNER)
    r = await client.post("/api/fix/requests/current/remeasure/retry")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "no_request"}
    assert await db.scalar(select(func.count()).select_from(MeasurementRun)) == 1
