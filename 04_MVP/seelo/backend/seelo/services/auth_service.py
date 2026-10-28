"""이메일 가입·인증·로그인·비밀번호 재설정(05 4·6·7장, W-01-2·4·5).

- 서비스 함수가 마지막에 커밋한다(01 7.2). 요청 제한 횟수는 결과와 상관없이 남도록 바로 커밋한다.
- 비밀번호 해시·검증(Argon2id)은 CPU를 쓰므로 스레드에서 돌린다.
- 링크 토큰 원문은 메일 비밀 값(Fernet 암호문)으로만 넘기고 DB에는 해시만 둔다.
"""

import asyncio
import math
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import case, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from seelo.config import get_settings
from seelo.errors import AppError
from seelo.models.ops import EmailLog
from seelo.models.store import Store
from seelo.models.user import AuthIdentity, AuthToken, User
from seelo.models.user import Session as SessionRow
from seelo.schemas.auth import (
    LoginRequest,
    MailStatusResponse,
    MailTicketResponse,
    Me,
    ResetRequest,
    SignupRequest,
    SignupResponse,
    UserResponse,
)
from seelo.security import ratelimit
from seelo.security.passwords import hash_password, needs_rehash, verify_password
from seelo.security.sessions import clear_auth_cookies, create_session, delete_sessions
from seelo.security.tokens import hash_token, new_token, normalize_email
from seelo.services import email_service
from seelo.timeutil import now_utc

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
RESEND_COOLDOWN = timedelta(seconds=60)
LOCK_AFTER = 5
LOCK_FOR = timedelta(minutes=10)
MAIL_TICKET_MAX_AGE = 86400  # 1일
DUMMY_TICKET_ID = 0  # 가입 여부를 드러내지 않으려고 주는 의미 없는 티켓


# --- 공용 도우미 -------------------------------------------------------------


def _ticket_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key.get_secret_value(), salt="mail-ticket")


def make_mail_ticket(email_log_id: int | None) -> str:
    return _ticket_serializer().dumps(email_log_id or DUMMY_TICKET_ID)


def read_mail_ticket(ticket: str) -> int:
    try:
        value = _ticket_serializer().loads(ticket, max_age=MAIL_TICKET_MAX_AGE)
    except BadSignature as e:  # 만료(SignatureExpired)도 여기에 포함
        raise AppError("NOT_FOUND") from e
    if not isinstance(value, int):
        raise AppError("NOT_FOUND")
    return value


async def provider_of(db: AsyncSession, user_id: int) -> str:
    """가입 방식. 사용자마다 연결은 하나다(email·google·kakao 중)."""
    provider = await db.scalar(
        select(AuthIdentity.provider)
        .where(AuthIdentity.user_id == user_id)
        .order_by(AuthIdentity.id)
        .limit(1)
    )
    return provider or "email"


async def build_me(db: AsyncSession, user: User) -> Me:
    has_store = await db.scalar(
        select(exists().where(Store.owner_id == user.id, Store.archived_at.is_(None)))
    )
    return Me(
        id=user.id,
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        provider=await provider_of(db, user.id),  # type: ignore[arg-type]
        has_store=bool(has_store),
    )


