"""현재 가게 보고서(04 7.4, S16)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.report import ReportResponse
from seelo.services import report_service

router = APIRouter(prefix="/fix", tags=["fix"])


@router.get("/report", response_model=ReportResponse)
async def current(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> ReportResponse:
    return await report_service.current(db, user)
