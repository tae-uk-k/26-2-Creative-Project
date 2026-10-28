"""/api/runs(04 5.3): 진행률(DB만, 빠르게)과 모은 정보 표(외부 호출 있음)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.integrations import Clients, get_clients
from seelo.models.user import User
from seelo.schemas.run import CollectedInfo, RunProgress
from seelo.services import collect_service, measure_service

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}/progress", response_model=RunProgress)
async def progress(
    run_id: int, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> RunProgress:
    """S10이 3초마다 부른다. DB 조회 1번, 외부 호출 없음(200ms 이내)."""
    return await measure_service.progress(db, user, run_id)


@router.get("/{run_id}/collected", response_model=CollectedInfo)
async def collected(
    run_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> CollectedInfo:
    """카카오·네이버 열은 요청 때마다 다시 불러온 값(저장하지 않음). 외부 호출이 있어 진행률과 따로 둔다."""
    return await collect_service.collected(db, clients, user, run_id)
