"""지난 보고서 조회(04 7.4). 보관된 가게도 소유자·관리자에게만 응답한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.report import ReportResponse
from seelo.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportResponse)
async def get(
    report_id: int, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> ReportResponse:
    return await report_service.get(db, user, report_id)
