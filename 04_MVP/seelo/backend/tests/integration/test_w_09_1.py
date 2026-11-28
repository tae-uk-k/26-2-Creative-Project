"""W-09-1 지도 연결(09 2·5·12장, 03 E11·E12·E18·E31, 04 7.2·8장).

연결 상태 전이표, [초대했어요], 관리자 연결 확인(수동 확인 모드·자동 작업), 정비안 만들기 조건,
초대 미도착 메일 1번만, 권한 회수(revoked·남은 칸 disconnected).
"읽은 값이 current_value에 저장"은 readCurrentValues(11단계) 테스트에서 본다.
"""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, FixPlan, FixPlanItem, FixRequest, MapConnection
from seelo.models.ops import AuditLog, EmailLog
from seelo.models.store import Store
from seelo.services import connection_service
from seelo.timeutil import now_utc
from tests.map_world import seed_store
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
OWNER, ADMIN = "owner@seelo.test", "admin@seelo.test"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        ADMIN_NOTIFY_EMAILS="ops@seelo.test",
        SEELO_GOOGLE_ACCOUNT_EMAIL="ops.google@seelo.test",
        SEELO_KAKAO_ACCOUNT_ID="seelo_kakao",
    )


async def _connecting(
    db: AsyncSession, status: str = "connecting", *, base: bool = True
) -> tuple[int, int, dict[str, int]]:
    """승인된 신청과 연결 2행. (store_id, request_id, {provider: connection_id})."""
    store_id, run_id = await seed_store(db, email=OWNER)
    await db.execute(text("UPDATE stores SET status = 'diagnosed' WHERE id = :i"), {"i": store_id})
    await db.execute(text("UPDATE measurement_runs SET status = 'completed' WHERE id = :i"), {"i": run_id})
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    req = FixRequest(user_id=owner_id, store_id=store_id, status=status, base_run_id=run_id if base else None)
    db.add(req)
    await db.flush()
    conns = {}
    for p in ("google", "kakao"):
        c = MapConnection(fix_request_id=req.id, provider=p, status="not_connected")
        db.add(c)
        await db.flush()
        conns[p] = c.id
    req_id = req.id
    await db.commit()
    return store_id, req_id, conns


async def _admin(db: AsyncSession) -> int:
    user = await make_user(db, ADMIN)
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": user.id})
    await db.commit()
    return user.id


async def _conn(db: AsyncSession, conn_id: int) -> MapConnection:
    db.expire_all()
    return await db.get(MapConnection, conn_id)


async def _set(db: AsyncSession, conn_id: int, **values: Any) -> None:
    await db.execute(update(MapConnection).where(MapConnection.id == conn_id).values(**values))
    await db.commit()


async def _jobs(db: AsyncSession, name: str) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text("SELECT args, queue_name, lock FROM procrastinate_jobs WHERE task_name = :n ORDER BY id"),
        {"n": name},
    )
    return [(r[0], r[1], r[2]) for r in rows]


# --- S15 ----------------------------------------------------------------------------------


async def test_connect_state_needs_approved_request(client: httpx.AsyncClient, db: AsyncSession) -> None:
    store_id, req_id, _ = await _connecting(db, "requested")
    await login(client, OWNER)
    r = await client.get("/api/fix/connect")
    assert r.status_code == 404
    await db.execute(text("UPDATE fix_requests SET status = 'connecting' WHERE id = :i"), {"i": req_id})
    await db.execute(
        text(
            "UPDATE store_sources SET match_status = 'not_found' WHERE store_id = :i AND provider = 'kakao'"
        ),
        {"i": store_id},
    )
    await db.commit()
    body = (await client.get("/api/fix/connect")).json()
    assert body["requestId"] == req_id
    assert body["seeloAccounts"] == {"google": "ops.google@seelo.test", "kakao": "seelo_kakao"}
    assert body["google"] == {
        "provider": "google", "status": "not_connected", "attentionReason": None, "invitedAt": None,
        "inviteNotArrived": False, "storeFoundOnMap": True, "canInvite": True,
    }  # fmt: skip
    assert body["kakao"]["storeFoundOnMap"] is False  # 화면이 카카오맵 등록 방법을 안내


