"""정비 테이블(02 4장 4절)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class FixRequest(Base):
    __tablename__ = "fix_requests"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    base_run_id: Mapped[int | None] = fk("measurement_runs.id", "SET NULL", nullable=True)
    status: Mapped[str] = txt()
    reject_reason: Mapped[str | None] = txt(nullable=True)
    decided_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    decided_at: Mapped[datetime | None] = ts()
    fix_completed_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = created_col()  # 갱신은 DB 트리거

    __table_args__ = (
        CheckConstraint("status <> 'rejected' OR reject_reason IS NOT NULL", name="ck_fix_request_reject"),
        Index(
            "uq_fix_request_store_active",
            "store_id",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
    )


class MapConnection(Base):
    __tablename__ = "map_connections"
    id: Mapped[int] = pk()
    fix_request_id: Mapped[int] = fk("fix_requests.id", "CASCADE")
    provider: Mapped[str] = txt()
    status: Mapped[str] = txt()
    attention_reason: Mapped[str | None] = txt(nullable=True)
    external_ref: Mapped[str | None] = txt(nullable=True)
    invited_at: Mapped[datetime | None] = ts()
    invite_reminder_sent_at: Mapped[datetime | None] = ts()
    connected_at: Mapped[datetime | None] = ts()
    confirmed_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    revoked_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = created_col()  # 갱신은 DB 트리거

    __table_args__ = (UniqueConstraint("fix_request_id", "provider", name="uq_connection"),)


class FixPlan(Base):
    __tablename__ = "fix_plans"
    id: Mapped[int] = pk()
    fix_request_id: Mapped[int] = fk("fix_requests.id", "CASCADE")
    provider: Mapped[str] = txt()
    base_run_id: Mapped[int | None] = fk("measurement_runs.id", "SET NULL", nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = txt()
    generation_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()
    approved_at: Mapped[datetime | None] = ts()
    approved_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)

    __table_args__ = (
        UniqueConstraint("fix_request_id", "provider", "version", name="uq_fix_plan_version"),
        Index(
            "uq_fix_plan_approved",
            "fix_request_id",
            "provider",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )


class FixPlanItem(Base):
    __tablename__ = "fix_plan_items"
    id: Mapped[int] = pk()
    fix_plan_id: Mapped[int] = fk("fix_plans.id", "CASCADE")
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = txt()
    current_value: Mapped[Any] = jsonb()
    proposed_value: Mapped[Any] = jsonb()
    approved_value: Mapped[Any] = jsonb()
    reason: Mapped[str | None] = txt(nullable=True)
    finding_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'")
    )
    evidence: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    needs_owner_input: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    owner_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    owner_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint("fix_plan_id", "field", name="uq_plan_item_field"),
        CheckConstraint(
            "field NOT IN ('name','address','category','listing')", name="ck_plan_item_forbidden"
        ),
    )


class FixLog(Base):
    __tablename__ = "fix_logs"
    id: Mapped[int] = pk()
    fix_plan_item_id: Mapped[int] = fk("fix_plan_items.id", "CASCADE")
    fix_request_id: Mapped[int] = fk("fix_requests.id", "CASCADE")
    provider: Mapped[str] = txt()
    field: Mapped[str] = txt()
    method: Mapped[str] = txt()
    before_value: Mapped[Any] = jsonb()
    applied_value: Mapped[Any] = jsonb(nullable=False)
    status: Mapped[str] = txt()
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = txt(nullable=True)
    manual_reason: Mapped[str | None] = txt(nullable=True)
    applied_at: Mapped[datetime | None] = ts()
    verified_at: Mapped[datetime | None] = ts()
    verify_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    last_checked_at: Mapped[datetime | None] = ts()
    handled_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    handled_at: Mapped[datetime | None] = ts()
    remeasure_value: Mapped[Any] = jsonb()
    remeasure_match: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = created_col()  # 갱신은 DB 트리거

    __table_args__ = (
        UniqueConstraint("fix_plan_item_id", name="fix_logs_fix_plan_item_id_key"),
        Index("ix_fix_logs_request", "fix_request_id"),
        Index(
            "ix_fix_logs_open",
            "status",
            postgresql_where=text("status IN ('queued','pending_reflection','manual_required')"),
        ),
    )


class RemeasureSchedule(Base):
    __tablename__ = "remeasure_schedules"
    id: Mapped[int] = pk()
    fix_request_id: Mapped[int] = fk("fix_requests.id", "CASCADE")
    due_at: Mapped[datetime] = ts(nullable=False)
    triggered_by: Mapped[str] = txt()
    status: Mapped[str] = txt()
    run_id: Mapped[int | None] = fk("measurement_runs.id", "SET NULL", nullable=True)
    started_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (
        Index(
            "uq_remeasure_active",
            "fix_request_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
        Index("ix_remeasure_due", "due_at", postgresql_where=text("status = 'scheduled'")),
    )
