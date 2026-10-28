"""W-09-4 정비안 조회·승인(04 7.3, 09 7장, 03 E15).

"확인 필요" 빈 칸·민감 정보 미확인 → 400(아무것도 저장 안 함), 사장님이 고친 값 형식 검사,
동시 승인 2개 → 1개,
남의 정비안 404·본문 없음, 연결 안 된 지도 409, 승인 뒤 fix_logs(수동·자동·카카오 꺼짐·API 미지원).
"""

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, RemeasureSchedule
from seelo.models.ops import AuditLog, EmailLog
from seelo.timeutil import now_utc
from tests.map_world import seed_plan_world
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
OWNER = "owner@seelo.test"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(ADMIN_NOTIFY_EMAILS="ops@seelo.test")


async def _awaiting(
    db: AsyncSession, *, provider: str = "google", status: str = "connecting"
) -> dict[str, Any]:
    """승인 대기 정비안: 전화(확인 필요 [ ]), 편의 정보(null), 메뉴(민감), 웹사이트(바로 승인 가능)."""
    w = await seed_plan_world(db, status=status)
    plan = FixPlan(
        fix_request_id=w["request_id"],
        provider=provider,
        version=1,
        status="awaiting_approval",
        base_run_id=w["run_id"],
    )
    db.add(plan)
    await db.flush()
    rows = {
        "phone": FixPlanItem(
            fix_plan_id=plan.id, order_no=1, field="phone", proposed_value="[ ]", needs_owner_input=True
        ),
        "attributes": FixPlanItem(
            fix_plan_id=plan.id,
            order_no=2,
            field="attributes",
            proposed_value={"vegetarian": None},
            needs_owner_input=True,
        ),
        "menu": FixPlanItem(
            fix_plan_id=plan.id,
            order_no=3,
            field="menu",
            proposed_value=[{"name": "칼국수", "nameEn": "Halal noodles", "price": 11000}],
            sensitive=True,
        ),
        "website": FixPlanItem(
            fix_plan_id=plan.id,
            order_no=4,
            field="website",
            proposed_value="https://demo.example/",
            current_value=None,
        ),
    }
    if provider == "kakao":
        rows = {
            "intro": FixPlanItem(fix_plan_id=plan.id, order_no=1, field="intro", proposed_value="명동 칼국수")
        }
    db.add_all(rows.values())
    await db.flush()
    w |= {"plan_id": plan.id, "items": {k: v.id for k, v in rows.items()}}
    await db.commit()
    return w


def _body(items: dict[str, int], **override: dict[str, Any]) -> dict[str, Any]:
    return {"items": [{"itemId": i, "excluded": False, **override.get(k, {})} for k, i in items.items()]}


FILLED = {
    "phone": {"approvedValue": "02-776-0000"},
    "attributes": {"approvedValue": {"vegetarian": False}},
    "menu": {"ownerConfirmed": True},
}


async def _plan(db: AsyncSession, plan_id: int) -> FixPlan:
    db.expire_all()
    return await db.get(FixPlan, plan_id)


async def _jobs(db: AsyncSession, name: str) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text("SELECT args, queue_name, lock FROM procrastinate_jobs WHERE task_name = :n ORDER BY id"),
        {"n": name},
    )
    return [(r[0], r[1], r[2]) for r in rows]


# --- 조회 ----------------------------------------------------------------------------------


