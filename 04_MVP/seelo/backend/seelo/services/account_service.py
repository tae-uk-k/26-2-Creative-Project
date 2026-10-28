"""계정 설정·탈퇴(05 8·9장, W-01-6)."""

import asyncio

import structlog
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from seelo.domain.labels import ACCOUNT_DELETE_CONFIRM_TEXT
from seelo.errors import AppError
from seelo.models.measurement import MeasurementRun
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger, User
from seelo.models.user import Session as SessionRow
from seelo.schemas.account import AccountResponse, ChangePasswordRequest, DeleteAccountRequest
from seelo.security.passwords import hash_password, verify_password
from seelo.security.sessions import clear_auth_cookies, delete_sessions
from seelo.security.tokens import email_hmac
from seelo.services import audit, jobs
from seelo.services.auth_service import provider_of
from seelo.services.eligibility import has_used_free

log = structlog.get_logger()


async def get(db: AsyncSession, user: User) -> AccountResponse:
    return AccountResponse(
        email=user.email,
        provider=await provider_of(db, user.id),  # type: ignore[arg-type]
        created_at=user.created_at,
        can_change_password=user.password_hash is not None,
    )


async def change_password(
    db: AsyncSession, user: User, session_row: SessionRow | None, body: ChangePasswordRequest
) -> None:
    if user.password_hash is None:
        raise AppError("PASSWORD_LOGIN_UNAVAILABLE", {"provider": await provider_of(db, user.id)})
    if body.new_password != body.new_password_confirm:
        raise AppError("VALIDATION_ERROR", {"fields": {"newPasswordConfirm": "password_mismatch"}})
    # 틀려도 로그인 잠금 횟수는 올리지 않는다(05 8장)
    if not await asyncio.to_thread(verify_password, user.password_hash, body.current_password):
        raise AppError("WRONG_PASSWORD")
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    await delete_sessions(db, user.id, except_id=session_row.id if session_row is not None else None)
    await db.commit()


async def delete_account(
    db: AsyncSession, user: User, body: DeleteAccountRequest, response: Response
) -> None:
    if body.confirm_text != ACCOUNT_DELETE_CONFIRM_TEXT:
        raise AppError("CONFIRM_TEXT_MISMATCH")
    user_id, email = user.id, user.email
    store_ids = list((await db.scalars(select(Store.id).where(Store.owner_id == user_id))).all())

    # 1) 가게에 딸린 작업 취소·중단 요청(06 7장). 실패해도 계속한다
    try:
        cancelled = await jobs.cancel_jobs(db, store_ids=store_ids)
    except Exception as e:
        cancelled = 0
        log.warning("account_delete_cancel_failed", user_id=user_id, error_type=type(e).__name__)

    # 2) 같은 트랜잭션: 무료 진단 기록 → 감사 기록 → 사용자 삭제(CASCADE)
    used_free = await has_used_free(db, email) or bool(
        await db.scalar(
            select(
                exists().where(
                    MeasurementRun.store_id == Store.id,
                    Store.owner_id == user_id,
                    MeasurementRun.is_free.is_(True),
                    MeasurementRun.status == "completed",
                )
            )
        )
    )
    if used_free:
        await db.execute(
            insert(FreeUsageLedger).values(email_hash=email_hmac(email)).on_conflict_do_nothing()
        )
    audit.record(db, actor_id=None, action="account.delete", target_type="user", target_id=user_id, detail={})
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    clear_auth_cookies(response)
    log.info("account_deleted", user_id=user_id, stores=len(store_ids), cancelled_jobs=cancelled)
