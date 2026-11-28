"""W-09-6 카카오 자동 정비·반영 확인(09 9·10장, 03 E16·E32).

- 카카오도 W-09-5와 같은 차단 처리.
- pending_reflection이 1시간마다 확인되고(verifyFix는 읽기만, 쓰기 0번)
  24시간 뒤 manual_required(not_reflected_24h).
- 반영되면 applied. 확인 중 가게가 안 보이면 권한 회수, 차단이면 상태 그대로.
- KAKAO_FIX_ENABLED=false면 승인 즉시 manual_required(W-09-4 test_kakao_fix_disabled).
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.fix import FixLog, MapConnection
from seelo.models.ops import EmailLog
from seelo.services import fix_apply_service
from tests.map_world import approved_plan, seed_plan_world

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _auto(settings_env: Any) -> None:
    settings_env(AUTO_FIX_ENABLED="true", KAKAO_FIX_ENABLED="true", ADMIN_NOTIFY_EMAILS="ops@seelo.test")


async def _pending(db: AsyncSession, map_admin: Any) -> dict[str, Any]:
    """카카오 한 줄 소개를 썼지만 아직 반영 안 됨(pending_reflection)."""
    w = await seed_plan_world(db)
    k = map_admin["kakao"]
    k.values["intro"] = "옛 소개"
    k.delay_reflection("intro")
    w |= await approved_plan(db, w, "kakao", {"intro": "명동 칼국수 맛집"})
    await fix_apply_service.apply(w["plan_id"])
    return w


async def _log(db: AsyncSession, log_id: int) -> FixLog:
    db.expire_all()
    return await db.get(FixLog, log_id)


async def _verify_jobs(db: AsyncSession) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text(
            "SELECT args, queue_name, lock FROM procrastinate_jobs"
            " WHERE task_name = 'verifyFix' AND status = 'todo' ORDER BY id"
        )
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _writes(admin: Any) -> int:
    return sum(1 for e in admin.events if e[0] == "write")


async def test_kakao_apply_pending_then_reflected(db: AsyncSession, map_admin: Any) -> None:
    w = await _pending(db, map_admin)
    lid = w["logs"]["intro"]
    lg = await _log(db, lid)
    assert (lg.status, lg.before_value) == ("pending_reflection", "옛 소개")
    k = map_admin["kakao"]
    await fix_apply_service.verify(lid, 1)  # 아직 반영 안 됨
    lg = await _log(db, lid)
    assert (lg.status, lg.verify_count) == ("pending_reflection", 1)
    k.reflect("intro")
    await fix_apply_service.verify(lid, 2)
    lg = await _log(db, lid)
    assert lg.status == "applied" and lg.verified_at is not None
    assert _writes(k) == 1  # 확인은 읽기만


async def test_hourly_checks_for_24h_then_manual(db: AsyncSession, map_admin: Any) -> None:
    w = await _pending(db, map_admin)
    lid = w["logs"]["intro"]
    applied_at = (await _log(db, lid)).applied_at
    # 처음 55분 안에는 확인하지 않는다
    assert await fix_apply_service.recheck_pending(db, applied_at + timedelta(minutes=30)) == {
        "expired": 0,
        "verify": 0,
    }
    for h in range(1, 24):
        now = applied_at + timedelta(hours=h, minutes=1)
        counts = await fix_apply_service.recheck_pending(db, now)
        await db.commit()
        assert counts == {"expired": 0, "verify": 1}
        assert await fix_apply_service.recheck_pending(db, now) == {
            "expired": 0,
            "verify": 1,
        }  # 같은 시각 두 번
        await db.commit()
        ((args, queue, lock),) = await _verify_jobs(db)  # queueing_lock으로 하나
        assert (args, queue, lock) == ({"fix_log_id": lid, "round": h}, "fix", "fix:kakao")
        await db.execute(
            text("UPDATE procrastinate_jobs SET status = 'succeeded' WHERE task_name = 'verifyFix'")
        )
        await db.commit()
        await fix_apply_service.verify(lid, h)
        await db.execute(
            text("UPDATE fix_logs SET last_checked_at = :t WHERE id = :i"), {"t": now, "i": lid}
        )  # 확인 시각을 시험 시계에 맞춘다
        await db.commit()
    lg = await _log(db, lid)
    assert (lg.status, lg.verify_count) == ("pending_reflection", 23)
    counts = await fix_apply_service.recheck_pending(db, applied_at + timedelta(hours=24))
    await db.commit()
    assert counts == {"expired": 1, "verify": 0}
    lg = await _log(db, lid)
    assert (lg.status, lg.manual_reason) == ("manual_required", "not_reflected_24h")
    assert _writes(map_admin["kakao"]) == 1  # 24시간 동안 쓰기 0번(처음 쓰기 1번뿐)
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "manual_required"))
    assert mail.dedupe_key == f"manual_required:log:{lid}"
    assert mail.template_params["items"] == [
        {"provider": "kakao", "field_label": "한 줄 소개", "reason": "not_reflected_24h"}
    ]
    finalize = await db.execute(
        text("SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'finalizeFix' AND status = 'todo'")
    )
    assert finalize.scalar_one() == 1


async def test_verify_blocked_keeps_state_and_not_visible_revokes(db: AsyncSession, map_admin: Any) -> None:
    w = await _pending(db, map_admin)
    lid = w["logs"]["intro"]
    k = map_admin["kakao"]
    k.block_on("open")
    await fix_apply_service.verify(lid, 1)
    lg = await _log(db, lid)
    assert (lg.status, lg.verify_count) == ("pending_reflection", 0)  # 다음 시각에 다시
    k.blocked.clear()
    k.not_visible()
    await fix_apply_service.verify(lid, 1)
    assert (await _log(db, lid)).status == "disconnected"
    assert (await db.get(MapConnection, w["connections"]["kakao"])).status == "revoked"


async def test_kakao_blocked_like_google(db: AsyncSession, map_admin: Any) -> None:
    w = await seed_plan_world(db)
    map_admin["kakao"].block_first_write = True
    w |= await approved_plan(
        db, w, "kakao", {"intro": "명동 칼국수 맛집", "links": ["https://demo.example/"]}
    )
    await fix_apply_service.apply(w["plan_id"])
    db.expire_all()
    logs = (await db.scalars(select(FixLog))).all()
    assert {(lg.status, lg.manual_reason) for lg in logs} == {("manual_required", "automation_blocked")}
    assert _writes(map_admin["kakao"]) == 1
