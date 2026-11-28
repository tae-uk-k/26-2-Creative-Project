"""/api/oauth(04 4장, 05 5장). GET만 있어 CSRF 검사 대상이 아니다(state로 막는다)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from seelo.db import get_db
from seelo.integrations import Clients, get_clients
from seelo.services import oauth_service

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/{provider}/start")
async def start(
    provider: str, request: Request, intent: str = "login", clients: Clients = Depends(get_clients)
) -> RedirectResponse:
    return oauth_service.start(request, clients, provider, intent)


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    clients: Clients = Depends(get_clients),
) -> RedirectResponse:
    return await oauth_service.callback(request, db, clients, provider)
