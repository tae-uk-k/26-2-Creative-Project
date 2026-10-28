"""상태 값과 전이(03 1~2장, 13 9장). 상태는 transition()으로만 바꾼다."""

from enum import StrEnum
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"


class AuthProvider(StrEnum):
    EMAIL = "email"
    GOOGLE = "google"
    KAKAO = "kakao"


class SocialProvider(StrEnum):
    GOOGLE = "google"
    KAKAO = "kakao"


class TokenType(StrEnum):
    VERIFY = "verify"
    RESET = "reset"


class Category(StrEnum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BAR = "bar"


class MapProvider(StrEnum):
    GOOGLE = "google"
    KAKAO = "kakao"


class InputProvider(StrEnum):
    GOOGLE = "google"
    KAKAO = "kakao"
    NAVER = "naver"


class SourceProvider(StrEnum):
    GOOGLE = "google"
    KAKAO = "kakao"
    NAVER = "naver"
    WEBSITE = "website"
    INSTAGRAM = "instagram"


class SnapshotProvider(StrEnum):
    GOOGLE = "google"
    WEBSITE = "website"
    INSTAGRAM = "instagram"


class AiProvider(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"


class IdentifyMode(StrEnum):
    NEW = "new"
    CHANGE = "change"


class MatchStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    CANDIDATE = "candidate"


class SnapshotStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    ROBOTS_DISALLOWED = "robots_disallowed"
    SKIPPED = "skipped"


class StoreStatus(StrEnum):
    COLLECTING = "collecting"
    COLLECTED = "collected"
    MEASURING = "measuring"
    DIAGNOSED = "diagnosed"
    MEASURE_FAILED = "measure_failed"
    ARCHIVED = "archived"


class RunKind(StrEnum):
    DIAGNOSIS = "diagnosis"
    REMEASURE = "remeasure"


class RunTrigger(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"
    SCHEDULER = "scheduler"
    ADMIN = "admin"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class RunStage(StrEnum):
    COLLECTING = "collecting"
    GENERATING_QUESTIONS = "generating_questions"
    CALLING_AI = "calling_ai"
    FINALIZING = "finalizing"
    DONE = "done"


class WaitingReason(StrEnum):
    COST_LIMIT = "cost_limit"


class FailureReason(StrEnum):
    FAILURE_RATE = "failure_rate"
    COLLECT_INSUFFICIENT = "collect_insufficient"
    ENQUEUE_FAILED = "enqueue_failed"
    STUCK = "stuck"


class Lang(StrEnum):
    EN = "en"
    KO = "ko"


class IntentType(StrEnum):
    BASIC = "basic"
    CONDITIONAL = "conditional"


class GeneratedBy(StrEnum):
    LLM = "llm"
    TEMPLATE = "template"


class ExecStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SubjectType(StrEnum):
    TARGET = "target"
    COMPETITOR = "competitor"
    SOURCE = "source"


class MetricName(StrEnum):
    SUCCESS_COUNT = "success_count"
    APPEARANCE_COUNT = "appearance_count"
    APPEARANCE_RATE = "appearance_rate"
    AVG_RANK = "avg_rank"
    CITATION_COUNT = "citation_count"
    TARGET_CITATION_COUNT = "target_citation_count"


class FindingStage(StrEnum):
    DIAGNOSIS = "diagnosis"
    PLAN = "plan"


class FindingCategory(StrEnum):
    MAP_MISSING = "map_missing"
    SOURCE_MISMATCH = "source_mismatch"
    ENGLISH_MISSING = "english_missing"
    CONDITION_MISSING = "condition_missing"
    AI_WRONG = "ai_wrong"


class FixRequestStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    CONNECTING = "connecting"
    FIXING = "fixing"
    REMEASURE_SCHEDULED = "remeasure_scheduled"
    REMEASURING = "remeasuring"
    REMEASURE_FAILED = "remeasure_failed"
    REPORT_READY = "report_ready"
    REJECTED = "rejected"


class ConnectionStatus(StrEnum):
    NOT_CONNECTED = "not_connected"
    INVITED = "invited"
    CONNECTED = "connected"
    NEEDS_ATTENTION = "needs_attention"
    REVOKED = "revoked"


class AttentionReason(StrEnum):
    VERIFICATION_REQUIRED = "verification_required"
    UNDER_REVIEW = "under_review"
    DUPLICATE_PROFILE = "duplicate_profile"
    NO_OWNER_AUTHORITY = "no_owner_authority"
    GUIDELINE_VIOLATION = "guideline_violation"
    STORE_NOT_VISIBLE = "store_not_visible"
    OTHER = "other"


class FixPlanStatus(StrEnum):
    GENERATING = "generating"
    GENERATION_FAILED = "generation_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"


class FixLogStatus(StrEnum):
    QUEUED = "queued"
    APPLIED = "applied"
    PENDING_REFLECTION = "pending_reflection"
    MANUAL_REQUIRED = "manual_required"
    MANUAL_DONE = "manual_done"
    DISCONNECTED = "disconnected"


class FixMethod(StrEnum):
    BROWSER = "browser"
    API = "api"
    MANUAL = "manual"


class ManualReason(StrEnum):
    AUTOMATION_BLOCKED = "automation_blocked"
    WRITE_FAILED = "write_failed"
    NOT_REFLECTED_24H = "not_reflected_24h"
    KAKAO_FIX_DISABLED = "kakao_fix_disabled"
    API_UNSUPPORTED = "api_unsupported"
    AUTOMATION_DISABLED = "automation_disabled"


class RemeasureMatch(StrEnum):
    MATCH = "match"
    DIFFERS = "differs"
    UNKNOWN = "unknown"


class ScheduleStatus(StrEnum):
    SCHEDULED = "scheduled"
    STARTED = "started"
    CANCELED = "canceled"


class TriggeredBy(StrEnum):
    SCHEDULER = "scheduler"
    ADMIN = "admin"


class ReportStatus(StrEnum):
    GENERATING = "generating"
    COMPLETED = "completed"
    GENERATION_FAILED = "generation_failed"


class EmailType(StrEnum):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"
    DIAGNOSIS_RESULT = "diagnosis_result"
    FIX_REQUESTED = "fix_requested"
    FIX_DECIDED = "fix_decided"
    MAP_CONNECTION = "map_connection"
    FIX_PLAN_READY = "fix_plan_ready"
    MANUAL_REQUIRED = "manual_required"
    FIX_COMPLETED = "fix_completed"
    REPORT_READY = "report_ready"


class EmailStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


TERMINAL_FIX_LOG = frozenset({FixLogStatus.APPLIED, FixLogStatus.MANUAL_DONE, FixLogStatus.DISCONNECTED})
ACTIVE_REQUEST = frozenset(set(FixRequestStatus) - {FixRequestStatus.REJECTED, FixRequestStatus.REPORT_READY})

# (테이블, 컬럼) → Enum. DDL의 CHECK 값 목록과 같아야 한다(tests/integration/test_schema.py).
CHECK_ENUMS: dict[tuple[str, str], type[StrEnum]] = {
    ("users", "role"): Role,
    ("auth_identities", "provider"): AuthProvider,
    ("auth_tokens", "type"): TokenType,
    ("pending_signups", "provider"): SocialProvider,
    ("identify_sessions", "mode"): IdentifyMode,
    ("identify_sessions", "input_provider"): InputProvider,
    ("stores", "input_provider"): InputProvider,
    ("stores", "category"): Category,
    ("stores", "status"): StoreStatus,
    ("store_sources", "provider"): SourceProvider,
    ("store_sources", "match_status"): MatchStatus,
    ("measurement_runs", "kind"): RunKind,
    ("measurement_runs", "trigger"): RunTrigger,
    ("measurement_runs", "status"): RunStatus,
    ("measurement_runs", "stage"): RunStage,
    ("measurement_runs", "waiting_reason"): WaitingReason,
    ("measurement_runs", "failure_reason"): FailureReason,
    ("source_snapshots", "provider"): SnapshotProvider,
    ("source_snapshots", "status"): SnapshotStatus,
    ("web_evidence", "provider"): AiProvider,
    ("question_sets", "category"): Category,
    ("question_sets", "generated_by"): GeneratedBy,
    ("questions", "lang"): Lang,
    ("questions", "intent_type"): IntentType,
    ("ai_executions", "provider"): AiProvider,
    ("ai_executions", "status"): ExecStatus,
    ("ai_responses", "extraction_status"): ExtractionStatus,
    ("metrics", "provider"): AiProvider,
    ("metrics", "subject_type"): SubjectType,
    ("metrics", "metric_name"): MetricName,
    ("fix_requests", "status"): FixRequestStatus,
    ("findings", "stage"): FindingStage,
    ("findings", "category"): FindingCategory,
    ("findings", "provider"): MapProvider,
    ("map_connections", "provider"): MapProvider,
    ("map_connections", "status"): ConnectionStatus,
    ("map_connections", "attention_reason"): AttentionReason,
    ("fix_plans", "provider"): MapProvider,
    ("fix_plans", "status"): FixPlanStatus,
    ("fix_logs", "provider"): MapProvider,
    ("fix_logs", "method"): FixMethod,
    ("fix_logs", "status"): FixLogStatus,
    ("fix_logs", "manual_reason"): ManualReason,
    ("fix_logs", "remeasure_match"): RemeasureMatch,
    ("remeasure_schedules", "triggered_by"): TriggeredBy,
    ("remeasure_schedules", "status"): ScheduleStatus,
    ("comparison_reports", "status"): ReportStatus,
    ("email_logs", "type"): EmailType,
    ("email_logs", "status"): EmailStatus,
}

# 허용 전이(03 2장). 테이블 이름 → {현재 상태: {다음 상태들}}
ALLOWED: dict[str, dict[str, set[str]]] = {
    "stores": {
        "collecting": {"measuring", "collected", "measure_failed", "archived"},
        "measuring": {"diagnosed", "measure_failed", "archived"},
        "measure_failed": {"collecting", "archived"},
        "collected": {"collecting", "archived"},
        "diagnosed": {"archived"},
    },
    "measurement_runs": {
        "queued": {"running", "failed", "canceled"},
        "running": {"parsing", "failed", "canceled"},
        "parsing": {"completed", "failed", "canceled"},
    },
    "fix_requests": {
        "requested": {"approved", "rejected"},
        "approved": {"connecting"},
        "connecting": {"fixing"},
        "fixing": {"remeasure_scheduled"},
        "remeasure_scheduled": {"fixing", "remeasuring"},
        "remeasuring": {"report_ready", "remeasure_failed"},
        "remeasure_failed": {"remeasuring"},
    },
    "map_connections": {
        "not_connected": {"invited", "connected", "needs_attention"},
        "invited": {"connected", "needs_attention"},
        "needs_attention": {"invited", "connected", "needs_attention"},
        "connected": {"revoked"},
        "revoked": {"invited"},
    },
    "fix_plans": {
        "generating": {"awaiting_approval", "generation_failed"},
        "generation_failed": {"generating"},
        "awaiting_approval": {"approved"},
    },
    "fix_logs": {
        "queued": {"applied", "pending_reflection", "manual_required", "disconnected"},
        "pending_reflection": {"applied", "manual_required", "disconnected"},
        "manual_required": {"manual_done", "disconnected"},
    },
    "remeasure_schedules": {"scheduled": {"started", "canceled"}},
    "comparison_reports": {"generating": {"completed", "generation_failed"}},
    "email_logs": {"queued": {"sent", "failed"}},
}


def check_allowed(table: str, from_: set[str] | frozenset[str], to: str) -> None:
    """허용표에 없는 전이는 코드 오류다."""
    if not from_:
        raise ValueError("from_ must not be empty")
    rules = ALLOWED[table]
    for f in from_:
        if to not in rules.get(f, set()):
            raise ValueError(f"illegal transition {table}: {f} -> {to}")


async def transition(
    session: AsyncSession,
    model: Any,
    row_id: int,
    *,
    from_: set[str] | frozenset[str],
    to: str,
    values: dict[str, Any] | None = None,
) -> bool:
    """조건부 UPDATE. 현재 상태가 from_ 중 하나일 때만 바꾸고 True. 아니면 False(커밋은 부르는 쪽)."""
    check_allowed(model.__tablename__, from_, to)
    stmt = (
        update(model)
        .where(model.id == row_id, model.status.in_([str(f) for f in from_]))
        .values(status=str(to), **(values or {}))
        .returning(model.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