async def test_invited_transitions(client: httpx.AsyncClient, db: AsyncSession) -> None:
    _, _, conns = await _connecting(db)
    await login(client, OWNER)
    r = await client.post("/api/fix/connect/google/invited")
    assert r.status_code == 200 and r.json()["status"] == "invited" and r.json()["canInvite"] is False
    first = (await _conn(db, conns["google"])).invited_at
    r = await client.post("/api/fix/connect/google/invited")  # 다시 눌러도 그대로
    assert r.status_code == 200 and (await _conn(db, conns["google"])).invited_at == first
    for prev in ("needs_attention", "revoked"):
        await _set(db, conns["kakao"], status=prev, attention_reason="other")
        r = await client.post("/api/fix/connect/kakao/invited")
        assert r.status_code == 200 and r.json()["status"] == "invited"
        assert (await _conn(db, conns["kakao"])).attention_reason is None
    await _set(db, conns["kakao"], status="connected")
    r = await client.post("/api/fix/connect/kakao/invited")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "connected"}
    assert (await client.post("/api/fix/connect/naver/invited")).status_code == 422


# --- E12 수동 확인 모드 ----------------------------------------------------------------------


async def test_manual_connected_creates_plan_mail_audit(client: httpx.AsyncClient, db: AsyncSession) -> None:
    admin_id = await _admin(db)
    store_id, req_id, conns = await _connecting(db)
    await login(client, ADMIN)
    r = await client.post(
        f"/api/admin/connections/{conns['google']}/verify",
        json={"manualResult": "connected", "externalRef": "locations/123"},
    )
    assert r.status_code == 200 and r.json() == {"status": "connected"}
    c = await _conn(db, conns["google"])
    assert (c.status, c.confirmed_by, c.external_ref, c.connected_at is not None) == (
        "connected", admin_id, "locations/123", True,
    )  # fmt: skip
    plan = await db.scalar(select(FixPlan))
    base = await db.scalar(select(FixRequest.base_run_id).where(FixRequest.id == req_id))
    assert (plan.provider, plan.version, plan.status, plan.base_run_id) == ("google", 1, "generating", base)
    # 수동 모드는 지금 값을 읽지 않아 plan 큐(기본 워커), lock 없음(11단계)
    assert await _jobs(db, "readCurrentValues") == [({"fix_plan_id": plan.id}, "plan", None)]
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "map_connection"))
    assert (mail.to_email, mail.template_params) == (OWNER, {"kind": "connected", "provider": "google"})
    audit = await db.scalar(select(AuditLog))
    assert (audit.action, audit.actor_id, audit.target_id, audit.detail) == (
        "connection.verify", admin_id, conns["google"],
        {"result": "connected", "attentionReason": None, "mode": "manual"},
    )  # fmt: skip
    # 이미 connected면 다시 확인할 수 없다
    r = await client.post(
        f"/api/admin/connections/{conns['google']}/verify", json={"manualResult": "connected"}
    )
    assert r.status_code == 409


