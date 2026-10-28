"""/api/account(04 4장, S14)."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.account import AccountResponse, ChangePasswordRequest, DeleteAccountRequest
from seelo.services import account_service

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountResponse)
async def get_account(
    user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> AccountResponse:
    return await account_service.get(db, user)


@router.post("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await account_service.change_password(db, user, request.state.session_row, body)


@router.delete("", status_code=204)
async def delete_account(
    body: DeleteAccountRequest,
    response: Response,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await account_service.delete_account(db, user, body, response)
