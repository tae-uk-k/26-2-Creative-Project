"""W-08-2 관리자(04 8장, 03 E9·E10·5장).

/api/admin/* 사장님 403, 처리된 신청 재처리 409, 승인·거절마다 audit_logs 1행·메일, 승인 때 기준 측정이 없으면
측정부터, 목록 필터·대표 상태·쪽 나누기, 상세(실패율·비용·수동 칸).
연결 확인·처리 완료·다시 생성·지금 재측정의 감사 기록은 해당 단계(10·12·14) 테스트에서 본다.
"""

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import AuditLog, EmailLog
from seelo.models.store import Store
from tests.map_world import seed_store
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
ADMIN = "admin@seelo.test"


async def _admin(db: AsyncSession) -> int:
    user = await make_user(db, ADMIN)
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": user.id})
    await db.commit()
    return user.id


async def _requested(
    db: AsyncSession, *, email: str = "owner@seelo.test", base: bool = True
) -> tuple[int, int]:
    """가게(diagnosed 또는 collected)와 requested 신청. (store_id, request_id)."""
    store_id, run_id = await seed_store(db, email=email)
    status = "diagnosed" if base else "collected"
    await db.execute(text("UPDATE stores SET status = :s WHERE id = :i"), {"s": status, "i": store_id})
    await db.execute(
        text("UPDATE measurement_runs SET status = :s WHERE id = :i"),
        {"s": "completed" if base else "canceled", "i": run_id},
    )
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    req = FixRequest(
        user_id=owner_id, store_id=store_id, status="requested", base_run_id=run_id if base else None
    )
    db.add(req)
    await db.flush()
    req_id = req.id
    await db.commit()
    return store_id, req_id


ADMIN_ROUTES = [
    ("GET", "/api/admin/fix-requests"),
    ("GET", "/api/admin/fix-requests/1"),
    ("POST", "/api/admin/fix-requests/1/approve"),
    ("POST", "/api/admin/fix-requests/1/reject"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
async def test_owner_gets_403(client: httpx.AsyncClient, db: AsyncSession, method: str, path: str) -> None:
    await make_user(db, "owner@seelo.test")
    await login(client, "owner@seelo.test")
    r = await client.request(method, path, json={"reason": "x"} if path.endswith("reject") else None)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_approve_with_base_run_goes_connecting(client: httpx.AsyncClient, db: AsyncSession) -> None:
    admin_id = await _admin(db)
    _, req_id = await _requested(db)
    await login(client, ADMIN)
    r = await client.post(f"/api/admin/fix-requests/{req_id}/approve")
    assert r.status_code == 200 and r.json() == {"status": "connecting"}
    db.expire_all()
    req = await db.get(FixRequest, req_id)
    assert (req.status, req.decided_by, req.decided_at is not None) == ("connecting", admin_id, True)
    conns = (await db.scalars(select(MapConnection).order_by(MapConnection.provider))).all()
    assert [(c.provider, c.status) for c in conns] == [
        ("google", "not_connected"),
        ("kakao", "not_connected"),
    ]
    audits = (await db.scalars(select(AuditLog))).all()
    assert [(a.action, a.actor_id, a.target_type, a.target_id) for a in audits] == [
        ("fix_request.approve", admin_id, "fix_request", req_id)
    ]
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "fix_decided"))
    assert (mail.to_email, mail.template_params) == (
        "owner@seelo.test",
        {"decision": "approved", "reject_reason": None},
    )
    # 이미 처리된 신청은 다시 처리할 수 없다
    for path, body in [("approve", None), ("reject", {"reason": "늦은 거절"})]:
        r = await client.post(f"/api/admin/fix-requests/{req_id}/{path}", json=body)
        assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "connecting"}
    assert len((await db.scalars(select(AuditLog))).all()) == 1


