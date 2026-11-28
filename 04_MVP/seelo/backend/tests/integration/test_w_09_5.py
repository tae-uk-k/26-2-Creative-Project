"""W-09-5 자동 정비 applyFix(09 9장, 03 E16): 가짜 관리 화면(FakeMapAdmin).

- 칸 수정·다시 읽기. **before_value 커밋이 쓰기보다 먼저**.
- 차단 → 즉시 중단, 재시도 0번, 그 칸과 남은 칸 manual_required, 관리자 메일.
- 일시 오류는 1번 다시, 쓸 수 없는 칸은 그 칸만 수동. 가게 안 보임 → 권한 회수. 정비 완료 뒤 쓰기 0번.
- PoC 전(셀렉터 파일 비어 있음) 실제 연동은 화면을 열지 않고 수동 처리로 넘긴다.
"""

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import session_scope
from seelo.integrations.browser.guards import AutomationBlocked
from seelo.integrations.map_admins import real_map_admin
from seelo.models.fix import FixLog, FixRequest, MapConnection
from seelo.models.ops import EmailLog
from seelo.services import fix_apply_service
from tests.map_world import approved_plan, seed_plan_world

pytestmark = pytest.mark.usefixtures("queue_app")
ITEMS = {"description": "명동의 칼국수 집이에요.", "website": "https://demo.example/", "phone": "02-776-0000"}
OLD = {"description": "옛 소개", "website": "https://old.example/", "phone": "02-111-2222"}


@pytest.fixture(autouse=True)
def _auto(settings_env: Any) -> None:
    settings_env(AUTO_FIX_ENABLED="true", ADMIN_NOTIFY_EMAILS="ops@seelo.test")


async def _world(db: AsyncSession, map_admin: Any, items: dict[str, Any] = ITEMS) -> dict[str, Any]:
    w = await seed_plan_world(db)
    map_admin["google"].values.update(OLD)
    return w | await approved_plan(db, w, "google", items)


async def _logs(db: AsyncSession) -> dict[str, FixLog]:
    db.expire_all()
    return {lg.field: lg for lg in await db.scalars(select(FixLog))}


async def _mails(db: AsyncSession) -> list[EmailLog]:
    q = select(EmailLog).where(EmailLog.type == "manual_required").order_by(EmailLog.id)
    return list((await db.scalars(q)).all())


async def _jobs(db: AsyncSession, name: str) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text(
            "SELECT args, queue_name, lock FROM procrastinate_jobs WHERE task_name = :n AND status = 'todo'"
        ),
        {"n": name},
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _writes(admin: Any) -> list[str]:
    return [e[1] for e in admin.events if e[0] == "write"]


