"""W-10-2 메일 10종·dedupe·발송 실패의 상태 격리(10 4장)."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from seelo.db import session_scope
from seelo.models.fix import FixRequest, MapConnection
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import EmailLog
from seelo.models.report import ComparisonReport
from seelo.services import connection_service, email_service, remeasure_service, report_service
from seelo.services.email_render import render_email
from seelo.timeutil import now_utc
from tests.report_world import completed_remeasure
from tests.support import make_user
from tests.unit.test_security_render import SAMPLES

pytestmark = pytest.mark.usefixtures("queue_app")
ADMIN_TYPES = {"fix_requested", "manual_required"}
AUTH_TYPES = {"verify_email", "password_reset"}


@pytest.mark.parametrize("type_", list(SAMPLES))
async def test_ten_types_queue_job_and_send_once(db, fake_mailer, type_):
    owner = await make_user(db, "owner@seelo.test")
    params, secret, path = SAMPLES[type_]
    key = None if type_ in AUTH_TYPES else f"{type_}:event:1"
    kwargs = dict(params=params, secret=secret, dedupe_key=key)
    if type_ not in ADMIN_TYPES:
        kwargs["user"] = owner
    log_id = await email_service.queue(db, type_, **kwargs)
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(EmailLog)) == 1
    row = (
        await db.execute(
            text("SELECT args,queue_name,lock FROM procrastinate_jobs WHERE task_name='sendEmail'")
        )
    ).one()
    assert row == ({"email_log_id": log_id}, "email", f"email:{log_id}")
    if key:
        assert await email_service.queue(db, type_, **kwargs) is None
        await db.commit()
    assert await email_service.send(log_id) == "sent"
    assert await email_service.send(log_id) == "skip"
    assert len(fake_mailer.sent) == 1
    sent = fake_mailer.sent[0]
    expected_to = ["admin1@seelo.test", "admin2@seelo.test"] if type_ in ADMIN_TYPES else ["owner@seelo.test"]
    assert sent["to"] == expected_to
    assert "http://seelo.test" + path in sent["text"]
    assert "<html" in sent["html"] and "{{" not in sent["text"]
    db.expire_all()
    log = await db.get(EmailLog, log_id)
    assert log.secret_payload is None and log.status == "sent" and log.attempt == 1


@pytest.mark.parametrize("type_", sorted(AUTH_TYPES))
async def test_auth_new_request_can_send_new_link(db, type_):
    owner = await make_user(db, "owner@seelo.test")
    a = await email_service.queue(db, type_, user=owner, secret={"token": "first-link"})
    b = await email_service.queue(db, type_, user=owner, secret={"token": "new-link"})
    await db.commit()
    assert a != b


async def test_concurrent_dedupe_does_not_break_event_transaction(db):
    owner = await make_user(db, "owner@seelo.test")
    owner_id = owner.id

    async def enqueue():
        async with session_scope() as s:
            user = await s.get(type(owner), owner_id)
            result = await email_service.queue(
                s, "report_ready", user=user, params={"report_id": 1}, dedupe_key="report_ready:1"
            )
            await s.commit()
            return result

    values = await asyncio.gather(enqueue(), enqueue())
    assert sum(v is not None for v in values) == 1
    assert await db.scalar(select(func.count()).select_from(EmailLog)) == 1


@pytest.mark.parametrize("type_", ["diagnosis_result", "fix_completed", "report_ready"])
async def test_mail_failure_does_not_change_completed_domain_state(db, fake_mailer, type_):
    w = await completed_remeasure(db)
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    report_id = await db.scalar(select(ComparisonReport.id))
    await report_service.generate(report_id)
    db.expire_all()
    before = (
        (await db.get(MeasurementRun, w["run_id"])).status,
        (await db.get(MeasurementRun, w["after_id"])).status,
        (await db.get(FixRequest, w["request_id"])).status,
        (await db.get(ComparisonReport, report_id)).status,
    )
    params, secret, _ = SAMPLES[type_]
    log_id = await email_service.queue(
        db, type_, to="owner@seelo.test", params=params, secret=secret, dedupe_key=f"failure:{type_}"
    )
    await db.commit()
    fake_mailer.fail_times = 100
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await email_service.send(log_id)
    assert await email_service.send(log_id) == "failed"
    db.expire_all()
    after = (
        (await db.get(MeasurementRun, w["run_id"])).status,
        (await db.get(MeasurementRun, w["after_id"])).status,
        (await db.get(FixRequest, w["request_id"])).status,
        (await db.get(ComparisonReport, report_id)).status,
    )
    assert after == before == ("completed", "completed", "report_ready", "completed")


async def test_smtp_exception_cannot_leak_token_to_error_or_queue(db, fake_mailer, monkeypatch):
    secret = "SENSITIVE-EMAIL-LINK-TOKEN"
    log_id = await email_service.queue(db, "verify_email", to="owner@seelo.test", secret={"token": secret})
    await db.commit()

    async def fail(**kwargs):
        raise RuntimeError(f"server echoed {secret} password=hidden owner@seelo.test")

    monkeypatch.setattr(fake_mailer, "send", fail)
    with pytest.raises(ConnectionError) as error:
        await email_service.send(log_id)
    assert secret not in str(error.value) and "owner@seelo.test" not in str(error.value)
    db.expire_all()
    row = await db.get(EmailLog, log_id)
    assert row.error == "RuntimeError"
    assert secret not in str((await db.execute(text("SELECT args FROM procrastinate_jobs"))).all())


async def test_repeated_connection_block_dedupes_but_new_invite_sends(db, map_admin, settings_env):
    settings_env(AUTO_FIX_ENABLED="true")
    w = await completed_remeasure(db)
    await db.execute(
        text("UPDATE fix_requests SET status='connecting' WHERE id=:id"), {"id": w["request_id"]}
    )
    conn = await db.scalar(select(MapConnection).where(MapConnection.provider == "google"))
    conn.status, conn.invited_at = "invited", now_utc()
    connection_id = conn.id
    await db.commit()
    map_admin["google"].block_on()
    await connection_service.verify(connection_id)
    await connection_service.verify(connection_id)
    count = select(func.count()).select_from(EmailLog).where(EmailLog.type == "manual_required")
    assert await db.scalar(count) == 1
    db.expire_all()
    conn = await db.get(MapConnection, connection_id)
    conn.invited_at = now_utc() + timedelta(seconds=1)
    await db.commit()
    await connection_service.verify(connection_id)
    assert await db.scalar(count) == 2


@pytest.mark.parametrize("type_", [t for t in SAMPLES if t not in ADMIN_TYPES])
def test_owner_body_omits_findings_and_changed_values(type_):
    params, secret, _ = SAMPLES[type_]
    params = {
        **params,
        "findings": [{"title": "PRIVATE-FINDING-TITLE"}],
        "before_value": "PRIVATE-BEFORE",
        "applied_value": "PRIVATE-APPLIED",
        "content": "PRIVATE-REPORT",
    }
    mail = render_email(type_, params, secret)
    assert all(
        word not in mail.text + mail.html
        for word in ("PRIVATE-FINDING-TITLE", "PRIVATE-BEFORE", "PRIVATE-APPLIED", "PRIVATE-REPORT")
    )


@pytest.mark.parametrize(
    "type_,params,secret,path",
    [
        ("password_reset", {"social_provider": "google"}, None, "/login"),
        ("password_reset", {"social_provider": "kakao"}, None, "/login"),
        ("diagnosis_result", {"result": "failed", "run_id": 1}, None, "/home"),
        ("fix_decided", {"decision": "approved"}, None, "/fix/connect"),
        ("map_connection", {"kind": "reminder", "provider": "google"}, None, "/fix/connect"),
        ("map_connection", {"kind": "connected", "provider": "google"}, None, "/fix/connect"),
    ],
)
def test_template_variants(type_, params, secret, path):
    mail = render_email(type_, params, secret)
    assert mail.link == "http://seelo.test" + path
    assert "{{" not in mail.text and mail.text.endswith("이 메일은 발신 전용이에요.")