async def test_approve_without_base_run_measures_first(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    store_id, req_id = await _requested(db, base=False)
    await login(client, ADMIN)
    r = await client.post(f"/api/admin/fix-requests/{req_id}/approve")
    assert r.json() == {"status": "approved"}
    db.expire_all()
    assert (await db.get(Store, store_id)).status == "collecting"
    run = await db.scalar(select(MeasurementRun).where(MeasurementRun.fix_request_id == req_id))
    assert (run.kind, run.is_free, run.trigger, run.status) == ("diagnosis", False, "initial", "queued")
    jobs = (
        (await db.execute(text("SELECT args FROM procrastinate_jobs WHERE task_name = 'collectStore'")))
        .scalars()
        .all()
    )
    assert jobs == [{"store_id": store_id, "run_id": run.id}]


async def test_reject_requires_reason_and_records(client: httpx.AsyncClient, db: AsyncSession) -> None:
    admin_id = await _admin(db)
    _, req_id = await _requested(db)
    await login(client, ADMIN)
    r = await client.post(f"/api/admin/fix-requests/{req_id}/reject", json={"reason": "   "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REJECT_REASON_REQUIRED"
    r = await client.post(
        f"/api/admin/fix-requests/{req_id}/reject", json={"reason": "서비스 지역이 아니에요"}
    )
    assert r.status_code == 200 and r.json() == {"status": "rejected"}
    db.expire_all()
    req = await db.get(FixRequest, req_id)
    assert (req.status, req.reject_reason, req.decided_by) == ("rejected", "서비스 지역이 아니에요", admin_id)
    audit = await db.scalar(select(AuditLog))
    assert (audit.action, audit.detail) == ("fix_request.reject", {"reason": "서비스 지역이 아니에요"})
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "fix_decided"))
    assert mail.template_params == {"decision": "rejected", "reject_reason": "서비스 지역이 아니에요"}
    r = await client.post(f"/api/admin/fix-requests/{req_id}/approve")
    assert r.status_code == 409


async def test_unknown_request_404(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    await login(client, ADMIN)
    assert (await client.post("/api/admin/fix-requests/999/approve")).status_code == 404
    assert (await client.get("/api/admin/fix-requests/999")).status_code == 404


async def _manual_log(db: AsyncSession, req_id: int) -> int:
    plan = FixPlan(fix_request_id=req_id, provider="google", version=1, status="approved")
    db.add(plan)
    await db.flush()
    item = FixPlanItem(fix_plan_id=plan.id, order_no=1, field="regular_hours")
    db.add(item)
    await db.flush()
    log_ = FixLog(
        fix_plan_item_id=item.id, fix_request_id=req_id, provider="google", field="regular_hours",
        method="manual", applied_value={"days": {}}, status="manual_required",
        manual_reason="automation_disabled",
    )  # fmt: skip
    db.add(log_)
    await db.flush()
    log_id = log_.id
    await db.commit()
    return log_id


async def test_list_filter_display_and_pages(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    _, first = await _requested(db, email="a@seelo.test")
    _, second = await _requested(db, email="b@seelo.test")
    _, third = await _requested(db, email="c@seelo.test")
    await db.execute(text("UPDATE fix_requests SET status = 'fixing' WHERE id = :i"), {"i": second})
    await _manual_log(db, second)
    await login(client, ADMIN)
    body = (await client.get("/api/admin/fix-requests")).json()
    assert (body["total"], body["page"], body["pageSize"]) == (3, 1, 20)
    assert [i["id"] for i in body["items"]] == [third, second, first]  # 최신 먼저
    row = next(i for i in body["items"] if i["id"] == second)
    assert (row["status"], row["displayStatus"], row["ownerEmail"]) == (
        "fixing",
        "manual_required",
        "b@seelo.test",
    )
    assert row["storeName"] == "명동교자" and row["diagnosisStatus"] == "completed"
    fixing = (await client.get("/api/admin/fix-requests", params={"filter": "fixing"})).json()
    assert [i["id"] for i in fixing["items"]] == [second]  # 수동 칸이 있어도 fixing 필터에 걸림
    page2 = (await client.get("/api/admin/fix-requests", params={"page": 2, "pageSize": 2})).json()
    assert [i["id"] for i in page2["items"]] == [first] and page2["total"] == 3
    bad = await client.get("/api/admin/fix-requests", params={"filter": "nope"})
    assert bad.status_code == 422


async def test_detail_shows_runs_cost_and_manual_items(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    store_id, req_id = await _requested(db)
    await db.execute(
        text("UPDATE measurement_runs SET failure_rate = 0.05, cost_usd = 0.1234 WHERE store_id = :i"),
        {"i": store_id},
    )
    await db.execute(text("UPDATE fix_requests SET status = 'fixing' WHERE id = :i"), {"i": req_id})
    log_id = await _manual_log(db, req_id)
    await login(client, ADMIN)
    r = await client.get(f"/api/admin/fix-requests/{req_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["request"]["status"], d["request"]["displayStatus"]) == ("fixing", "manual_required")
    assert d["owner"]["email"] == "owner@seelo.test" and d["store"]["name"] == "명동교자"
    assert d["store"]["sources"]["google"] == "found"
    assert d["baseRun"]["status"] == "completed"
    assert d["runs"][0]["failureRate"] == 0.05 and d["runs"][0]["costUsd"] == 0.1234  # 숫자로
    assert [(p["provider"], p["version"], p["status"]) for p in d["plans"]] == [("google", 1, "approved")]
    assert d["manualItems"] == [
        {
            "fixLogId": log_id, "fixRequestId": req_id, "storeName": "명동교자", "provider": "google",
            "field": "regular_hours", "fieldLabel": "영업시간", "approvedValue": {"days": {}},
            "manualReason": "automation_disabled", "adminUrl": "https://business.google.com/",
            "createdAt": d["manualItems"][0]["createdAt"],
        }
    ]  # fmt: skip
    assert d["schedule"] is None and d["reports"] == [] and d["connections"] == []


async def test_admin_routes_need_login(api: httpx.AsyncClient) -> None:
    r = await api.get("/api/admin/fix-requests")
    assert r.status_code == 401
