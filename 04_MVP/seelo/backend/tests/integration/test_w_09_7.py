"""W-09-7 정비 완료·수동 처리·재측정 예약(09 11·13장, 03 E17·E30, D-16).

모든 칸 자동 완료·일부 수동·연결 끊김 3가지 → remeasure_scheduled, 예약 1행, due_at = fix_completed_at + 14일.
남은 칸이 있으면 그대로, 여러 번·동시에 불러도 예약 1행. 관리자 [처리 완료]·수동 칸 목록.
D-16: 재측정 전 다른 지도 승인 → fixing(예약 취소) → 끝나면 새 예약.
M2 흐름(수동 모드 승인 → 처리 완료 → 예약).
"""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, RemeasureSchedule
from seelo.models.ops import AuditLog, EmailLog
from seelo.models.store import Store
from seelo.services import fix_apply_service
from seelo.services.email_render import render_email
from seelo.timeutil import kst_date, now_utc
from tests.map_world import seed_plan_world
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
OWNER = "owner@seelo.test"
ADMIN = "admin@seelo.test"
VALUES: dict[str, Any] = {
    "website": "https://demo.example/",
    "phone": "02-776-0000",
    "attributes": {"vegetarian": True},
    "menu": [{"name": "칼국수", "price": 11000}],
    "intro": "명동 칼국수",
}
LABEL = {"website": "웹사이트", "phone": "전화번호", "attributes": "편의 정보", "menu": "메뉴·가격"}


async def _admin(db: AsyncSession) -> int:
    user = await make_user(db, ADMIN)
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": user.id})
    await db.commit()
    return user.id


async def _approved(
    db: AsyncSession,
    logs: dict[str, str],
    *,
    provider: str = "google",
    status: str = "fixing",
    w: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """승인된 정비안과 칸마다 fix_logs(상태를 정해 둠). logs가 비면 칸 0개 정비안."""
    w = w or await seed_plan_world(db, status=status)
    plan = FixPlan(
        fix_request_id=w["request_id"],
        provider=provider,
        version=1,
        status="approved",
        base_run_id=w["run_id"],
        approved_at=now_utc(),
    )
    db.add(plan)
    await db.flush()
    ids = {}
    for n, (field, st) in enumerate(logs.items(), 1):
        item = FixPlanItem(
            fix_plan_id=plan.id,
            order_no=n,
            field=field,
            proposed_value=VALUES[field],
            approved_value=VALUES[field],
        )
        db.add(item)
        await db.flush()
        manual = st in ("manual_required", "manual_done")
        lg = FixLog(
            fix_plan_item_id=item.id,
            fix_request_id=w["request_id"],
            provider=provider,
            field=field,
            method="manual" if manual else "browser",
            applied_value=VALUES[field],
            status=st,
            manual_reason="automation_disabled" if manual else None,
        )
        db.add(lg)
        await db.flush()
        ids[field] = lg.id
    await db.commit()
    return w | {"plan_id": plan.id, "logs": ids}


async def _req(db: AsyncSession, request_id: int) -> FixRequest:
    db.expire_all()
    return await db.get(FixRequest, request_id)


async def _schedules(db: AsyncSession) -> list[RemeasureSchedule]:
    """다른 객체를 만료시키지 않고 예약만 새로 읽는다(앞에서 읽은 신청 값을 그대로 쓰려고)."""
    q = select(RemeasureSchedule).order_by(RemeasureSchedule.id).execution_options(populate_existing=True)
    return list((await db.scalars(q)).all())


async def _mails(db: AsyncSession, type_: str) -> list[EmailLog]:
    return list(
        (await db.scalars(select(EmailLog).where(EmailLog.type == type_).order_by(EmailLog.id))).all()
    )


async def _jobs(db: AsyncSession, name: str) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text(
            "SELECT args, queue_name, lock FROM procrastinate_jobs"
            " WHERE task_name = :n AND status = 'todo' ORDER BY id"
        ),
        {"n": name},
    )
    return [(r[0], r[1], r[2]) for r in rows]


