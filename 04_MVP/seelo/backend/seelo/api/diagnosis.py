"""/api/diagnosis(04 6장, S11). 처리는 diagnosis_service가 한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.diagnosis import DiagnosisResponse
from seelo.services import diagnosis_service

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.get("/{run_id}", response_model=DiagnosisResponse)
async def get(
    run_id: int, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> DiagnosisResponse:
    """진단이고 completed인 측정만. 고쳐야 할 점은 개수(findingsCount)만 내려준다."""
    return await diagnosis_service.get(db, user, run_id)
