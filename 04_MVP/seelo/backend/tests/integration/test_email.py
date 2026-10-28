"""2단계: 메일 등록·발송(W-10-1, 10 4장)."""

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.ops import EmailLog
from seelo.models.user import User
from seelo.services import email_service
from seelo.timeutil import now_utc
from seelo.worker.tasks_email import send_email


async def _log(db: AsyncSession, log_id: int) -> EmailLog:
    db.expire_all()
    row = await db.get(EmailLog, log_id)
    assert row is not None
    return row


async def test_queue_stores_secret_encrypted_and_job_args_only_id(db: AsyncSession, queue_app: Any) -> None:
    user = User(email="owner@seelo.test", terms_agreed_at=now_utc())
    db.add(user)
    await db.flush()
    log_id = await email_service.queue(db, "verify_email", user=user, secret={"token": "PLAIN-LINK-TOKEN"})
    await db.commit()

    row = await _log(db, log_id)
    assert row.to_email == "owner@seelo.test" and row.status == "queued" and row.attempt == 0
    assert row.secret_payload is not None and b"PLAIN-LINK-TOKEN" not in row.secret_payload
    jobs = (await db.execute(text("SELECT task_name, queue_name, args FROM procrastinate_jobs"))).all()
    assert [(j.task_name, j.queue_name, j.args) for j in jobs] == [
        ("sendEmail", "email", {"email_log_id": log_id})
    ]


async def test_queue_dedupe_and_admin_recipients(db: AsyncSession, queue_app: Any) -> None:
    params = {"request_id": 5, "store_name": "데모식당"}
    first = await email_service.queue(db, "fix_requested", params=params, dedupe_key="fix_requested:5")
    second = await email_service.queue(db, "fix_requested", params=params, dedupe_key="fix_requested:5")
    await db.commit()
    assert first is not None and second is None
    row = await _log(db, first)
    assert row.to_email == "admin1@seelo.test,admin2@seelo.test" and row.user_id is None
    count = (await db.execute(text("SELECT count(*) FROM procrastinate_jobs"))).scalar()
    assert count == 1


def test_retry_strategy_matches_max_attempts() -> None:
    assert send_email.retry_strategy.max_attempts == email_service.MAX_ATTEMPTS - 1


async def test_send_success_clears_secret(db: AsyncSession, queue_app: Any, fake_mailer: Any) -> None:
    log_id = await email_service.queue(
        db, "password_reset", to="o@seelo.test", params={"social_provider": None}, secret={"token": "T1"}
    )
    await db.commit()

    assert await email_service.send(log_id) == "sent"
    row = await _log(db, log_id)
    assert (
        row.status == "sent" and row.sent_at is not None and row.secret_payload is None and row.attempt == 1
    )
    mail = fake_mailer.sent[0]
    assert mail["to"] == ["o@seelo.test"] and "http://seelo.test/password/reset/T1" in mail["text"]
    # 이미 보낸 메일은 다시 보내지 않는다(작업이 두 번 실행돼도 안전)
    assert await email_service.send(log_id) == "skip"
    assert len(fake_mailer.sent) == 1


async def test_send_fails_after_three_retries(db: AsyncSession, queue_app: Any, fake_mailer: Any) -> None:
    """W-10-1: 발송 실패 → 재시도 3번(총 4번 시도) → failed, secret_payload 삭제."""
    fake_mailer.fail_times = 99
    log_id = await email_service.queue(db, "verify_email", to="o@seelo.test", secret={"token": "T2"})
    await db.commit()

    for attempt in (1, 2, 3):
        with pytest.raises(ConnectionError):
            await email_service.send(log_id)
        row = await _log(db, log_id)
        assert row.status == "queued" and row.attempt == attempt
        assert row.secret_payload is not None
        assert row.error is not None and "o@seelo.test" not in row.error  # 주소는 가린다
    assert await email_service.send(log_id) == "failed"
    row = await _log(db, log_id)
    assert row.status == "failed" and row.attempt == 4 and row.secret_payload is None and row.sent_at is None
    assert fake_mailer.sent == []


async def test_send_recovers_on_retry(db: AsyncSession, queue_app: Any, fake_mailer: Any) -> None:
    fake_mailer.fail_times = 2
    log_id = await email_service.queue(db, "report_ready", to="o@seelo.test", params={"report_id": 1})
    await db.commit()
    for _ in range(2):
        with pytest.raises(ConnectionError):
            await email_service.send(log_id)
    assert await email_service.send(log_id) == "sent"
    row = await _log(db, log_id)
    assert row.status == "sent" and row.attempt == 3 and row.error is None


async def test_render_failure_is_final(db: AsyncSession, queue_app: Any, fake_mailer: Any) -> None:
    log_id = await email_service.queue(db, "fix_requested", to="o@seelo.test", params={"request_id": 1})
    await db.commit()
    assert await email_service.send(log_id) == "failed"
    row = await _log(db, log_id)
    assert row.status == "failed" and row.attempt == 1 and row.error.startswith("render:")
    assert fake_mailer.calls == 0


async def test_user_delete_cascades_email_logs(db: AsyncSession, queue_app: Any) -> None:
    user = User(email="gone@seelo.test", terms_agreed_at=now_utc())
    db.add(user)
    await db.flush()
    await email_service.queue(db, "verify_email", user=user, secret={"token": "T3"})
    await db.commit()
    await db.delete(user)
    await db.commit()
    assert (await db.scalars(select(EmailLog.id))).all() == []