# --- E17 정비 완료 -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statuses",
    [
        {"website": "applied", "phone": "applied"},  # 모든 칸 자동 완료
        {"website": "applied", "phone": "manual_done"},  # 일부 수동 처리
        {"website": "disconnected", "phone": "applied"},  # 연결 끊김
    ],
    ids=["auto", "partly_manual", "disconnected"],
)
async def test_all_done_schedules_remeasure(db: AsyncSession, statuses: dict[str, str]) -> None:
    w = await _approved(db, statuses)
    await fix_apply_service.finalize(w["request_id"])
    req = await _req(db, w["request_id"])
    assert req.status == "remeasure_scheduled" and req.fix_completed_at is not None
    (sched,) = await _schedules(db)
    assert (sched.status, sched.triggered_by, sched.run_id) == ("scheduled", "scheduler", None)
    assert sched.due_at == req.fix_completed_at + timedelta(days=14)
    (mail,) = await _mails(db, "fix_completed")
    changed = [f"Google 지도 {LABEL[f]}" for f, st in statuses.items() if st != "disconnected"]
    assert mail.template_params == {
        "changed_fields": changed,
        "remeasure_date": kst_date(sched.due_at).isoformat(),
    }
    assert (mail.to_email, mail.dedupe_key) == (OWNER, f"fix_completed:{sched.id}")
    body = render_email("fix_completed", mail.template_params).text
    assert f"바꾼 항목: {', '.join(changed)}" in body
    due = kst_date(sched.due_at)
    assert f"{due.month}월 {due.day}일에 같은 질문으로" in body
    assert "02-776-0000" not in body and "demo.example" not in body  # 값 원문 없음


@pytest.mark.parametrize("left", ["queued", "pending_reflection", "manual_required"])
async def test_open_items_keep_fixing(db: AsyncSession, left: str) -> None:
    w = await _approved(db, {"website": "applied", "phone": left})
    await fix_apply_service.finalize(w["request_id"])
    req = await _req(db, w["request_id"])
    assert (req.status, req.fix_completed_at) == ("fixing", None)
    assert await _schedules(db) == [] and await _mails(db, "fix_completed") == []


async def test_skip_when_not_fixing_or_no_approved_plan(db: AsyncSession) -> None:
    w = await _approved(db, {"website": "applied"}, status="connecting")
    await fix_apply_service.finalize(w["request_id"])
    assert (await _req(db, w["request_id"])).status == "connecting"
    # fixing인데 승인된 정비안이 없음(승인 대기만)
    await db.execute(text("UPDATE fix_requests SET status = 'fixing' WHERE id = :i"), {"i": w["request_id"]})
    await db.execute(
        text("UPDATE fix_plans SET status = 'awaiting_approval' WHERE id = :i"), {"i": w["plan_id"]}
    )
    await db.commit()
    await fix_apply_service.finalize(w["request_id"])
    assert (await _req(db, w["request_id"])).status == "fixing"
    assert await _schedules(db) == []
    await fix_apply_service.finalize(999_999)  # 없는 신청


async def test_repeated_and_concurrent_finalize_one_schedule(db: AsyncSession) -> None:
    w = await _approved(db, {"website": "applied"})
    rid = w["request_id"]
    await asyncio.gather(fix_apply_service.finalize(rid), fix_apply_service.finalize(rid))
    await fix_apply_service.finalize(rid)
    assert len(await _schedules(db)) == 1
    assert len(await _mails(db, "fix_completed")) == 1


async def test_empty_plan_is_done_and_waiting_plan_does_not_block(db: AsyncSession) -> None:
    """칸 0개 정비안(수동 모드 카카오)은 끝난 것.

    다른 지도의 승인 대기 정비안은 막지 않는다(승인하면 D-16으로 다시 fixing).
    """
    w = await _approved(db, {}, provider="kakao")
    db.add(FixPlan(fix_request_id=w["request_id"], provider="google", version=1, status="awaiting_approval"))
    await db.commit()
    await fix_apply_service.finalize(w["request_id"])
    assert (await _req(db, w["request_id"])).status == "remeasure_scheduled"
    (mail,) = await _mails(db, "fix_completed")
    assert mail.template_params["changed_fields"] == []
    assert "바꾼 항목: 없음" in render_email("fix_completed", mail.template_params).text


# --- E30 관리자 [처리 완료]·수동 칸 목록 -----------------------------------------------------------


