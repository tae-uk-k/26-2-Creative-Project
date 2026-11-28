"""메일 등록·발송(10 4장, 13 13장).

- queue(): 사건 트랜잭션 안에서 email_logs 행을 만들고 sendEmail 작업을 같은 트랜잭션에 등록한다.
  메일 링크 토큰 같은 비밀 값은 secret_payload에 Fernet 암호문으로만 둔다.
- send(): sendEmail 작업 본체. 실패하면 예외를 다시 던져 Procrastinate가 재시도하게 하고,
  마지막(4번째) 시도도 실패하면 failed로 끝낸다. 성공·최종 실패 때 secret_payload를 지운다.
- 발송 실패는 측정·정비·보고서 상태를 바꾸지 않는다(W-10-2).
"""

from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.states import EmailStatus, EmailType, transition
from seelo.integrations import Clients, get_clients
from seelo.logging import mask_text
from seelo.models.ops import EmailLog
from seelo.models.user import User
from seelo.security.crypto import decrypt_json, encrypt_json
from seelo.services import jobs
from seelo.services.email_render import render_email
from seelo.timeutil import now_utc

log = structlog.get_logger()

MAX_ATTEMPTS = 4  # 처음 1번 + 재시도 3번(06 4장 sendEmail의 RetryStrategy와 같아야 한다)


async def queue(
    session: AsyncSession,
    type_: EmailType | str,
    *,
    user: User | None = None,
    to: str | None = None,
    params: dict[str, Any] | None = None,
    secret: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> int | None:
    """메일 한 통을 등록한다. 커밋은 부르는 쪽. 받는 사람이 없거나 같은 dedupe_key가 있으면 None.

    받는 사람: to(직접 지정) → user.email → 관리자 주소(ADMIN_NOTIFY_EMAILS).
    """
    type_ = EmailType(type_)
    recipient = to or (user.email if user is not None else ",".join(get_settings().admin_emails))
    if not recipient:
        log.warning("email_no_recipient", type=str(type_))
        return None
    stmt = (
        insert(EmailLog)
        .values(
            user_id=user.id if user is not None else None,
            type=str(type_),
            to_email=recipient,
            template_params=params or {},
            secret_payload=encrypt_json(secret) if secret else None,
            dedupe_key=dedupe_key,
            status=str(EmailStatus.QUEUED),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(EmailLog.id)
    )
    log_id = await session.scalar(stmt)
    if log_id is None:
        log.info("email_deduped", type=str(type_), dedupe_key=dedupe_key)
        return None
    from seelo.worker.tasks_email import send_email  # 순환 import 방지

    await jobs.defer(
        session,
        send_email,
        args={"email_log_id": log_id},
        links=jobs.JobLinks(),
        queueing_lock=f"email:{log_id}",
        lock=f"email:{log_id}",
    )
    return log_id


async def send(email_log_id: int, *, clients: Clients | None = None) -> str:
    """메일 한 통을 보낸다. 반환값: sent|failed|retry|skip. retry면 예외를 다시 던진다."""
    clients = clients or get_clients()

    # 1) 읽고 시도 횟수 올리기(외부 호출 전에 트랜잭션을 닫는다)
    async with session_scope() as s:
        row = await s.get(EmailLog, email_log_id)
        if row is None or row.status != EmailStatus.QUEUED:
            log.info("email_skip", email_log_id=email_log_id)
            return "skip"
        row.attempt += 1
        attempt = row.attempt
        type_, to_email = row.type, row.to_email
        params = dict(row.template_params or {})
        secret = decrypt_json(row.secret_payload) if row.secret_payload else None
        await s.commit()

    # 2) 렌더(실패하면 재시도해도 소용없으므로 바로 최종 실패)
    try:
        rendered = render_email(type_, params, secret)
    except Exception as e:
        await _finish(email_log_id, ok=False, error=f"render: {type(e).__name__}")
        log.error("email_render_failed", email_log_id=email_log_id, type=type_, error_type=type(e).__name__)
        return "failed"

    # 3) 발송
    to_list = [a.strip() for a in to_email.split(",") if a.strip()]
    try:
        await clients.mailer.send(
            to=to_list, subject=rendered.subject, text=rendered.text, html=rendered.html
        )
    except Exception as e:
        error = type(e).__name__
        if attempt >= MAX_ATTEMPTS:
            await _finish(email_log_id, ok=False, error=error)
            log.error("email_failed", email_log_id=email_log_id, type=type_, attempt=attempt)
            return "failed"
        async with session_scope() as s:
            row = await s.get(EmailLog, email_log_id)
            if row is not None:
                row.error = mask_text(error)[:500]
                await s.commit()
        log.warning("email_retry", email_log_id=email_log_id, type=type_, attempt=attempt)
        # SMTP 서버가 오류에 본문·인증 값을 돌려줘도 작업 로그에는 남기지 않는다(10 4장).
        raise ConnectionError(f"smtp: {type(e).__name__}") from None

    await _finish(email_log_id, ok=True, error=None)
    log.info("email_sent", email_log_id=email_log_id, type=type_, attempt=attempt)
    return "sent"


async def _finish(email_log_id: int, *, ok: bool, error: str | None) -> None:
    async with session_scope() as s:
        values: dict[str, Any] = {"secret_payload": None, "error": mask_text(error)[:500] if error else None}
        if ok:
            values["sent_at"] = now_utc()
        await transition(
            s,
            EmailLog,
            email_log_id,
            from_={EmailStatus.QUEUED},
            to=EmailStatus.SENT if ok else EmailStatus.FAILED,
            values=values,
        )
        await s.commit()
