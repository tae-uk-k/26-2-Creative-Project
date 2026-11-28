"""/api/fix/connect(04 7.2, S15). 처리는 connection_service가 한다."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.fix import ConnectionView, ConnectState
from seelo.services import connection_service

router = APIRouter(prefix="/fix/connect", tags=["fix"])


@router.get("", response_model=ConnectState)
async def state(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> ConnectState:
    """승인된 신청(approved~report_ready)이 없으면 404."""
    return await connection_service.state(db, user)


@router.post("/{provider}/invited", response_model=ConnectionView)
async def invited(
    provider: Literal["google", "kakao"],
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectionView:
    """E11 [초대했어요]. 이미 invited면 그대로 200, connected 등은 409."""
    return await connection_service.mark_invited(db, user, provider)
