"""질문·측정 테이블(02 4장 3절)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class QuestionSet(Base):
    __tablename__ = "question_sets"
    id: Mapped[int] = pk()
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    region_ko: Mapped[str] = txt()
    region_en: Mapped[str] = txt()
    category: Mapped[str] = txt()
    features: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    generated_by: Mapped[str] = txt()
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("store_id", "version", name="uq_question_set_version"),)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = pk()
    question_set_id: Mapped[int] = fk("question_sets.id", "CASCADE")
    order_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lang: Mapped[str] = txt()
    intent_type: Mapped[str] = txt()
    text: Mapped[str] = txt()
    text_ko: Mapped[str | None] = txt(nullable=True)

    __table_args__ = (UniqueConstraint("question_set_id", "order_no", name="uq_question_order"),)


class MeasurementRun(Base):
    __tablename__ = "measurement_runs"
    id: Mapped[int] = pk()
    store_id: Mapped[int] = fk("stores.id", "CASCADE")
    question_set_id: Mapped[int | None] = fk(
        "question_sets.id", "SET NULL", nullable=True, name="fk_runs_question_set", use_alter=True
    )
    kind: Mapped[str] = txt()
    fix_request_id: Mapped[int | None] = fk(
        "fix_requests.id", "SET NULL", nullable=True, name="fk_runs_fix_request", use_alter=True
    )
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    trigger: Mapped[str] = txt()
    status: Mapped[str] = txt()
    stage: Mapped[str] = txt(default="collecting")
    waiting_reason: Mapped[str | None] = txt(nullable=True)
    failure_reason: Mapped[str | None] = txt(nullable=True)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failure_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    extraction_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default=text("0"))
    started_at: Mapped[datetime | None] = ts()
    completed_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = created_col()  # 갱신은 DB 트리거

    __table_args__ = (
        CheckConstraint("NOT is_free OR kind = 'diagnosis'", name="ck_run_free_kind"),
        Index("ix_runs_store_created", "store_id", text("created_at DESC")),
        Index(
            "ix_runs_active",
            "status",
            postgresql_where=text("status IN ('queued','running','parsing')"),
        ),
    )


class AiExecution(Base):
    __tablename__ = "ai_executions"
    id: Mapped[int] = pk()
    run_id: Mapped[int] = fk("measurement_runs.id", "CASCADE")
    question_id: Mapped[int] = fk("questions.id", "CASCADE")
    provider: Mapped[str] = txt()
    model_id: Mapped[str | None] = txt(nullable=True)
    repeat_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = txt()
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = txt(nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    web_search_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_col()
    finished_at: Mapped[datetime | None] = ts()

    __table_args__ = (
        UniqueConstraint("run_id", "question_id", "provider", "repeat_no", name="uq_ai_execution"),
        Index("ix_ai_exec_run_status", "run_id", "status"),
    )


class AiResponse(Base):
    __tablename__ = "ai_responses"
    id: Mapped[int] = pk()
    execution_id: Mapped[int] = fk("ai_executions.id", "CASCADE")
    raw_text: Mapped[str] = txt()
    raw_json: Mapped[Any] = jsonb(nullable=False)
    source_urls: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    annotated_text: Mapped[str | None] = txt(nullable=True)
    extraction_status: Mapped[str] = txt(default="pending")
    extraction_json: Mapped[Any] = jsonb()
    target_claims: Mapped[Any] = jsonb()
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("execution_id", name="ai_responses_execution_id_key"),)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = pk()
    response_id: Mapped[int] = fk("ai_responses.id", "CASCADE")
    name: Mapped[str] = txt()
    normalized_name: Mapped[str] = txt()
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_urls: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    mentioned_attributes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    is_target: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index("ix_recommendations_response", "response_id"),
        Index("ix_recommendations_name", "normalized_name"),
    )


class Metric(Base):
    __tablename__ = "metrics"
    id: Mapped[int] = pk()
    run_id: Mapped[int] = fk("measurement_runs.id", "CASCADE")
    provider: Mapped[str] = txt()
    question_id: Mapped[int | None] = fk("questions.id", "CASCADE", nullable=True)
    subject_type: Mapped[str] = txt()
    subject_name: Mapped[str] = txt()
    metric_name: Mapped[str] = txt()
    value: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    denominator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_order: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    display_name: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()

    __table_args__ = (Index("ix_metrics_run", "run_id", "subject_type", "provider"),)