async def find_user(db: AsyncSession, email: str, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    if for_update:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def drop_unverified_or_raise_taken(db: AsyncSession, email: str) -> None:
    """같은 이메일 사용자가 있으면: 인증됨 → 409 EMAIL_TAKEN, 미인증 → 삭제(05 4.1·5.3·5.4)."""
    existing = await find_user(db, email, for_update=True)
    if existing is None:
        return
    if existing.email_verified_at is not None:
        raise AppError("EMAIL_TAKEN", {"provider": await provider_of(db, existing.id)})
    await db.delete(existing)
    await db.flush()


async def issue_verify_mail(db: AsyncSession, user: User) -> int | None:
    """verify 토큰을 만들고 인증 메일을 등록한다(같은 트랜잭션). email_logs.id를 돌려준다."""
    token = new_token()
    db.add(
        AuthToken(
            user_id=user.id, type="verify", token_hash=hash_token(token), expires_at=now_utc() + VERIFY_TTL
        )
    )
    return await email_service.queue(db, "verify_email", user=user, secret={"token": token})


async def _hit(db: AsyncSession, kind: str, ip: str) -> None:
    await ratelimit.hit(db, kind, ip)
    await db.commit()


async def _use_token(db: AsyncSession, raw: str, type_: str) -> AuthToken:
    """토큰을 한 번만 쓰게 조건부로 used_at을 채운다. 없음·사용됨·만료는 모두 410."""
    row = await db.scalar(
        select(AuthToken).where(AuthToken.token_hash == hash_token(raw), AuthToken.type == type_)
    )
    now = now_utc()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AppError("TOKEN_EXPIRED")
    used = await db.execute(
        update(AuthToken).where(AuthToken.id == row.id, AuthToken.used_at.is_(None)).values(used_at=now)
    )
    if used.rowcount != 1:  # type: ignore[attr-defined]
        raise AppError("TOKEN_EXPIRED")
    return row


# --- W-01-2 이메일 가입·인증 ---------------------------------------------------


async def signup(db: AsyncSession, body: SignupRequest, ip: str) -> SignupResponse:
    await _hit(db, "signup", ip)
    email = normalize_email(body.email)
    await drop_unverified_or_raise_taken(db, email)
    pw_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(email=email, password_hash=pw_hash, terms_agreed_at=now_utc())
    db.add(user)
    await db.flush()
    db.add(AuthIdentity(user_id=user.id, provider="email", provider_user_id=None))
    log_id = await issue_verify_mail(db, user)
    await db.commit()
    return SignupResponse(email=email, mail_ticket=make_mail_ticket(log_id))


async def mail_status(db: AsyncSession, ticket: str) -> MailStatusResponse:
    log_id = read_mail_ticket(ticket)
    if log_id == DUMMY_TICKET_ID:
        return MailStatusResponse(status="sent")
    status = await db.scalar(select(EmailLog.status).where(EmailLog.id == log_id))
    if status is None:
        raise AppError("NOT_FOUND")
    return MailStatusResponse(status=status)  # type: ignore[arg-type]


async def verify_email(db: AsyncSession, token: str, response: Response) -> UserResponse:
    row = await _use_token(db, token, "verify")
    user = await db.get(User, row.user_id, with_for_update=True)
    if user is None:
        raise AppError("TOKEN_EXPIRED")
    if user.email_verified_at is None:
        user.email_verified_at = now_utc()
    await create_session(db, user, response)
    await db.commit()
    return UserResponse(user=await build_me(db, user))


async def resend_verify(db: AsyncSession, email: str, ip: str) -> MailTicketResponse:
    await _hit(db, "resend", ip)
    user = await find_user(db, email, for_update=True)
    if user is None or user.email_verified_at is not None:
        return MailTicketResponse(mail_ticket=make_mail_ticket(None))
    last = await db.scalar(
        select(AuthToken.created_at)
        .where(AuthToken.user_id == user.id, AuthToken.type == "verify")
        .order_by(AuthToken.created_at.desc())
        .limit(1)
    )
    now = now_utc()
    if last is not None and now - last < RESEND_COOLDOWN:
        wait = math.ceil((RESEND_COOLDOWN - (now - last)).total_seconds())
        limit = math.ceil(RESEND_COOLDOWN.total_seconds())  # DB 시계가 조금 앞서도 대기 시간을 넘기지 않게
        raise AppError("RESEND_COOLDOWN", {"retryAfterSeconds": min(limit, max(1, wait))})
    await db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.type == "verify", AuthToken.used_at.is_(None))
        .values(used_at=now)
    )
    log_id = await issue_verify_mail(db, user)
    await db.commit()
    return MailTicketResponse(mail_ticket=make_mail_ticket(log_id))


# --- W-01-4 로그인·잠금 -------------------------------------------------------