async def test_manual_needs_attention_then_connected(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    _, _, conns = await _connecting(db)
    await login(client, ADMIN)
    url = f"/api/admin/connections/{conns['kakao']}/verify"
    r = await client.post(url, json={"manualResult": "needs_attention"})
    assert r.status_code == 422 and r.json()["error"]["details"] == {
        "fields": {"attentionReason": "required"}
    }
    r = await client.post(url, json={"manualResult": "needs_attention", "attentionReason": "bogus"})
    assert r.status_code == 422
    r = await client.post(
        url, json={"manualResult": "needs_attention", "attentionReason": "no_owner_authority"}
    )
    assert r.json() == {"status": "needs_attention"}
    c = await _conn(db, conns["kakao"])
    assert (c.status, c.attention_reason) == ("needs_attention", "no_owner_authority")
    assert (await client.post(url, json={"manualResult": "connected"})).json() == {"status": "connected"}
    assert (await _conn(db, conns["kakao"])).attention_reason is None
    assert await db.scalar(select(func.count()).select_from(AuditLog)) == 2


async def test_no_body_needs_auto_fix(client: httpx.AsyncClient, db: AsyncSession, settings_env: Any) -> None:
    admin_id = await _admin(db)
    _, _, conns = await _connecting(db)
    await login(client, ADMIN)
    url = f"/api/admin/connections/{conns['kakao']}/verify"
    r = await client.post(url)
    assert r.status_code == 422 and r.json()["error"]["details"] == {"fields": {"manualResult": "required"}}
    settings_env(AUTO_FIX_ENABLED="true")
    r = await client.post(url)
    assert r.status_code == 202 and r.json() == {}
    assert await _jobs(db, "verifyConnection") == [
        ({"connection_id": conns["kakao"], "requested_by": admin_id}, "fix", "fix:kakao")
    ]


async def test_owner_cannot_verify(client: httpx.AsyncClient, db: AsyncSession) -> None:
    _, _, conns = await _connecting(db)
    await login(client, OWNER)
    r = await client.post(
        f"/api/admin/connections/{conns['google']}/verify", json={"manualResult": "connected"}
    )
    assert r.status_code == 403


async def test_verify_needs_request_in_progress(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _admin(db)
    _, req_id, conns = await _connecting(db, "report_ready")
    await login(client, ADMIN)
    r = await client.post(
        f"/api/admin/connections/{conns['google']}/verify", json={"manualResult": "connected"}
    )
    assert r.status_code == 409 and r.json()["error"]["details"] == {"currentStatus": "report_ready"}
    assert (
        await client.post("/api/admin/connections/999/verify", json={"manualResult": "connected"})
    ).status_code == 404


# --- 정비안 만들기 조건(E12·E4) -------------------------------------------------------------


async def _connect(db: AsyncSession, req_id: int, provider: str) -> list[int]:
    """연결 성공 처리를 서비스로(관리자 없이)."""
    conn_id = await db.scalar(
        select(MapConnection.id).where(
            MapConnection.fix_request_id == req_id, MapConnection.provider == provider
        )
    )
    conn, req = await connection_service._locked(db, conn_id)
    await connection_service._apply_result(
        db,
        conn,
        req,
        result="connected",
        attention_reason=None,
        external_ref=None,
        actor_id=None,
        mode="manual",
    )
    await db.commit()
    return list((await db.scalars(select(FixPlan.id).where(FixPlan.provider == provider))).all())


async def test_plan_conditions(db: AsyncSession, fake_mailer: Any) -> None:
    # 신청이 approved(측정 먼저)면 연결돼도 정비안을 만들지 않는다
    _, req_id, _ = await _connecting(db, "approved", base=False)
    assert await _connect(db, req_id, "google") == []
    # E4로 connecting + 기준 측정이 생기면 이미 연결된 지도마다 만든다
    base = await db.scalar(text("SELECT id FROM measurement_runs LIMIT 1"))
    await db.execute(
        text("UPDATE fix_requests SET status = 'connecting', base_run_id = :b WHERE id = :i"),
        {"b": base, "i": req_id},
    )
    await db.commit()
    req = await db.get(FixRequest, req_id)
    await db.refresh(req)
    made = await connection_service.plans_for_connected(db, req)
    await db.commit()
    assert len(made) == 1


async def test_reconnect_does_not_duplicate_approved_plan(db: AsyncSession, fake_mailer: Any) -> None:
    _, req_id, conns = await _connecting(db, "fixing")
    db.add(FixPlan(fix_request_id=req_id, provider="google", version=1, status="approved"))
    db.add(FixPlan(fix_request_id=req_id, provider="kakao", version=1, status="generation_failed"))
    await db.commit()
    await _set(db, conns["google"], status="revoked")
    await _set(db, conns["google"], status="invited")
    assert await _connect(db, req_id, "google") == [1]  # 새 정비안 없음(승인된 1번만)
    kakao = await _connect(db, req_id, "kakao")
    versions = (await db.scalars(select(FixPlan.version).where(FixPlan.provider == "kakao"))).all()
    assert len(kakao) == 2 and sorted(versions) == [1, 2]  # 생성 실패만 있으면 새 버전


# --- 자동 확인 작업(AUTO_FIX_ENABLED=true, FakeMapAdmin) -------------------------------------


@pytest.mark.parametrize(
    ("setup", "status", "reason"),
    [
        (lambda a: None, "connected", None),
        (lambda a: a.not_visible(), "needs_attention", "store_not_visible"),
        (lambda a: a.needs_attention("verification_required"), "needs_attention", "verification_required"),
        (lambda a: a.transient_on("open", 1), "connected", None),  # 일시 오류 1번은 다시
    ],
)
async def test_verify_job_results(
    db: AsyncSession, map_admin: Any, settings_env: Any, setup: Any, status: str, reason: str | None
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    admin_id = await _admin(db)
    store_id, _, conns = await _connecting(db)
    setup(map_admin["google"])
    await connection_service.verify(conns["google"], admin_id)
    c = await _conn(db, conns["google"])
    assert (c.status, c.attention_reason) == (status, reason)
    if status == "connected":
        assert c.external_ref == f"fake-google-{store_id}" and c.confirmed_by == admin_id
    audit = await db.scalar(select(AuditLog))
    assert audit.detail["mode"] == "auto"


async def test_verify_job_blocked_keeps_state_and_mails_admin(
    db: AsyncSession, map_admin: Any, settings_env: Any
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    _, req_id, conns = await _connecting(db)
    await _set(db, conns["kakao"], status="invited", invited_at=now_utc())
    map_admin["kakao"].block_on("open")
    await connection_service.verify(conns["kakao"])
    c = await _conn(db, conns["kakao"])
    assert c.status == "invited"  # 상태는 바꾸지 않는다
    audit = await db.scalar(select(AuditLog))
    assert audit.detail == {"result": "blocked", "reason": "security_check", "mode": "auto"}
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "manual_required"))
    assert mail.to_email == "ops@seelo.test" and mail.template_params["request_id"] == req_id
    assert len([e for e in map_admin["kakao"].events if e[0] == "open"]) == 1  # 차단은 다시 시도하지 않음


async def test_verify_job_two_transient_errors_keep_state(
    db: AsyncSession, map_admin: Any, settings_env: Any
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    _, _, conns = await _connecting(db)
    map_admin["google"].transient_on("open", 2)
    await connection_service.verify(conns["google"])
    assert (await _conn(db, conns["google"])).status == "not_connected"
    assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0


# --- E31 초대 미도착 ---------------------------------------------------------------------------


async def test_invite_reminder_once(client: httpx.AsyncClient, db: AsyncSession) -> None:
    _, _, conns = await _connecting(db)
    now = now_utc()
    await _set(db, conns["google"], status="invited", invited_at=now - timedelta(days=3, minutes=1))
    await _set(db, conns["kakao"], status="invited", invited_at=now - timedelta(days=2, hours=23))
    assert await connection_service.check_pending_invites(db, now) == 1
    await db.commit()
    assert (
        await connection_service.check_pending_invites(db, now + timedelta(hours=1)) == 0
    )  # 두 번 돌려도 1통
    await db.commit()
    mails = (await db.scalars(select(EmailLog).where(EmailLog.type == "map_connection"))).all()
    assert [m.template_params for m in mails] == [{"kind": "reminder", "provider": "google"}]
    await login(client, OWNER)
    body = (await client.get("/api/fix/connect")).json()
    assert (body["google"]["inviteNotArrived"], body["kakao"]["inviteNotArrived"]) == (True, False)
    # 다시 [초대했어요]를 누르면 안내 표시는 초기화된다(needs_attention 등에서 다시 초대할 때)
    await _set(db, conns["google"], status="needs_attention")
    await client.post("/api/fix/connect/google/invited")
    assert (await _conn(db, conns["google"])).invite_reminder_sent_at is None


def test_check_pending_invites_is_hourly() -> None:
    import seelo.worker.periodic  # noqa: F401
    from seelo.worker.app import app

    crons = {t.task.name: t.cron for t in app.periodic_registry.periodic_tasks.values()}
    assert crons["checkPendingInvites"] == "15 * * * *"


# --- E18 권한 회수 ---------------------------------------------------------------------------


async def test_revoke_disconnects_remaining_items(client: httpx.AsyncClient, db: AsyncSession) -> None:
    _, req_id, conns = await _connecting(db, "fixing")
    await _set(db, conns["google"], status="connected")
    plan = FixPlan(fix_request_id=req_id, provider="google", version=1, status="approved")
    db.add(plan)
    await db.flush()
    statuses = ["queued", "pending_reflection", "manual_required", "applied"]
    for i, st in enumerate(statuses, 1):
        item = FixPlanItem(fix_plan_id=plan.id, order_no=i, field=f"f{i}")
        db.add(item)
        await db.flush()
        db.add(
            FixLog(
                fix_plan_item_id=item.id, fix_request_id=req_id, provider="google", field=f"f{i}",
                method="browser", applied_value="v", status=st,
            )
        )  # fmt: skip
    await db.commit()
    assert await connection_service.revoke(db, req_id, "google") is True
    await db.commit()
    db.expire_all()
    c = await db.get(MapConnection, conns["google"])
    assert (c.status, c.revoked_at is not None) == ("revoked", True)
    logs = {log_.field: log_.status for log_ in await db.scalars(select(FixLog))}
    assert logs == {"f1": "disconnected", "f2": "disconnected", "f3": "disconnected", "f4": "applied"}
    assert await _jobs(db, "finalizeFix") == [({"fix_request_id": req_id}, "plan", f"request:{req_id}")]
    assert await connection_service.revoke(db, req_id, "google") is False  # 이미 revoked
    await login(client, OWNER)
    home = (await client.get("/api/home")).json()
    assert home["revokedProviders"] == ["google"]
    view = (await client.get("/api/fix/connect")).json()["google"]
    assert (view["status"], view["canInvite"]) == ("revoked", True)
