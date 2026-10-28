"""W-06-3 홈 GET /api/home(04 5.1, 03 4장): 카드별 data와 공통 표시.

카드 판정 15가지 자체는 unit/test_home_card.py. 여기서는 DB 상태 → 응답(data 키·값, 공통 표시)을 본다.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.report import ComparisonReport
from seelo.models.store import Store
from tests.map_world import g_detail, measure_to_end, seed_google_snapshot, seed_measuring, seed_store
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
OWNER = "owner@seelo.test"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        AI_REPEAT_COUNT="2", OPENAI_MEASURE_MODEL="m", GEMINI_MEASURE_MODEL="m", OPENAI_CHEAP_MODEL="c"
    )


async def _home(client: httpx.AsyncClient) -> dict[str, Any]:
    await login(client, OWNER)
    r = await client.get("/api/home")
    assert r.status_code == 200, r.text
    return r.json()


async def _diagnosed(db: AsyncSession) -> tuple[int, int]:
    store_id, run_id, _ = await seed_measuring(db, name="데모식당")
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    await measure_to_end(db, run_id)
    return store_id, run_id


async def _request(db: AsyncSession, store_id: int, status: str, **kw: Any) -> int:
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    req = FixRequest(user_id=owner_id, store_id=store_id, status=status, **kw)
    db.add(req)
    await db.flush()
    req_id = req.id
    await db.commit()
    return req_id


async def _plan_with_logs(db: AsyncSession, req_id: int, plan_status: str, log_statuses: list[str]) -> int:
    plan = FixPlan(fix_request_id=req_id, provider="google", version=1, status=plan_status)
    db.add(plan)
    await db.flush()
    for i, st in enumerate(log_statuses or ["-"], 1):
        item = FixPlanItem(fix_plan_id=plan.id, order_no=i, field=f"field{i}")
        db.add(item)
        await db.flush()
        if st != "-":
            db.add(
                FixLog(
                    fix_plan_item_id=item.id, fix_request_id=req_id, provider="google", field=f"field{i}",
                    method="manual", applied_value="v", status=st,
                )
            )  # fmt: skip
    plan_id = plan.id
    await db.commit()
    return plan_id


async def test_no_store(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, OWNER)
    body = await _home(client)
    assert body == {
        "card": "no_store",
        "store": None,
        "storeChangeBlocked": False,
        "revokedProviders": [],
        "manualInProgress": False,
        "retriesLeftToday": 3,
        "hasHistory": False,
        "data": {},
    }


async def test_measuring_shows_progress(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db)
    await db.execute(
        text("UPDATE measurement_runs SET progress_done = 23, progress_total = 60 WHERE id = :i"),
        {"i": run_id},
    )
    await db.commit()
    body = await _home(client)
    assert body["card"] == "measuring" and body["store"]["name"] == "명동교자"
    assert body["data"] == {
        "runId": run_id, "kind": "diagnosis", "stage": "calling_ai", "progressDone": 23, "progressTotal": 60,
        "waitingReason": None,
    }  # fmt: skip


async def test_diagnosed_card_has_rates_and_findings_count(
    client: httpx.AsyncClient, db: AsyncSession, ai: Any
) -> None:
    _, run_id = await _diagnosed(db)
    body = await _home(client)
    assert body["card"] == "diagnosed" and body["store"]["status"] == "diagnosed"
    assert body["store"]["address"] == "대한민국 서울특별시 중구 명동10길 29"  # Google 스냅샷
    data = body["data"]
    assert data["runId"] == run_id and data["findingsCount"] > 0
    assert data["providers"]["openai"] == {
        "successCount": 6,
        "appearanceCount": 3,
        "rate": 0.5,
        "avgRank": 2.0,
    }
    assert not ({"findings", "title", "evidence"} & set(str(body).split("'")))  # 내용은 없음
    assert body["storeChangeBlocked"] is False


async def test_measure_failed_and_retries_left(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, run_id = await seed_store(db)
    await db.execute(text("UPDATE stores SET status = 'measure_failed' WHERE id = :i"), {"i": store_id})
    await db.execute(text("UPDATE measurement_runs SET status = 'failed' WHERE id = :i"), {"i": run_id})
    retry = MeasurementRun(store_id=store_id, kind="diagnosis", trigger="retry", status="failed")
    db.add(retry)
    await db.flush()
    retry_id = retry.id
    await db.commit()
    body = await _home(client)
    assert (body["card"], body["retriesLeftToday"]) == ("measure_failed", 2)  # 오늘 다시 시도 1번
    assert body["data"] == {"runId": retry_id} and retry_id != run_id  # 가장 최근 실패 측정


async def test_fix_requested_blocks_store_change(
    client: httpx.AsyncClient, db: AsyncSession, ai: Any
) -> None:
    store_id, _ = await _diagnosed(db)
    req_id = await _request(db, store_id, "requested")
    body = await _home(client)
    assert body["card"] == "fix_requested" and body["storeChangeBlocked"] is True
    assert body["data"]["requestId"] == req_id and body["data"]["requestedAt"].endswith("Z")


async def test_fix_rejected(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    store_id, _ = await _diagnosed(db)
    req_id = await _request(db, store_id, "rejected", reject_reason="지원하지 않는 지역")
    body = await _home(client)
    assert (body["card"], body["data"]) == (
        "fix_rejected",
        {"requestId": req_id, "rejectReason": "지원하지 않는 지역"},
    )
    assert body["storeChangeBlocked"] is False  # 거절된 신청은 진행 중이 아님


async def test_connect_needed_with_revoked(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    store_id, _ = await _diagnosed(db)
    req_id = await _request(db, store_id, "connecting")
    db.add_all(
        [
            MapConnection(fix_request_id=req_id, provider="google", status="invited"),
            MapConnection(fix_request_id=req_id, provider="kakao", status="revoked"),
        ]
    )
    await db.commit()
    body = await _home(client)
    assert body["card"] == "connect_needed"
    assert body["data"] == {"connections": {"google": "invited", "kakao": "revoked"}}
    assert body["revokedProviders"] == ["kakao"]


async def test_plan_needs_approval(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    store_id, _ = await _diagnosed(db)
    req_id = await _request(db, store_id, "connecting")
    plan_id = await _plan_with_logs(db, req_id, "awaiting_approval", ["-"])
    db.add(FixPlanItem(fix_plan_id=plan_id, order_no=2, field="description"))
    await db.commit()
    body = await _home(client)
    assert (body["card"], body["data"]) == ("plan_needs_approval", {"planIds": [plan_id], "itemCount": 2})


async def test_remeasure_waiting_with_manual(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    store_id, _ = await _diagnosed(db)
    req_id = await _request(db, store_id, "remeasure_scheduled")
    await _plan_with_logs(db, req_id, "approved", ["applied", "manual_done", "manual_required"])
    due = datetime(2026, 11, 11, 16, 30, tzinfo=UTC)  # KST로 11월 12일
    db.add(RemeasureSchedule(fix_request_id=req_id, due_at=due, triggered_by="scheduler", status="scheduled"))
    await db.commit()
    body = await _home(client)
    assert (body["card"], body["data"]) == ("remeasure_waiting", {"dueDate": "2026-11-12", "changedCount": 2})
    assert body["manualInProgress"] is True and body["storeChangeBlocked"] is True


async def test_report_ready_uses_before_after_metrics(
    client: httpx.AsyncClient, db: AsyncSession, ai: Any
) -> None:
    store_id, base_run = await _diagnosed(db)
    req_id = await _request(db, store_id, "report_ready", base_run_id=base_run)
    after = MeasurementRun(store_id=store_id, kind="remeasure", trigger="scheduler", status="completed")
    db.add(after)
    await db.flush()
    report = ComparisonReport(
        fix_request_id=req_id, store_id=store_id, base_run_id=base_run, after_run_id=after.id, version=1,
        status="completed",
    )  # fmt: skip
    db.add(report)
    await db.flush()
    report_id = report.id
    await db.commit()
    body = await _home(client)
    assert body["card"] == "report_ready" and body["data"]["reportId"] == report_id
    openai = body["data"]["providers"]["openai"]
    assert openai["before"]["rate"] == 0.5
    assert openai["after"] == {"successCount": 0, "appearanceCount": 0, "rate": None, "avgRank": None}


async def test_history_flag(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, _ = await seed_store(db, with_run=False)
    await db.execute(
        text("UPDATE stores SET archived_at = :t, status = 'archived' WHERE id = :i"),
        {"t": datetime.now(UTC) - timedelta(days=1), "i": store_id},
    )
    await db.commit()
    body = await _home(client)
    assert (body["card"], body["hasHistory"]) == ("no_store", True)
