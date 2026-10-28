"""/api/auth(04 4장). 처리는 auth_service·oauth_service가 한다."""

import hmac

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_user
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.auth import (
    EmailRequest,
    LoginRequest,
    MailStatusResponse,
    MailTicketResponse,
    Me,
    PendingCompleteRequest,
    PendingCompleteResponse,
    PendingSignupResponse,
    ResetRequest,
    SignupRequest,
    SignupResponse,
    TokenRequest,
    UserResponse,
)
from seelo.security.csrf import CSRF_COOKIE, new_csrf_value, set_csrf_cookie, verify_signature
from seelo.security.tokens import hash_token
from seelo.services import auth_service, oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers가 신뢰 프록시(nginx)의 X-Forwarded-For를 반영한다(05 10장)
    return request.client.host if request.client else "unknown"


@router.get("/csrf", status_code=204)
async def csrf(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    """로그인 전에는 새 값을 준다. 로그인 중이면 세션에 묶인 값을 유지하고, 없거나 다르면 새로 묶는다."""
    row = request.state.session_row
    cookie = request.cookies.get(CSRF_COOKIE)
    if (
        row is not None
        and cookie
        and verify_signature(cookie)
        and hmac.compare_digest(hash_token(cookie), row.csrf_token_hash)
    ):
        return
    value = new_csrf_value()
    if row is not None:
        row.csrf_token_hash = hash_token(value)
        await db.commit()
    set_csrf_cookie(response, value)


@router.post("/signup", status_code=201, response_model=SignupResponse)
async def signup(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    return await auth_service.signup(db, body, client_ip(request))


@router.get("/signup/mail-status", response_model=MailStatusResponse)
async def mail_status(ticket: str, db: AsyncSession = Depends(get_db)) -> MailStatusResponse:
    return await auth_service.mail_status(db, ticket)


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    body: TokenRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    return await auth_service.verify_email(db, body.token, response)


@router.post("/verify-email/resend", status_code=202, response_model=MailTicketResponse)
async def resend_verify(
    body: EmailRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MailTicketResponse:
    return await auth_service.resend_verify(db, body.email, client_ip(request))


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)) -> UserResponse:
    return await auth_service.login(db, body, response)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    _: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await auth_service.logout(db, request.state.session_row, response)


@router.get("/me", response_model=Me)
async def me(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> Me:
    return await auth_service.me(db, user)


@router.post("/password/forgot", status_code=202)
async def forgot_password(body: EmailRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await auth_service.forgot_password(db, body.email, client_ip(request))
    return {}


@router.post("/password/reset", status_code=204)
async def reset_password(body: ResetRequest, db: AsyncSession = Depends(get_db)) -> None:
    await auth_service.reset_password(db, body)


@router.get("/pending-signup", response_model=PendingSignupResponse)
async def pending_signup(request: Request, db: AsyncSession = Depends(get_db)) -> PendingSignupResponse:
    return await oauth_service.pending(db, request.cookies.get(oauth_service.PENDING_COOKIE))


@router.post(
    "/pending-signup/complete", response_model=PendingCompleteResponse, response_model_exclude_none=True
)
async def pending_complete(
    body: PendingCompleteRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> PendingCompleteResponse:
    """제공자 인증 이메일이면 200 + 세션, 사장님이 입력한 이메일이면 202 + 인증 메일."""
    return await oauth_service.complete(db, request.cookies.get(oauth_service.PENDING_COOKIE), body, response)
