"""계정 테이블(02 4장 1절)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, PrimaryKeyConstraint, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, pk, ts, txt


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = pk()
    email: Mapped[str] = txt()
    email_verified_at: Mapped[datetime | None] = ts()
    password_hash: Mapped[str | None] = txt(nullable=True)
    role: Mapped[str] = txt(default="owner")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = ts()
    terms_agreed_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        UniqueConstraint("email", name="users_email_key"),
        Index("ix_users_unverified", "created_at", postgresql_where=text("email_verified_at IS NULL")),
    )


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    provider: Mapped[str] = txt()
    provider_user_id: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_identity_user_provider"),
        CheckConstraint(
            "(provider = 'email') = (provider_user_id IS NULL)", name="ck_identity_provider_user"
        ),
        Index(
            "uq_identity_provider_user",
            "provider",
            "provider_user_id",
            unique=True,
            postgresql_where=text("provider_user_id IS NOT NULL"),
        ),
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    type: Mapped[str] = txt()
    token_hash: Mapped[str] = txt()
    expires_at: Mapped[datetime] = ts(nullable=False)
    used_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        UniqueConstraint("token_hash", name="auth_tokens_token_hash_key"),
        Index("ix_auth_tokens_user_type", "user_id", "type", text("created_at DESC")),
    )


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    token_hash: Mapped[str] = txt()
    csrf_token_hash: Mapped[str] = txt()
    expires_at: Mapped[datetime] = ts(nullable=False)
    created_at: Mapped[datetime] = created_col()
    last_seen_at: Mapped[datetime] = created_col()

    __table_args__ = (
        UniqueConstraint("token_hash", name="sessions_token_hash_key"),
        Index("ix_sessions_user", "user_id"),
        Index("ix_sessions_expires", "expires_at"),
    )


class PendingSignup(Base):
    __tablename__ = "pending_signups"
    id: Mapped[int] = pk()
    provider: Mapped[str] = txt()
    provider_user_id: Mapped[str] = txt()
    email: Mapped[str | None] = txt(nullable=True)
    token_hash: Mapped[str] = txt()
    expires_at: Mapped[datetime] = ts(nullable=False)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        UniqueConstraint("token_hash", name="pending_signups_token_hash_key"),
        UniqueConstraint("provider", "provider_user_id", name="uq_pending_provider_user"),
    )


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = txt()
    window_start: Mapped[datetime] = ts(nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (PrimaryKeyConstraint("key", "window_start", name="rate_limits_pkey"),)


class FreeUsageLedger(Base):
    __tablename__ = "free_usage_ledger"
    email_hash: Mapped[str] = txt()
    used_at: Mapped[datetime] = created_col()

    __table_args__ = (PrimaryKeyConstraint("email_hash", name="free_usage_ledger_pkey"),)
