"""/api/home(04 5.1, S07). 처리는 home_service가 한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.integrations import Clients, get_clients
from seelo.models.user import User
from seelo.schemas.home import HomeResponse
from seelo.services import home_service

router = APIRouter(prefix="/home", tags=["home"])


@router.get("", response_model=HomeResponse)
async def home(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> HomeResponse:
    """카드 하나와 공통 표시. 가게 요약 주소가 Google에 없으면 카카오를 다시 부른다(외부 호출)."""
    return await home_service.home(db, clients, user)
