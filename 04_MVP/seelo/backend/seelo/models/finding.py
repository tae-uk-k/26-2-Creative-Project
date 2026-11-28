"""고쳐야 할 점(02 4장 4절)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, txt


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = pk()
    run_id: Mapped[int] = fk("measurement_runs.id", "CASCADE")
    fix_plan_id: Mapped[int | None] = fk(
        "fix_plans.id", "CASCADE", nullable=True, name="fk_findings_fix_plan", use_alter=True
    )
    stage: Mapped[str] = txt()
    category: Mapped[str] = txt()
    title_key: Mapped[str] = txt()
    provider: Mapped[str] = txt()
    field: Mapped[str] = txt()
    competitor_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    evidence: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (Index("ix_findings_run_stage", "run_id", "stage"),)