async def test_detail_findings_items_and_guides(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    await db.execute(text("UPDATE fix_plan_items SET finding_ids = ARRAY[3] WHERE field = 'phone'"))
    await db.commit()
    await login(client, OWNER)
    plans = (await client.get("/api/fix/plans")).json()
    assert plans == {
        "plans": [{"planId": w["plan_id"], "provider": "google", "status": "awaiting_approval", "version": 1}]
    }
    d = (await client.get(f"/api/fix/plans/{w['plan_id']}")).json()
    assert (d["status"], d["readOnly"], d["mapNotFound"]) == ("awaiting_approval", False, False)
    assert [i["field"] for i in d["items"]] == ["phone", "attributes", "menu", "website"]
    phone = d["items"][0]
    assert (phone["fieldLabel"], phone["constraints"], phone["result"]) == (
        "전화번호",
        {"type": "phone", "maxLength": None, "maxItems": None},
        None,
    )
    titles = {f["title"]: f["itemId"] for f in d["findings"]}
    assert titles["공식 웹사이트와 Google 지도의 전화번호가 달라요"] == phone["itemId"]
    assert [f["field"] for f in d["ownerOnlyFields"]] == ["name"]  # 이름 다름 → 사장님이 직접
    assert d["summary"]["connections"] == {"google": "connected", "kakao": "connected"}
    assert d["summary"]["itemCounts"] == {"google": 4, "kakao": 0}
    ev = (await client.get(f"/api/fix/plans/{w['plan_id']}/evidence")).json()
    assert ev == {"questions": []}  # 이 테스트 세계는 질문 세트가 없다


async def test_generating_plan_has_no_items(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    await db.execute(text("UPDATE fix_plans SET status = 'generating' WHERE id = :i"), {"i": w["plan_id"]})
    await db.commit()
    await login(client, OWNER)
    d = (await client.get(f"/api/fix/plans/{w['plan_id']}")).json()
    assert (d["items"], d["findings"], d["readOnly"]) == ([], [], True)


async def test_other_owner_404_admin_read_only(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    await make_user(db, "other@seelo.test")
    admin = await make_user(db, "admin@seelo.test")
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": admin.id})
    await db.commit()
    await login(client, "other@seelo.test")
    for path in ("", "/evidence"):
        r = await client.get(f"/api/fix/plans/{w['plan_id']}{path}")
        assert r.status_code == 404 and "명동교자" not in r.text and "demo.example" not in r.text
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    assert r.status_code == 404
    await login(client, "admin@seelo.test")
    d = (await client.get(f"/api/fix/plans/{w['plan_id']}")).json()
    assert d["readOnly"] is True
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    assert r.status_code == 404  # 승인은 사장님만


async def test_never_connected_map_is_404(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    await db.execute(text("UPDATE map_connections SET connected_at = NULL, status = 'invited'"))
    await db.commit()
    await login(client, OWNER)
    assert (await client.get(f"/api/fix/plans/{w['plan_id']}")).status_code == 404


# --- 승인 검사(09 7장 3~5번) -----------------------------------------------------------------


async def test_validation_order_and_nothing_saved(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    url, items = f"/api/fix/plans/{w['plan_id']}/approve", w["items"]
    await login(client, OWNER)
    partial = {"items": [{"itemId": items["phone"], "excluded": True}]}
    r = await client.post(url, json=partial)
    assert r.status_code == 400 and r.json()["error"]["code"] == "ITEMS_MISMATCH"
    dup = {"items": [{"itemId": i, "excluded": False} for i in [*items.values(), items["phone"]]]}
    assert (await client.post(url, json=dup)).json()["error"]["code"] == "ITEMS_MISMATCH"
    r = await client.post(url, json=_body(items))
    assert r.status_code == 400 and r.json()["error"] == {
        "code": "NEEDS_OWNER_INPUT",
        "message": '"확인 필요" 칸을 채우거나 빼 주세요',
        "details": {"itemIds": [items["phone"], items["attributes"]]},
    }
    r = await client.post(url, json=_body(items, phone=FILLED["phone"], attributes=FILLED["attributes"]))
    assert r.json()["error"] == {
        "code": "SENSITIVE_NOT_CONFIRMED",
        "message": "알레르기·할랄 정보를 확인해 주세요",
        "details": {"itemIds": [items["menu"]]},
    }
    r = await client.post(url, json=_body(items, **(FILLED | {"phone": {"approvedValue": "123"}})))
    assert r.json()["error"]["details"] == {"itemId": items["phone"], "reason": "bad_format"}
    r = await client.post(url, json=_body(items, **(FILLED | {"website": {"approvedValue": None}})))
    assert r.json()["error"]["details"] == {"itemId": items["website"], "reason": "placeholder_left"}  # 비움
    plan = await _plan(db, w["plan_id"])
    assert plan.status == "awaiting_approval"
    assert await db.scalar(select(func.count()).select_from(FixLog)) == 0
    assert all(i.approved_value is None for i in await db.scalars(select(FixPlanItem)))


async def test_approve_manual_mode(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    items = w["items"]
    await login(client, OWNER)
    body = _body(items, **(FILLED | {"website": {"excluded": True}}))
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=body)
    assert r.status_code == 202 and r.json() == {"planId": w["plan_id"], "status": "approved"}
    plan = await _plan(db, w["plan_id"])
    assert plan.status == "approved" and plan.approved_at is not None
    assert (await db.get(FixRequest, w["request_id"])).status == "fixing"
    rows = {i.field: i for i in await db.scalars(select(FixPlanItem))}
    assert (rows["phone"].approved_value, rows["phone"].owner_edited) == ("02-776-0000", True)
    assert (rows["menu"].owner_confirmed, rows["menu"].owner_edited) == (True, False)
    assert (rows["website"].excluded, rows["website"].approved_value) == (True, None)
    logs = {lg.field: lg for lg in await db.scalars(select(FixLog))}
    assert set(logs) == {"phone", "attributes", "menu"}  # 제외한 칸은 기록 없음
    assert {(lg.status, lg.method, lg.manual_reason) for lg in logs.values()} == {
        ("manual_required", "manual", "automation_disabled")
    }
    assert logs["attributes"].applied_value == {"vegetarian": False}
    assert await _jobs(db, "finalizeFix") == [
        ({"fix_request_id": w["request_id"]}, "plan", f"request:{w['request_id']}")
    ]
    assert await _jobs(db, "applyFix") == []
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "manual_required"))
    assert mail.to_email == "ops@seelo.test"
    assert {i["field_label"] for i in mail.template_params["items"]} == {"전화번호", "편의 정보", "메뉴·가격"}
    audit = await db.scalar(select(AuditLog))
    assert (audit.action, audit.detail) == (
        "fix_plan.approve",
        {"itemCount": 3, "excludedCount": 1, "editedCount": 2},
    )
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=body)  # 두 번 누름
    assert r.status_code == 409


async def test_approve_auto_modes(client: httpx.AsyncClient, db: AsyncSession, settings_env: Any) -> None:
    settings_env(AUTO_FIX_ENABLED="true", GOOGLE_FIX_MODE="api")
    w = await _awaiting(db)
    await login(client, OWNER)
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    assert r.status_code == 202
    logs = {lg.field: (lg.status, lg.method, lg.manual_reason) for lg in await db.scalars(select(FixLog))}
    assert logs == {
        "phone": ("queued", "api", None),
        "website": ("queued", "api", None),
        "attributes": ("manual_required", "manual", "api_unsupported"),  # 사전에 api 매핑 없음
        "menu": ("manual_required", "manual", "api_unsupported"),
    }
    assert await _jobs(db, "applyFix") == [({"fix_plan_id": w["plan_id"]}, "fix", "fix:google")]
    assert await _jobs(db, "finalizeFix") == []


async def test_kakao_fix_disabled(client: httpx.AsyncClient, db: AsyncSession, settings_env: Any) -> None:
    settings_env(AUTO_FIX_ENABLED="true", KAKAO_FIX_ENABLED="false")
    w = await _awaiting(db, provider="kakao")
    await login(client, OWNER)
    assert (
        await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"]))
    ).status_code == 202
    log_ = await db.scalar(select(FixLog))
    assert (log_.status, log_.manual_reason) == ("manual_required", "kakao_fix_disabled")


async def test_concurrent_approvals_one_wins(make_client: Any, db: AsyncSession, settings_env: Any) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    w = await _awaiting(db)
    c1, c2 = await make_client(), await make_client()
    await login(c1, OWNER)
    await login(c2, OWNER)
    url, body = f"/api/fix/plans/{w['plan_id']}/approve", _body(w["items"], **FILLED)
    r1, r2 = await asyncio.gather(c1.post(url, json=body), c2.post(url, json=body))
    assert sorted([r1.status_code, r2.status_code]) == [202, 409]
    assert len(await _jobs(db, "applyFix")) == 1
    assert await db.scalar(select(func.count()).select_from(FixLog)) == 4


async def test_connection_not_connected(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db)
    await db.execute(
        text("UPDATE map_connections SET status = 'needs_attention' WHERE id = :i"),
        {"i": w["connections"]["google"]},
    )
    await db.commit()
    await login(client, OWNER)
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONNECTION_NOT_CONNECTED"


async def test_remeasure_scheduled_goes_back_to_fixing(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db, status="remeasure_scheduled")
    db.add(
        RemeasureSchedule(
            fix_request_id=w["request_id"], due_at=now_utc(), triggered_by="scheduler", status="scheduled"
        )
    )
    await db.commit()
    await login(client, OWNER)
    assert (
        await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    ).status_code == 202
    db.expire_all()
    assert (await db.get(FixRequest, w["request_id"])).status == "fixing"
    assert (await db.scalar(select(RemeasureSchedule.status))) == "canceled"  # D-16


async def test_request_not_writable(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _awaiting(db, status="remeasuring")
    await login(client, OWNER)
    r = await client.post(f"/api/fix/plans/{w['plan_id']}/approve", json=_body(w["items"], **FILLED))
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "remeasuring"}
