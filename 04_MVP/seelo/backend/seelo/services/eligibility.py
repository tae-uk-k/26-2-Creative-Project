"""자격 판정 공용 함수(03 7장). 정비 관련 판정은 해당 단계에서 더한다."""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.states import FixRequestStatus
from seelo.models.fix import FixRequest
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger
from seelo.security.tokens import email_hmac

DONE_REQUEST = (FixRequestStatus.REJECTED, FixRequestStatus.REPORT_READY)


async def has_used_free(db: AsyncSession, email: str) -> bool:
    """이 이메일로 무료 진단을 쓴 적이 있다(탈퇴 후 재가입 포함)."""
    return bool(await db.scalar(select(exists().where(FreeUsageLedger.email_hash == email_hmac(email)))))


async def current_store(db: AsyncSession, user_id: int, *, for_update: bool = False) -> Store | None:
    """보관 중이 아닌 가게(사용자당 최대 1개, uq_store_owner_active)."""
    stmt = select(Store).where(Store.owner_id == user_id, Store.archived_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def active_request(db: AsyncSession, store_id: int) -> FixRequest | None:
    """그 가게의 신청 중 rejected·report_ready가 아닌 것(최대 1개)."""
    return await db.scalar(
        select(FixRequest)
        .where(FixRequest.store_id == store_id, FixRequest.status.not_in([str(s) for s in DONE_REQUEST]))
        .limit(1)
    )


async def can_change_store(db: AsyncSession, user_id: int) -> bool:
    """보관 중이 아닌 가게가 없거나, 그 가게에 진행 중인 신청이 없다."""
    store = await current_store(db, user_id)
    return store is None or await active_request(db, store.id) is None
