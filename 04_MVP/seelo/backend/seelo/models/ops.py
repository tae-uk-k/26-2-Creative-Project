"""운영 테이블(02 4장 5절)."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Index, LargeBinary, SmallInteger, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class EmailLog(Base):
    __tablename__ = "email_logs"
    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = fk("users.id", "CASCADE", nullable=True)
    type: Mapped[str] = txt()
    to_email: Mapped[str] = txt()
    template_params: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    secret_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dedupe_key: Mapped[str | None] = txt(nullable=True)
    status: Mapped[str] = txt()
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    sent_at: Mapped[datetime | None] = ts()
    error: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("dedupe_key", name="email_logs_dedupe_key_key"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = pk()
    actor_id: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    action: Mapped[str] = txt()
    target_type: Mapped[str] = txt()
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (Index("ix_audit_target", "target_type", "target_id"),)


class JobLink(Base):
    __tablename__ = "job_links"
    id: Mapped[int] = pk()
    procrastinate_job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_name: Mapped[str] = txt()
    store_id: Mapped[int | None] = fk("stores.id", "CASCADE", nullable=True)
    run_id: Mapped[int | None] = fk("measurement_runs.id", "CASCADE", nullable=True)
    fix_request_id: Mapped[int | None] = fk("fix_requests.id", "CASCADE", nullable=True)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        Index("ix_job_links_store", "store_id"),
        Index("ix_job_links_run", "run_id"),
        Index("ix_job_links_request", "fix_request_id"),
    )
