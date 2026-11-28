"""LLM 공통(07 4.4, 06 6장): 오류와 비용 계산. 공급자 구현은 openai_client.py·gemini_client.py."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from seelo.config import get_settings

log = structlog.get_logger()
BACKEND = Path(__file__).resolve().parents[2]


# 다시 시도할 오류: 시간 초과, 429, 5xx·연결 오류, 빈 답변(08 2.2). 나머지(400·401·403·404·거절)는 바로 실패
RETRYABLE = frozenset({"timeout", "rate_limited", "server_error", "empty_answer"})

# 측정 조건 고정(08 2.3): 옵션이 바뀌면 정비 전후 비교가 성립하지 않는다. raw_json에 이 문자열을 남긴다
MEASURE_TOOL_OPTIONS = "openai:web_search/medium/no-location;gemini:google_search"


class LlmError(Exception):
    """reason: not_configured | refused | empty_answer | timeout | rate_limited | server_error | bad_request
    | auth_error | api_error | parse_failed | unknown"""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider, self.reason = provider, reason
        super().__init__(f"{provider}: {reason}")

    @property
    def retryable(self) -> bool:
        return self.reason in RETRYABLE


def reason_for_status(status: int | None) -> str:
    """HTTP 상태 → 오류 코드(ai_executions.error_code)."""
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 500:
        return "server_error"
    if status in (401, 403):
        return "auth_error"
    if status is not None and 400 <= status < 500:
        return "bad_request"
    return "unknown"


@lru_cache
def _pricing(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = BACKEND / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cost_usd(
    provider: str, model: str, *, input_tokens: int | None, output_tokens: int | None, search_calls: int = 0
) -> float:
    """입력/1e6 × inputPer1M + 출력/1e6 × outputPer1M + 검색 횟수 × 건당 요금.

    표에 없으면 0과 경고(06 6장).
    """
    if model.startswith(("codex-cli/", "gemini-cli/")):
        # 별도 API 청구액은 계산하지 않는다. CLI 구독/무료 쿼터 사용은 PC 브리지에서 제한한다.
        return 0.0
    price = _pricing(get_settings().pricing_file).get(provider, {}).get(model)
    if not price:
        log.warning("llm_price_missing", provider=provider, model=model)
        return 0.0
    per_search = price.get("webSearchPerCall", price.get("groundingPerQuery", 0.0))
    return (
        (input_tokens or 0) / 1e6 * price.get("inputPer1M", 0.0)
        + (output_tokens or 0) / 1e6 * price.get("outputPer1M", 0.0)
        + search_calls * per_search
    )