async def test_manual_done_api(make_client: Any, db: AsyncSession) -> None:
    admin_id = await _admin(db)
    w = await _approved(
        db,
        {
            "website": "manual_required",
            "phone": "manual_required",
            "attributes": "manual_required",
            "menu": "applied",
        },
    )
    rid, logs = w["request_id"], w["logs"]
    await db.execute(
        text("UPDATE fix_logs SET before_value = '\"02-000-0000\"'::jsonb WHERE id = :i"),
        {"i": logs["phone"]},
    )
    await db.commit()
    owner, admin = await make_client(), await make_client()
    await login(owner, OWNER)
    await login(admin, ADMIN)
    url = "/api/admin/fix-logs/{}/manual-done"
    assert (await owner.post(url.format(logs["website"]))).status_code == 403
    assert (await admin.post(url.format(999_999))).status_code == 404
    r = await admin.post(url.format(logs["menu"]))
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "applied"}

    r = await admin.post(url.format(logs["website"]), json={"beforeValue": "https://old.example/"})
    assert r.status_code == 200 and r.json() == {"status": "manual_done"}
    lg = await db.get(FixLog, logs["website"])
    assert (lg.status, lg.method, lg.handled_by, lg.before_value) == (
        "manual_done", "manual", admin_id, "https://old.example/",
    )  # fmt: skip
    assert lg.handled_at is not None
    assert (await admin.post(url.format(logs["website"]))).status_code == 409  # 두 번 누름
    # before_value가 이미 있으면 받은 값을 쓰지 않는다. 본문이 없어도 된다
    assert (await admin.post(url.format(logs["phone"]), json={"beforeValue": "x"})).status_code == 200
    assert (await admin.post(url.format(logs["attributes"]))).status_code == 200
    db.expire_all()
    assert (await db.get(FixLog, logs["phone"])).before_value == "02-000-0000"
    assert (await db.get(FixLog, logs["attributes"])).before_value is None
    # 칸마다 finalizeFix를 등록하지만 대기 중인 것과 하나로 합쳐진다(plan 큐, lock request:{id})
    assert await _jobs(db, "finalizeFix") == [({"fix_request_id": rid}, "plan", f"request:{rid}")]
    audits = (await db.scalars(select(AuditLog).where(AuditLog.action == "fix_log.manual_done"))).all()
    assert [(a.actor_id, a.target_type) for a in audits] == [(admin_id, "fix_log")] * 3
    assert audits[0].detail == {"provider": "google", "field": "website", "beforeValueGiven": True}
    assert audits[1].detail["beforeValueGiven"] is False

    await fix_apply_service.finalize(rid)
    assert (await _req(db, rid)).status == "remeasure_scheduled"


async def test_manual_items_list(make_client: Any, db: AsyncSession) -> None:
    await _admin(db)
    w = await _approved(db, {"website": "manual_required", "phone": "applied"})
    owner, admin = await make_client(), await make_client()
    await login(owner, OWNER)
    await login(admin, ADMIN)
    assert (await owner.get("/api/admin/manual-items")).status_code == 403
    r = await admin.get("/api/admin/manual-items")
    assert r.status_code == 200
    (item,) = r.json()
    store_name = await db.scalar(select(Store.name).where(Store.id == w["store_id"]))
    assert {k: v for k, v in item.items() if k != "createdAt"} == {
        "fixLogId": w["logs"]["website"],
        "fixRequestId": w["request_id"],
        "storeName": store_name,
        "provider": "google",
        "field": "website",
        "fieldLabel": "웹사이트",
        "approvedValue": "https://demo.example/",
        "manualReason": "automation_disabled",
        "adminUrl": "https://business.google.com/",
    }
    await admin.post(f"/api/admin/fix-logs/{w['logs']['website']}/manual-done")
    assert (await admin.get("/api/admin/manual-items")).json() == []


# --- D-16·M2 흐름 ---------------------------------------------------------------------------------


async def _awaiting_plan(
    db: AsyncSession, request_id: int, run_id: int, provider: str, field: str
) -> dict[str, int]:
    plan = FixPlan(
        fix_request_id=request_id,
        provider=provider,
        version=1,
        status="awaiting_approval",
        base_run_id=run_id,
    )
    db.add(plan)
    await db.flush()
    item = FixPlanItem(fix_plan_id=plan.id, order_no=1, field=field, proposed_value=VALUES[field])
    db.add(item)
    await db.commit()
    return {"plan_id": plan.id, "item_id": item.id}