async def test_writes_approved_fields_and_reads_again(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    committed: dict[str, Any] = {}

    async def before_write(field_: str) -> None:  # 쓰기 직전, 다른 연결로 본 DB
        async with session_scope() as s:
            lg = await s.get(FixLog, w["logs"][field_])
            committed[field_] = (lg.before_value, lg.attempt)

    g = map_admin["google"]
    g.before_write = before_write
    await fix_apply_service.apply(w["plan_id"])
    assert committed == {f: (OLD[f], 1) for f in ITEMS}  # before_value·attempt가 쓰기보다 먼저 커밋
    logs = await _logs(db)
    for f in ITEMS:
        lg = logs[f]
        assert (lg.status, lg.before_value, lg.attempt) == ("applied", OLD[f], 1)
        assert lg.applied_at is not None and lg.verified_at is not None
    assert g.values == ITEMS
    assert [e[0] for e in g.events] == ["open"] + [
        "read",
        "write",
        "read",
    ] * 3  # 칸마다 읽기 → 쓰기 → 다시 읽기
    rid = w["request_id"]
    assert await _jobs(db, "finalizeFix") == [({"fix_request_id": rid}, "plan", f"request:{rid}")]
    await fix_apply_service.finalize(rid)
    assert (await db.get(FixRequest, rid)).status == "remeasure_scheduled"
    # 정비 완료 뒤 다시 불러도 쓰지 않는다(queued 칸 없음)
    await fix_apply_service.apply(w["plan_id"])
    assert len(_writes(g)) == 3 and map_admin.opened == ["google"]


async def test_not_reflected_yet_is_pending(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    map_admin["google"].delay_reflection("description")
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    d = logs["description"]
    assert d.status == "pending_reflection" and d.applied_at is not None and d.last_checked_at is not None
    assert d.verified_at is None
    assert logs["website"].status == "applied"


@pytest.mark.parametrize("where", ["open", "first_write"])
async def test_blocked_stops_without_retry(db: AsyncSession, map_admin: Any, where: str) -> None:
    w = await _world(db, map_admin)
    g = map_admin["google"]
    if where == "open":
        g.block_on("open")
    else:
        g.block_first_write = True
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    assert {(lg.status, lg.manual_reason, lg.error_code) for lg in logs.values()} == {
        ("manual_required", "automation_blocked", "security_check")
    }  # 그 칸과 남은 칸 모두
    assert len(_writes(g)) == (0 if where == "open" else 1)  # 다시 시도 0번
    (mail,) = await _mails(db)
    assert (
        mail.to_email == "ops@seelo.test"
        and mail.dedupe_key == f"manual_required:plan:{w['plan_id']}:blocked"
    )
    assert [i["field_label"] for i in mail.template_params["items"]] == ["가게 소개", "웹사이트", "전화번호"]


async def test_transient_retry_once_then_that_field_only(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    g = map_admin["google"]
    g.transient_on("description", 1)  # 한 번 실패 → 다시 해서 성공
    g.transient_on("website", 2)  # 두 번 실패 → 그 칸만 수동
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    assert (logs["description"].status, logs["description"].attempt) == ("applied", 2)
    assert logs["description"].before_value == OLD["description"]  # 다시 해도 처음 읽은 값
    web = logs["website"]
    assert (web.status, web.manual_reason, web.error_code, web.attempt) == (
        "manual_required", "write_failed", "transient", 2,
    )  # fmt: skip
    assert logs["phone"].status == "applied"  # 다음 칸은 계속
    (mail,) = await _mails(db)
    assert mail.dedupe_key == f"manual_required:plan:{w['plan_id']}:write_failed"
    assert mail.template_params["items"] == [
        {"provider": "google", "field_label": "웹사이트", "reason": "write_failed"}
    ]


async def test_field_without_screen_goes_manual(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    map_admin["google"].fail_write("phone")
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    assert (logs["phone"].status, logs["phone"].error_code) == ("manual_required", "unsupported_field")
    assert logs["description"].status == logs["website"].status == "applied"


async def test_store_not_visible_revokes(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    map_admin["google"].not_visible()
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    assert {lg.status for lg in logs.values()} == {"disconnected"}
    conn = await db.get(MapConnection, w["connections"]["google"])
    assert conn.status == "revoked" and conn.revoked_at is not None
    assert _writes(map_admin["google"]) == []


async def test_skip_when_not_approved_or_disconnected(db: AsyncSession, map_admin: Any) -> None:
    w = await _world(db, map_admin)
    await db.execute(
        text("UPDATE fix_plans SET status = 'awaiting_approval' WHERE id = :i"), {"i": w["plan_id"]}
    )
    await db.commit()
    await fix_apply_service.apply(w["plan_id"])
    await db.execute(text("UPDATE fix_plans SET status = 'approved' WHERE id = :i"), {"i": w["plan_id"]})
    await db.execute(
        text("UPDATE map_connections SET status = 'revoked' WHERE id = :i"), {"i": w["connections"]["google"]}
    )
    await db.commit()
    await fix_apply_service.apply(w["plan_id"])
    assert map_admin.opened == [] and {lg.status for lg in (await _logs(db)).values()} == {"queued"}


async def test_real_screens_before_poc_go_manual(db: AsyncSession, map_admin: Any) -> None:
    """실제 연동(셀렉터 파일이 비어 있음)은 브라우저를 열지 않고 남은 칸을 모두 수동 처리로 넘긴다."""
    import dataclasses

    from seelo.integrations import get_clients, set_clients

    with pytest.raises(AutomationBlocked) as e:
        async with real_map_admin("kakao"):
            pass
    assert e.value.reason == "selectors_missing"
    w = await _world(db, map_admin)
    set_clients(dataclasses.replace(get_clients(), map_admin=real_map_admin))
    await fix_apply_service.apply(w["plan_id"])
    logs = await _logs(db)
    assert {(lg.status, lg.manual_reason, lg.error_code) for lg in logs.values()} == {
        ("manual_required", "automation_blocked", "selectors_missing")
    }
