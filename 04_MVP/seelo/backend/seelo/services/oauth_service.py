"""구글·카카오 로그인과 소셜 첫 가입(05 5장, W-01-3).

- state: 새 난수를 seelo_oauth 세션 쿠키(SessionMiddleware, 10분)에 두고 콜백에서 비교한다.
- 첫 가입은 약관 동의(S02)·카카오 이메일 입력(S04)이 끝날 때까지 계정을 만들지 않고
  pending_signups 행 + seelo_pending 쿠키(30분)로 기다린다.
- 리디렉션은 화면 경로(04 3장)로만 한다. 같은 출처라 상대 경로를 쓴다.
"""

import hmac
from datetime import timedelta
from urllib.parse import urlencode

import structlog
from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse, Response

from seelo.config import get_settings
from seelo.errors import AppError
from seelo.integrations import Clients, OAuthProfile
from seelo.models.user import AuthIdentity, PendingSignup, User
from seelo.schemas.auth import PendingCompleteRequest, PendingCompleteResponse, PendingSignupResponse
from seelo.security.sessions import create_session
from seelo.security.tokens import hash_token, new_token, normalize_email
from seelo.services import auth_service
from seelo.timeutil import now_utc

log = structlog.get_logger()

PROVIDERS = ("google", "kakao")
PENDING_COOKIE = "seelo_pending"
PENDING_TTL = timedelta(minutes=30)
STATE_KEY = "oauth"


def redirect_uri(provider: str) -> str:
    return f"{get_settings().app_base_url}/api/oauth/{provider}/callback"


def _go(path: str, **query: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?{urlencode(query)}" if query else path, status_code=302)


def start(request: Request, clients: Clients, provider: str, intent: str) -> RedirectResponse:
    if provider not in PROVIDERS:
        raise AppError("NOT_FOUND")
    intent = intent if intent in ("signup", "login") else "login"
    state = new_token()
    request.session[STATE_KEY] = {"provider": provider, "state": state, "intent": intent}
    try:
        url = clients.oauth.authorize_url(provider, redirect_uri=redirect_uri(provider), state=state)
    except Exception as e:  # 설정 누락 등
        log.error("oauth_start_failed", provider=provider, error_type=type(e).__name__)
        return _go(f"/{intent}", error="oauth_failed")
    return RedirectResponse(url, status_code=302)


async def callback(request: Request, db: AsyncSession, clients: Clients, provider: str) -> RedirectResponse:
    if provider not in PROVIDERS:
        raise AppError("NOT_FOUND")
    saved = request.session.pop(STATE_KEY, None) or {}
    intent = saved.get("intent", "login")
    back = f"/{intent}"
    q = request.query_params

    # 1) 사용자 취소·제공자 오류
    if q.get("error"):
        log.info("oauth_canceled", provider=provider, error=q.get("error"))
        return _go(back, error="oauth_canceled")
    # 2) state 확인(없음·제공자 다름·값 다름은 모두 실패)
    state = q.get("state") or ""
    if (
        saved.get("provider") != provider
        or not state
        or not hmac.compare_digest(state, str(saved.get("state", "")))
        or not q.get("code")
    ):
        log.warning("oauth_state_mismatch", provider=provider)
        return _go(back, error="oauth_failed")
    try:
        profile = await clients.oauth.fetch_profile(
            provider, code=q["code"], redirect_uri=redirect_uri(provider)
        )
    except Exception as e:
        log.error("oauth_token_failed", provider=provider, error_type=type(e).__name__)
        return _go(back, error="oauth_failed")

    # 3) 구글 이메일이 인증되지 않았으면 가입하지 않는다(W-01-3)
    if provider == "google" and not (profile.email and profile.email_verified):
        return _go("/signup", error="oauth_failed")

    # 4) 이미 연결된 계정
    identity = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider, AuthIdentity.provider_user_id == profile.provider_user_id
        )
    )
    if identity is not None:
        user = await db.get(User, identity.user_id)
        if user is None or user.email_verified_at is None:
            return _go("/signup/sent")  # 카카오 S04에서 메일 인증을 아직 안 마침
        response = _go("/home")
        await create_session(db, user, response)
        await db.commit()
        return response

    # 5) 첫 가입
    email = _verified_email(profile)
    if email is not None:
        try:
            await auth_service.drop_unverified_or_raise_taken(db, email)
        except AppError as e:
            await db.rollback()
            return _go("/signup", error="email_taken", provider=e.details.get("provider", "email"))
    token = new_token()
    await db.execute(
        insert(PendingSignup)
        .values(
            provider=provider,
            provider_user_id=profile.provider_user_id,
            email=email,
            token_hash=hash_token(token),
            expires_at=now_utc() + PENDING_TTL,
        )
        .on_conflict_do_update(
            constraint="uq_pending_provider_user",
            set_={
                "email": email,
                "token_hash": hash_token(token),
                "expires_at": now_utc() + PENDING_TTL,
            },
        )
    )
    await db.commit()
    response = _go("/signup/terms" if email else "/signup/kakao-email")
    _set_pending_cookie(response, token)
    return response


def _verified_email(profile: OAuthProfile) -> str | None:
    if profile.email and profile.email_verified:
        return normalize_email(profile.email)
    return None


def _set_pending_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        PENDING_COOKIE,
        token,
        max_age=int(PENDING_TTL.total_seconds()),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )


async def _pending_row(db: AsyncSession, cookie: str | None) -> PendingSignup:
    if not cookie:
        raise AppError("NOT_FOUND")
    row = await db.scalar(select(PendingSignup).where(PendingSignup.token_hash == hash_token(cookie)))
    if row is None or row.expires_at <= now_utc():
        raise AppError("NOT_FOUND")
    return row


async def pending(db: AsyncSession, cookie: str | None) -> PendingSignupResponse:
    row = await _pending_row(db, cookie)
    return PendingSignupResponse(provider=row.provider, email=row.email, needs_email=row.email is None)  # type: ignore[arg-type]


async def complete(
    db: AsyncSession, cookie: str | None, body: PendingCompleteRequest, response: Response
) -> PendingCompleteResponse:
    row = await _pending_row(db, cookie)
    provider, provider_user_id = row.provider, row.provider_user_id
    if row.email is not None:  # 제공자가 인증한 이메일. 요청의 email은 무시한다
        email, verified = row.email, True
    else:
        if body.email is None:
            raise AppError("VALIDATION_ERROR", {"fields": {"email": "required"}})
        email, verified = normalize_email(body.email), False

    # 두 번 눌러도 한 번만 처리되게 대기 행을 먼저 지운다
    gone = await db.execute(
        delete(PendingSignup).where(PendingSignup.id == row.id).returning(PendingSignup.id)
    )
    if gone.first() is None:
        raise AppError("NOT_FOUND")
    await auth_service.drop_unverified_or_raise_taken(db, email)

    now = now_utc()
    user = User(email=email, email_verified_at=now if verified else None, terms_agreed_at=now)
    db.add(user)
    await db.flush()
    db.add(AuthIdentity(user_id=user.id, provider=provider, provider_user_id=provider_user_id))
    response.delete_cookie(PENDING_COOKIE, path="/")

    if verified:
        await create_session(db, user, response)
        await db.commit()
        return PendingCompleteResponse(next="/home", user=await auth_service.build_me(db, user))

    log_id = await auth_service.issue_verify_mail(db, user)
    await db.commit()
    response.status_code = 202
    return PendingCompleteResponse(next="/signup/sent", mail_ticket=auth_service.make_mail_ticket(log_id))
