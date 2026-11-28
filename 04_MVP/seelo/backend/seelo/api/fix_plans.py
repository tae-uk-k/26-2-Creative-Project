"""/api/fix/plans(04 7.3, S13). 처리는 fix_plan_service가 한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.fix import ApproveRequest, ApproveResponse, PlanDetail, PlanEvidence, PlanList
from seelo.services import fix_plan_service

router = APIRouter(prefix="/fix/plans", tags=["fix"])


@router.get("", response_model=PlanList)
async def plans(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> PlanList:
    """지도별 최신 버전만."""
    return await fix_plan_service.list_plans(db, user)


@router.get("/{plan_id}", response_model=PlanDetail)
async def detail(
    plan_id: int, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> PlanDetail:
    """사장님(그 가게)·관리자. 그 지도가 한 번이라도 연결됐을 때만, 아니면 404."""
    return await fix_plan_service.detail(db, user, plan_id)


@router.get("/{plan_id}/evidence", response_model=PlanEvidence)
async def evidence(
    plan_id: int, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> PlanEvidence:
    return await fix_plan_service.evidence(db, user, plan_id)


@router.post("/{plan_id}/approve", status_code=202, response_model=ApproveResponse)
async def approve(
    plan_id: int,
    body: ApproveRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ApproveResponse:
    """E15 [정비 시작]. 오류가 하나라도 있으면 아무것도 저장하지 않는다(09 7장)."""
    return await fix_plan_service.approve(db, user, plan_id, body)
