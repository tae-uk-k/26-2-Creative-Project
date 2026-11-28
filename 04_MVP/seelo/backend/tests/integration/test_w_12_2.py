"""W-12-2 읽기 전용 비교·보고서·재생성(E21·E22·E24)."""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import func, select, text

from seelo.integrations import get_clients
from seelo.integrations.map_admins import real_map_admin
from seelo.models.fix import FixLog, FixRequest, MapConnection
from seelo.models.ops import AuditLog, EmailLog, JobLink
from seelo.models.report import ComparisonReport
from seelo.services import remeasure_service, report_service
from tests.map_world import approved_plan, g_detail, seed_google_snapshot
from tests.report_world import completed_remeasure
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


async def test_manual_compare_places_unknown_no_writes_and_idempotent(db, map_admin, settings_env):
    settings_env(AUTO_FIX_ENABLED="false")
    w = await completed_remeasure(db)
    g = g_detail("G1", "명동교자")
    g["nationalPhoneNumber"] = "02-123-4567"
    await seed_google_snapshot(db, w["store_id"], w["after_id"], g)
    await asyncio.gather(
        *[remeasure_service.compare_fix_values(w["request_id"], w["after_id"]) for _ in range(2)]
    )
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    db.expire_all()
    phone = await db.get(FixLog, w["logs"]["phone"])
    description = await db.get(FixLog, w["logs"]["description"])
    assert phone.remeasure_match == "match" and phone.remeasure_value == "02-123-4567"
    assert description.remeasure_match == "unknown" and description.remeasure_value is None
    assert map_admin.opened == []
    assert await db.scalar(select(func.count()).select_from(ComparisonReport)) == 1
    assert (
        await db.scalar(
            select(func.count()).select_from(JobLink).where(JobLink.task_name == "generateComparisonReport")
        )
        == 1
    )
    report = await db.scalar(select(ComparisonReport))
    assert report.interval_days == 14
    await report_service.generate(report.id)
    await report_service.generate(report.id)
    db.expire_all()
    report = await db.scalar(select(ComparisonReport))
    assert report.status == "completed"
    assert report.content["changes"][0]["beforeValue"] == "확인하지 못함"
    assert (await db.get(FixRequest, w["request_id"])).status == "report_ready"
    assert (
        await db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.type == "report_ready"))
        == 1
    )


@pytest.mark.parametrize("mode", ["match", "differs", "blocked", "revoked", "selectors_missing"])
async def test_admin_read_failures_continue_without_write(db, map_admin, settings_env, mode):
    settings_env(AUTO_FIX_ENABLED="true", KAKAO_FIX_ENABLED="true")
    w = await completed_remeasure(db)
    kp = await approved_plan(db, w, "kakao", {"intro": "설명"}, status="manual_done")
    await db.execute(
        text("UPDATE fix_requests SET status='remeasuring' WHERE id=:id"), {"id": w["request_id"]}
    )
    await db.commit()
    map_admin["google"].values["description"] = "Seelo cafe"
    map_admin["kakao"].values["intro"] = "설명" if mode == "match" else "다른 설명"
    if mode == "blocked":
        map_admin["kakao"].block_on()
    if mode == "revoked":
        map_admin["kakao"].not_visible()
    clients = replace(get_clients(), map_admin=real_map_admin) if mode == "selectors_missing" else None
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"], clients=clients)
    db.expire_all()
    lg = await db.get(FixLog, kp["logs"]["intro"])
    expected = mode if mode in {"match", "differs"} else "unknown"
    assert lg.remeasure_match == expected
    if mode == "revoked":
        conn = await db.scalar(select(MapConnection).where(MapConnection.provider == "kakao"))
        assert conn.status == "revoked"
    assert all(e[0] != "write" for p in ("google", "kakao") for e in map_admin[p].events)
    report = await db.scalar(select(ComparisonReport))
    report_id = report.id
    await report_service.generate(report_id)
    db.expire_all()
    assert (await db.get(ComparisonReport, report_id)).status == "completed"


async def test_queue_selection_without_fix_worker(db, settings_env):
    w = await completed_remeasure(db)
    settings_env(AUTO_FIX_ENABLED="false")
    await remeasure_service.defer_compare(db, w["request_id"], w["after_id"], w["store_id"])
    await db.commit()
    row = (
        await db.execute(
            text("SELECT queue_name, lock FROM procrastinate_jobs WHERE task_name='compareFixValues'")
        )
    ).one()
    assert row == ("plan", None)


async def test_google_hours_with_optional_notes_is_comparable(db, settings_env):
    from seelo.domain.hours import from_google_periods
    from seelo.models.fix import FixPlanItem

    settings_env(AUTO_FIX_ENABLED="false")
    w = await completed_remeasure(db)
    periods = [{"open": {"day": 1, "hour": 11, "minute": 0}, "close": {"day": 1, "hour": 21, "minute": 0}}]
    hours = from_google_periods(periods)
    item = FixPlanItem(fix_plan_id=w["plan_id"], order_no=3, field="regular_hours", approved_value=hours)
    db.add(item)
    await db.flush()
    lg = FixLog(
        fix_plan_item_id=item.id,
        fix_request_id=w["request_id"],
        provider="google",
        field="regular_hours",
        method="manual",
        applied_value=hours,
        status="manual_done",
    )
    db.add(lg)
    await db.flush()
    log_id = lg.id
    await db.commit()
    g = g_detail("G1", "명동교자")
    g["regularOpeningHours"] = {"periods": periods}
    await seed_google_snapshot(db, w["store_id"], w["after_id"], g)
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    db.expire_all()
    assert (await db.get(FixLog, log_id)).remeasure_match == "match"


async def test_generation_retry_then_new_version_api(db, client, monkeypatch):
    w = await completed_remeasure(db)
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    report_id = await db.scalar(select(ComparisonReport.id))
    original = report_service.report_builder.build_report

    def broken(**kwargs):
        raise ValueError("report_banned_term")

    monkeypatch.setattr(report_service.report_builder, "build_report", broken)
    await report_service.generate(report_id)
    db.expire_all()
    first = await db.get(ComparisonReport, report_id)
    assert first.status == "generating" and first.generation_attempts == 1
    await report_service.generate(report_id)
    db.expire_all()
    first = await db.get(ComparisonReport, report_id)
    assert (first.status, first.generation_attempts, first.last_error) == (
        "generation_failed",
        2,
        "banned_term",
    )
    assert (await db.get(FixRequest, w["request_id"])).status == "remeasuring"
    admin = await make_user(db, "admin@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, "admin@seelo.test")
    path = f"/api/admin/fix-requests/{w['request_id']}/report/regenerate"
    r = await client.post(path)
    assert r.status_code == 202, r.text
    new_id = r.json()["reportId"]
    assert new_id != report_id
    assert (await client.post(path)).status_code == 409
    monkeypatch.setattr(report_service.report_builder, "build_report", original)
    await report_service.generate(new_id)
    db.expire_all()
    assert (await db.get(ComparisonReport, report_id)).status == "generation_failed"
    new = await db.get(ComparisonReport, new_id)
    assert (new.status, new.version) == ("completed", 2)
    assert (
        await db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "report.regenerate")
        )
        == 1
    )
