"""OpenAI(08 2.3, 2026-10-23 공식 문서로 확인).

- structured: responses.parse(model, input, text_format=Schema) → output_parsed. 없거나 거절이면 LlmError.
  웹 검색 도구와 구조화 출력을 한 호출에 섞지 않는다.
- web_answer: 웹 검색 도구(web_search, medium, 위치 없음). 질문 문장만 보낸다(지시문 없음).
  인용(url_citation)만 출처로 쓰고, 참고한 전체 목록(web_search_call.action.sources)은 raw에만 남긴다.
- 요청·응답 원문은 로그에 남기지 않는다(모델·토큰·지연 시간만).
"""

import time

import structlog
from pydantic import BaseModel

from seelo.config import get_settings
from seelo.domain.annotate import annotate_openai
from seelo.integrations import LlmResult, StructuredResult
from seelo.integrations.llm import MEASURE_TOOL_OPTIONS, LlmError, reason_for_status

log = structlog.get_logger()

AI_TIMEOUT_S = 60.0


class OpenAiClient:
    provider = "openai"

    def __init__(self) -> None:
        self._client = None

    def _sdk(self):  # noqa: ANN202
        key = get_settings().openai_api_key.get_secret_value()
        if not key:
            raise LlmError("openai", "not_configured")
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=key, timeout=AI_TIMEOUT_S, max_retries=0)
        return self._client

    async def structured(self, prompt: str, schema: type[BaseModel], *, model: str) -> StructuredResult:
        if not model:
            raise LlmError("openai", "not_configured")
        client = self._sdk()
        started = time.perf_counter()
        try:
            resp = await client.responses.parse(model=model, input=prompt, text_format=schema)
        except Exception as e:  # SDK 오류 종류가 많아 한데 묶는다(원문은 남기지 않음)
            log.warning("openai_structured_failed", model=model, error_type=type(e).__name__)
            raise LlmError("openai", "api_error") from e
        parsed = resp.output_parsed
        if parsed is None:
            raise LlmError("openai", "refused")
        usage = resp.usage
        ms = round((time.perf_counter() - started) * 1000)
        log.info("openai_structured", model=resp.model, schema=schema.__name__, ms=ms)
        return StructuredResult(
            parsed=parsed,
            model_id=resp.model,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            latency_ms=ms,
        )

    async def web_answer(self, prompt: str, *, model: str) -> LlmResult:
        if not model:
            raise LlmError("openai", "not_configured")
        client = self._sdk()
        started = time.perf_counter()
        try:
            resp = await client.responses.create(
                model=model,
                input=prompt,
                tools=[{"type": "web_search", "search_context_size": "medium"}],
                include=["web_search_call.action.sources"],
            )
        except Exception as e:
            raise _classify(e) from e
        ms = round((time.perf_counter() - started) * 1000)
        search_calls, cites, refused = 0, [], False
        for item in resp.output:
            if item.type == "web_search_call":
                search_calls += 1
            if item.type == "message":
                for c in item.content:
                    if c.type == "refusal":
                        refused = True
                    if c.type == "output_text":
                        for a in c.annotations or []:
                            if a.type == "url_citation":
                                cites.append((a.url, a.title, a.start_index, a.end_index))
        if refused:
            raise LlmError("openai", "refused")
        answer = resp.output_text or ""
        if not answer.strip():
            raise LlmError("openai", "empty_answer")
        annotated, sources = annotate_openai(answer, cites)
        raw = resp.model_dump(mode="json")
        raw["_seelo"] = {"options": MEASURE_TOOL_OPTIONS}
        usage = resp.usage
        log.info("openai_web_answer", model=resp.model, ms=ms, searches=search_calls, cites=len(cites))
        return LlmResult(
            text=answer,
            sources=sources,
            raw=raw,
            model_id=resp.model,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            search_calls=search_calls,
            latency_ms=ms,
            annotated_text=annotated,
        )


def _classify(e: Exception) -> LlmError:
    """SDK 예외 → 오류 코드. 원문은 남기지 않는다."""
    import openai

    if isinstance(e, openai.APITimeoutError):
        return LlmError("openai", "timeout")
    if isinstance(e, openai.APIConnectionError):
        return LlmError("openai", "server_error")
    if isinstance(e, openai.APIStatusError):
        return LlmError("openai", reason_for_status(e.status_code))
    return LlmError("openai", "unknown")
