"""전후 비교 보고서(02 4장 4절)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Integer, SmallInteger, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class ComparisonReport(Base):
    __tablename__ = "comparison_reports"
    id: Mapped[int] = pk()
    fix_request_id: Mapped[int] = fk("fix_requests.id", "CASCADE")
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    base_run_id: Mapped[int | None] = fk("measurement_runs.id", "SET NULL", nullable=True)
    after_run_id: Mapped[int | None] = fk("measurement_runs.id", "SET NULL", nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = txt()
    generation_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = txt(nullable=True)
    content: Mapped[Any] = jsonb()
    created_at: Mapped[datetime] = created_col()
    completed_at: Mapped[datetime | None] = ts()

    __table_args__ = (UniqueConstraint("fix_request_id", "version", name="uq_report_version"),)
