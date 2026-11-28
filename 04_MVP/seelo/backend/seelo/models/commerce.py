"""쇼핑몰 전용 데이터. 지도 가게·정비 테이블과 분리한다."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    LargeBinary,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from seelo.models.base import Base, created_col, fk, jsonb, pk, ts, txt


class CommerceShop(Base):
    __tablename__ = "commerce_shops"
    id: Mapped[int] = pk()
    owner_id: Mapped[int] = fk("users.id", "CASCADE")
    platform: Mapped[str] = txt()
    external_id: Mapped[str] = txt()
    shop_no: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = txt()
    manager_status: Mapped[str] = txt(default="not_requested")
    api_status: Mapped[str] = txt(default="not_connected")
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    scopes: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    access_expires_at: Mapped[datetime | None] = ts()
    oauth_state_hash: Mapped[str | None] = txt(nullable=True)
    oauth_expires_at: Mapped[datetime | None] = ts()
    read_verified_at: Mapped[datetime | None] = ts()
    write_verified_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = created_col()
    # 운영자가 위임 목록에서 확인한 가게 고유값·브라우저 세션 상태. AI 추정 값을 넣지 않는다.
    delegation: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    __table_args__ = (
        CheckConstraint("platform IN ('cafe24', 'smartstore')", name="ck_commerce_platform"),
        CheckConstraint("shop_no > 0", name="ck_commerce_shop_no"),
        CheckConstraint(
            "manager_status IN ('not_requested','invited','verified','revoked')",
            name="ck_commerce_manager_status",
        ),
        CheckConstraint(
            "api_status IN ('not_connected','authorized','read_verified','write_verified','revoked')",
            name="ck_commerce_api_status",
        ),
        UniqueConstraint("owner_id", "platform", "external_id", "shop_no", name="uq_commerce_shop"),
    )


class CommerceProduct(Base):
    __tablename__ = "commerce_products"
    id: Mapped[int] = pk()
    shop_id: Mapped[int] = fk("commerce_shops.id", "CASCADE")
    external_id: Mapped[str] = txt()
    name: Mapped[str] = txt()
    identity: Mapped[str] = txt()
    snapshot: Mapped[Any] = jsonb(nullable=False)
    snapshot_hash: Mapped[str] = txt()
    snapshot_source: Mapped[str] = txt()
    facts: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    asked_fields: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    collected_at: Mapped[datetime] = created_col()
    __table_args__ = (UniqueConstraint("shop_id", "external_id", name="uq_commerce_product"),)


class CommercePlan(Base):
    __tablename__ = "commerce_plans"
    id: Mapped[int] = pk()
    product_id: Mapped[int] = fk("commerce_products.id", "CASCADE")
    status: Mapped[str] = txt(default="draft")
    snapshot_hash: Mapped[str] = txt()
    changes: Mapped[Any] = jsonb(nullable=False)
    questions: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    deferred: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    approval: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    model_id: Mapped[str | None] = txt(nullable=True)
    approved_at: Mapped[datetime | None] = ts()
    applied_at: Mapped[datetime | None] = ts()
    # 관리 API 저장과 공개 PC·모바일 확인을 구분한다.
    publication: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    created_at: Mapped[datetime] = created_col()
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','approved','no_changes','applying','applied','pending_reflection',"
            "'uncertain','conflict','rejected','manual_required','manual_recorded','rolled_back','superseded')",
            name="ck_commerce_plan_status",
        ),
        Index(
            "uq_commerce_active_plan",
            "product_id",
            unique=True,
            postgresql_where=text("status IN ('approved','applying','pending_reflection','uncertain')"),
        ),
    )


class CommerceWrite(Base):
    __tablename__ = "commerce_writes"
    id: Mapped[int] = pk()
    plan_id: Mapped[int] = fk("commerce_plans.id", "CASCADE")
    action: Mapped[str] = txt()
    status: Mapped[str] = txt()
    before: Mapped[Any] = jsonb(nullable=False)
    after: Mapped[Any] = jsonb(nullable=False)
    error_code: Mapped[str | None] = txt(nullable=True)
    note: Mapped[str | None] = txt(nullable=True)
    created_at: Mapped[datetime] = created_col()
    finished_at: Mapped[datetime | None] = ts()
    __table_args__ = (CheckConstraint("action IN ('apply','rollback')", name="ck_commerce_write_action"),)


class CommerceJob(Base):
    """브라우저·AI 작업 상태. 저장 결과가 불명확하면 같은 저장을 다시 등록하지 않고 재조회 작업을 만든다."""

    __tablename__ = "commerce_jobs"
    id: Mapped[int] = pk()
    shop_id: Mapped[int] = fk("commerce_shops.id", "CASCADE")
    product_id: Mapped[int | None] = fk("commerce_products.id", "CASCADE", nullable=True)
    plan_id: Mapped[int | None] = fk("commerce_plans.id", "CASCADE", nullable=True)
    kind: Mapped[str] = txt()
    status: Mapped[str] = txt(default="queued")
    dedupe_key: Mapped[str] = txt()
    input: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    result: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    error_code: Mapped[str | None] = txt(nullable=True)
    requested_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    queue_job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = created_col()
    started_at: Mapped[datetime | None] = ts()
    finished_at: Mapped[datetime | None] = ts()
    __table_args__ = (
        CheckConstraint(
            "kind IN ('collect','apply','rollback','verify','catalog','prepare','forget_session','measure')",
            name="ck_commerce_job_kind",
        ),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_commerce_job_status"),
        Index("ix_commerce_jobs_shop", "shop_id", "id"),
        Index("ix_commerce_jobs_plan", "plan_id"),
        Index(
            "uq_commerce_active_job",
            "shop_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )


class CommerceMeasureSet(Base):
    """고정 질문 세트. 비교 기준이 바뀌지 않도록 수정하지 않고 새 세트를 만든다."""

    __tablename__ = "commerce_measure_sets"
    id: Mapped[int] = pk()
    product_id: Mapped[int] = fk("commerce_products.id", "CASCADE")
    name: Mapped[str] = txt()
    common_suffix: Mapped[str] = txt()
    queries: Mapped[Any] = jsonb(nullable=False)
    targets: Mapped[Any] = jsonb(nullable=False)
    created_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    created_at: Mapped[datetime] = created_col()
    __table_args__ = (Index("ix_commerce_measure_sets_product", "product_id"),)


class CommerceMeasureRun(Base):
    """한 측정 회차. 측정 조건·상품 원본 해시·직전 정비안을 함께 남겨 전후를 구분한다."""

    __tablename__ = "commerce_measure_runs"
    id: Mapped[int] = pk()
    set_id: Mapped[int] = fk("commerce_measure_sets.id", "CASCADE")
    product_id: Mapped[int] = fk("commerce_products.id", "CASCADE")
    label: Mapped[str] = txt()
    status: Mapped[str] = txt(default="queued")
    condition: Mapped[Any] = jsonb(nullable=False)
    snapshot_hash: Mapped[str] = txt()
    plan_id: Mapped[int | None] = fk("commerce_plans.id", "SET NULL", nullable=True)
    created_by: Mapped[int | None] = fk("users.id", "SET NULL", nullable=True)
    created_at: Mapped[datetime] = created_col()
    started_at: Mapped[datetime | None] = ts()
    finished_at: Mapped[datetime | None] = ts()
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','partial','failed')",
            name="ck_commerce_measure_run_status",
        ),
        Index("ix_commerce_measure_runs_product", "product_id", "id"),
    )


class CommerceMeasureAnswer(Base):
    """AI 원문 답변 하나. 호출 실패는 status=failed로 남기고 노출 0으로 세지 않는다."""

    __tablename__ = "commerce_measure_answers"
    id: Mapped[int] = pk()
    run_id: Mapped[int] = fk("commerce_measure_runs.id", "CASCADE")
    query_id: Mapped[str] = txt()
    repeat: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = txt()
    error_code: Mapped[str | None] = txt(nullable=True)
    prompt: Mapped[str] = txt()
    raw_text: Mapped[str | None] = txt(nullable=True)
    sources: Mapped[Any] = jsonb(nullable=False, default="'[]'")
    model_id: Mapped[str | None] = txt(nullable=True)
    identified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recommended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_url_cited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluation: Mapped[Any] = jsonb(nullable=False, default="'{}'")
    measured_at: Mapped[datetime] = created_col()
    __table_args__ = (
        CheckConstraint("status IN ('ok','failed')", name="ck_commerce_measure_answer_status"),
        UniqueConstraint("run_id", "query_id", "repeat", "attempt", name="uq_commerce_measure_answer"),
    )
