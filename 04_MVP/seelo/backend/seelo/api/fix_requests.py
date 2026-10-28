"""/api/fix/requests(04 7.1, S12). 처리는 fix_request_service가 한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.fix import CreatedRequest, FixRequestState
from seelo.schemas.run import RunIdResponse
from seelo.services import fix_request_service

router = APIRouter(prefix="/fix/requests", tags=["fix"])


@router.get("/current", response_model=FixRequestState)
async def current(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> FixRequestState:
    return await fix_request_service.state(db, user)


@router.post("", status_code=201, response_model=CreatedRequest)
async def create(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> CreatedRequest:
    """E8. 관리자에게 메일. 동시 신청은 하나만 성공(나머지 409 ALREADY_REQUESTED)."""
    return await fix_request_service.create(db, user)


@router.post("/current/remeasure/retry", status_code=202, response_model=RunIdResponse)
async def retry_remeasure(
    user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> RunIdResponse:
    """E26. 재측정 실패 뒤 다시 시도(하루 3번, 진단 다시 시도와 합산)."""
    return await fix_request_service.retry_remeasure(db, user)
