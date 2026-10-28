"""/api/stores(04 5.2). 처리는 identify_service·store_service가 한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.integrations import Clients, get_clients
from seelo.models.user import User
from seelo.schemas.run import RunIdResponse
from seelo.schemas.store import (
    CurrentStoreResponse,
    HistoryResponse,
    IdentifyCandidates,
    IdentifyConfirmed,
    IdentifyRequest,
    IdentifyResult,
    IdentifySelectRequest,
    NotMineRequest,
)
from seelo.services import identify_service, store_service

router = APIRouter(prefix="/stores", tags=["stores"])


@router.post("/identify", response_model=IdentifyResult)
async def identify(
    body: IdentifyRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> IdentifyConfirmed | IdentifyCandidates:
    return await identify_service.identify(db, clients, user, body)


@router.post("/identify/select", response_model=IdentifyConfirmed)
async def identify_select(
    body: IdentifySelectRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> IdentifyConfirmed:
    return await identify_service.select_candidate(db, clients, user, body)


@router.get("/current", response_model=CurrentStoreResponse)
async def current(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> CurrentStoreResponse:
    return await store_service.current(db, clients, user)


@router.get("/history", response_model=HistoryResponse)
async def history(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> HistoryResponse:
    return await store_service.history(db, user)


@router.post("/current/not-mine", status_code=204)
async def not_mine(
    body: NotMineRequest, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> None:
    await store_service.not_mine(db, user, body.run_id)


@router.post("/current/retry", status_code=202, response_model=RunIdResponse)
async def retry(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> RunIdResponse:
    return await store_service.retry_measurement(db, user)