async def test_d16_other_map_approved_then_new_schedule(make_client: Any, db: AsyncSession) -> None:
    await _admin(db)
    w = await _approved(db, {"website": "applied"})
    rid = w["request_id"]
    await fix_apply_service.finalize(rid)
    (first,) = await _schedules(db)
    first_done = (await _req(db, rid)).fix_completed_at

    k = await _awaiting_plan(db, rid, w["run_id"], "kakao", "intro")
    owner, admin = await make_client(), await make_client()
    await login(owner, OWNER)
    await login(admin, ADMIN)
    body = {"items": [{"itemId": k["item_id"], "excluded": False}]}
    assert (await owner.post(f"/api/fix/plans/{k['plan_id']}/approve", json=body)).status_code == 202
    assert (await _req(db, rid)).status == "fixing"
    assert [s.status for s in await _schedules(db)] == ["canceled"]
    await fix_apply_service.finalize(rid)  # 카카오 칸이 아직 수동 처리 전
    assert (await _req(db, rid)).status == "fixing"

    kakao_log = await db.scalar(select(FixLog.id).where(FixLog.provider == "kakao"))
    assert (await admin.post(f"/api/admin/fix-logs/{kakao_log}/manual-done")).status_code == 200
    await fix_apply_service.finalize(rid)
    req = await _req(db, rid)
    assert req.status == "remeasure_scheduled" and req.fix_completed_at > first_done
    old, new = await _schedules(db)
    assert (old.id, old.status, new.status) == (first.id, "canceled", "scheduled")
    assert new.due_at == req.fix_completed_at + timedelta(days=14)
    mails = await _mails(db, "fix_completed")
    assert [m.dedupe_key for m in mails] == [f"fix_completed:{first.id}", f"fix_completed:{new.id}"]
    assert mails[1].template_params["changed_fields"] == ["Google 지도 웹사이트", "카카오맵 한 줄 소개"]


async def test_m2_flow_manual_mode(make_client: Any, db: AsyncSession) -> None:
    """수동 모드: 사장님 승인 → 관리자가 직접 고치고 [처리 완료] → 정비 완료·재측정 예약(M2)."""
    await _admin(db)
    w = await seed_plan_world(db)
    p = await _awaiting_plan(db, w["request_id"], w["run_id"], "google", "website")
    owner, admin = await make_client(), await make_client()
    await login(owner, OWNER)
    await login(admin, ADMIN)
    body = {"items": [{"itemId": p["item_id"], "excluded": False}]}
    assert (await owner.post(f"/api/fix/plans/{p['plan_id']}/approve", json=body)).status_code == 202
    await fix_apply_service.finalize(w["request_id"])  # 승인 때 등록된 작업: 수동 칸이 남아 그대로
    assert (await owner.get("/api/home")).json()["card"] == "fixing"

    (item,) = (await admin.get("/api/admin/manual-items")).json()
    assert (await admin.post(f"/api/admin/fix-logs/{item['fixLogId']}/manual-done")).status_code == 200
    await fix_apply_service.finalize(w["request_id"])

    req = await _req(db, w["request_id"])
    due = kst_date(req.fix_completed_at + timedelta(days=14)).isoformat()
    home = (await owner.get("/api/home")).json()
    assert (home["card"], home["data"]) == ("remeasure_waiting", {"dueDate": due, "changedCount": 1})
    state = (await owner.get("/api/fix/requests/current")).json()["request"]
    assert state["remeasureDueDate"] == due
    assert [s["key"] for s in state["steps"] if s["state"] == "current"] == ["remeasure_waiting"]
    detail = (await owner.get(f"/api/fix/plans/{p['plan_id']}")).json()
    assert [i["result"]["statusLabel"] for i in detail["items"]] == ["완료"]
    admin_detail = (await admin.get(f"/api/admin/fix-requests/{w['request_id']}")).json()
    assert admin_detail["request"]["displayStatus"] == "remeasure_waiting"
    assert admin_detail["schedule"]["status"] == "scheduled" and admin_detail["manualItems"] == []
    assert (
        await db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.type == "fix_completed"))
        == 1
    )
