"""가게 테이블(02 4장 2절)."""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class IdentifySession(Base):
    __tablename__ = "identify_sessions"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    mode: Mapped[str] = txt()
    input_name: Mapped[str] = txt()
    input_url: Mapped[str] = txt()
    input_provider: Mapped[str] = txt()
    candidates: Mapped[Any] = jsonb(nullable=False)
    token_hash: Mapped[str] = txt()
    expires_at: Mapped[datetime] = ts(nullable=False)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("token_hash", name="identify_sessions_token_hash_key"),)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = pk()
    owner_id: Mapped[int] = fk("users.id", "CASCADE")
    name: Mapped[str] = txt()
    input_url: Mapped[str] = txt()
    input_provider: Mapped[str] = txt()
    category: Mapped[str] = txt()
    status: Mapped[str] = txt()
    archived_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = created_col()  # 갱신은 DB 트리거

    __table_args__ = (
        CheckConstraint("(status = 'archived') = (archived_at IS NOT NULL)", name="ck_store_archived"),
        Index(
            "uq_store_owner_active",
            "owner_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class StoreSource(Base):
    __tablename__ = "store_sources"
    id: Mapped[int] = pk()
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    provider: Mapped[str] = txt()
    external_id: Mapped[str | None] = txt(nullable=True)
    url: Mapped[str | None] = txt(nullable=True)
    match_status: Mapped[str] = txt()
    matched_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("store_id", "provider", name="uq_store_source"),)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = pk()
    source_id: Mapped[int] = fk("store_sources.id", "CASCADE")
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    run_id: Mapped[int | None] = fk("measurement_runs.id", "CASCADE", nullable=True)
    provider: Mapped[str] = txt()
    status: Mapped[str] = txt()
    error_code: Mapped[str | None] = txt(nullable=True)
    payload: Mapped[Any] = jsonb()
    collected_at: Mapped[datetime] = created_col()
    expires_at: Mapped[datetime] = ts(nullable=False)

    __table_args__ = (
        Index("ix_snapshots_store_provider", "store_id", "provider", text("collected_at DESC")),
        Index("ix_snapshots_expires", "expires_at"),
    )


class WebEvidence(Base):
    __tablename__ = "web_evidence"
    id: Mapped[int] = pk()
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    run_id: Mapped[int | None] = fk("measurement_runs.id", "CASCADE", nullable=True)
    provider: Mapped[str] = txt()
    site_url: Mapped[str] = txt()
    site_name: Mapped[str | None] = txt(nullable=True)
    fields: Mapped[Any] = jsonb(nullable=False)
    collected_at: Mapped[datetime] = created_col()
    expires_at: Mapped[datetime] = ts(nullable=False)

    __table_args__ = (Index("ix_web_evidence_store", "store_id", text("collected_at DESC")),)