async def login(db: AsyncSession, body: LoginRequest, response: Response) -> UserResponse:
    user = await find_user(db, body.email)
    if user is None:
        await asyncio.to_thread(verify_password, None, body.password)  # 응답 시간 맞추기
        raise AppError("INVALID_CREDENTIALS")
    now = now_utc()
    if user.locked_until is not None and user.locked_until > now:
        raise AppError("ACCOUNT_LOCKED", {"lockedUntil": _iso(user.locked_until)})
    if user.password_hash is None:
        raise AppError("SOCIAL_ACCOUNT", {"provider": await provider_of(db, user.id)})

    ok = await asyncio.to_thread(verify_password, user.password_hash, body.password)
    if not ok:
        raise await _count_failure(db, user.id)

    if user.email_verified_at is None:
        raise AppError("EMAIL_NOT_VERIFIED", {"email": user.email})
    user.failed_login_count = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, body.password)
    await create_session(db, user, response)
    await db.commit()
    return UserResponse(user=await build_me(db, user))


async def _count_failure(db: AsyncSession, user_id: int) -> AppError:
    """틀린 횟수를 원자적으로 올리고 낼 오류를 돌려준다. 5번째면 10분 잠그고 횟수를 0으로(05 6장)."""
    now = now_utc()
    reached = User.failed_login_count + 1 >= LOCK_AFTER
    result = await db.execute(
        update(User)
        .where(User.id == user_id, (User.locked_until.is_(None)) | (User.locked_until <= now))
        .values(
            failed_login_count=case((reached, 0), else_=User.failed_login_count + 1),
            locked_until=case((reached, now + LOCK_FOR), else_=None),
        )
        .returning(User.locked_until)
    )
    row = result.first()
    await db.commit()
    if row is None:  # 그 사이 다른 요청이 잠갔다
        locked = await db.scalar(select(User.locked_until).where(User.id == user_id))
        return AppError("ACCOUNT_LOCKED", {"lockedUntil": _iso(locked)} if locked else {})
    if row.locked_until is not None:
        return AppError("ACCOUNT_LOCKED", {"lockedUntil": _iso(row.locked_until)})
    return AppError("INVALID_CREDENTIALS")


def _iso(at: datetime) -> str:
    """04 1장 시각 형식: 2026-11-02T03:15:00Z"""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def logout(db: AsyncSession, session_row: SessionRow | None, response: Response) -> None:
    if session_row is not None:
        await db.delete(session_row)
        await db.commit()
    clear_auth_cookies(response)


async def me(db: AsyncSession, user: User) -> Me:
    return await build_me(db, user)


# --- W-01-5 비밀번호 재설정 ----------------------------------------------------


async def forgot_password(db: AsyncSession, email: str, ip: str) -> None:
    """가입 여부와 상관없이 같은 응답. 메일은 인증된 사용자에게만 간다."""
    await _hit(db, "pwreset", ip)
    user = await find_user(db, email)
    if user is None or user.email_verified_at is None:
        return
    if user.password_hash is None:
        provider = await provider_of(db, user.id)
        await email_service.queue(db, "password_reset", user=user, params={"social_provider": provider})
    else:
        now = now_utc()
        # 새 링크를 보내면 이전에 보낸 재설정 링크는 막는다(마지막 메일의 링크만 유효)
        await db.execute(
            update(AuthToken)
            .where(AuthToken.user_id == user.id, AuthToken.type == "reset", AuthToken.used_at.is_(None))
            .values(used_at=now)
        )
        token = new_token()
        db.add(
            AuthToken(user_id=user.id, type="reset", token_hash=hash_token(token), expires_at=now + RESET_TTL)
        )
        await email_service.queue(
            db, "password_reset", user=user, params={"social_provider": None}, secret={"token": token}
        )
    await db.commit()


async def reset_password(db: AsyncSession, body: ResetRequest) -> None:
    row = await _use_token(db, body.token, "reset")
    user = await db.get(User, row.user_id, with_for_update=True)
    if user is None:
        raise AppError("TOKEN_EXPIRED")
    user.password_hash = await asyncio.to_thread(hash_password, body.password)
    user.failed_login_count = 0
    user.locked_until = None
    await delete_sessions(db, user.id)
    await db.commit()
