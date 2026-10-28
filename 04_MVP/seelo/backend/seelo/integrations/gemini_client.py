"""Gemini(08 2.3, google-genai, 2026-10-23 공식 문서로 확인, 2026-10-27 설치 SDK 2.33.0 필드 확인).

- web_answer: Google 검색 그라운딩. 질문 문장만 보낸다.
- 출처 uri는 리디렉션 주소다. 따라가지 않고 그대로 저장하고, 도메인은 web.domain → title 순으로 정한다.
- 그라운딩 메타데이터가 비어 와도 답변 원문이 있으면 성공(출처 []).
"""

import time
from typing import Any

import structlog

from seelo.config import get_settings
from seelo.domain.annotate import annotate_gemini
from seelo.integrations import LlmResult, StructuredResult
from seelo.integrations.llm import MEASURE_TOOL_OPTIONS, LlmError, reason_for_status

log = structlog.get_logger()

AI_TIMEOUT_S = 60.0


class GeminiClient:
    provider = "gemini"

    def __init__(self) -> None:
        self._client: Any = None

    def _sdk(self) -> Any:
        key = get_settings().gemini_api_key.get_secret_value()
        if not key:
            raise LlmError("gemini", "not_configured")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=key)
        return self._client

    async def web_answer(self, prompt: str, *, model: str) -> LlmResult:
        if not model:
            raise LlmError("gemini", "not_configured")
        from google.genai import types

        client = self._sdk()
        started = time.perf_counter()
        try:
            resp = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
            )
        except Exception as e:
            raise _classify(e) from e
        ms = round((time.perf_counter() - started) * 1000)
        answer = resp.text or ""
        if not answer.strip():
            raise LlmError("gemini", "empty_answer")
        cand = resp.candidates[0] if resp.candidates else None
        gm = cand.grounding_metadata if cand else None
        chunks = [
            {"uri": c.web.uri, "title": c.web.title, "domain": getattr(c.web, "domain", None)}
            for c in ((gm.grounding_chunks if gm else None) or [])
            if c.web is not None
        ]
        supports = [
            {
                "start_index": s.segment.start_index if s.segment else None,
                "end_index": s.segment.end_index if s.segment else None,
                "text": s.segment.text if s.segment else None,
                "chunk_indices": list(s.grounding_chunk_indices or []),
            }
            for s in ((gm.grounding_supports if gm else None) or [])
        ]
        annotated, sources = annotate_gemini(answer, chunks, supports)
        raw = resp.model_dump(mode="json")
        raw["_seelo"] = {"options": MEASURE_TOOL_OPTIONS}
        um = resp.usage_metadata
        searches = len((gm.web_search_queries if gm else None) or [])
        log.info("gemini_web_answer", model=model, ms=ms, searches=searches, chunks=len(chunks))
        return LlmResult(
            text=answer,
            sources=sources,
            raw=raw,
            model_id=getattr(resp, "model_version", None) or model,
            input_tokens=um.prompt_token_count if um else None,
            output_tokens=um.candidates_token_count if um else None,
            search_calls=searches,
            latency_ms=ms,
            annotated_text=annotated,
        )

    async def structured(self, prompt: str, schema: Any, *, model: str) -> StructuredResult:
        raise LlmError("gemini", "not_configured")  # 구조화 정리는 OpenAI만 쓴다(08 2.3)


def _classify(e: Exception) -> LlmError:
    import httpx
    from google.genai import errors

    if isinstance(e, errors.APIError):
        return LlmError("gemini", reason_for_status(getattr(e, "code", None)))
    if isinstance(e, httpx.TimeoutException | TimeoutError):
        return LlmError("gemini", "timeout")
    if isinstance(e, httpx.HTTPError):
        return LlmError("gemini", "server_error")
    return LlmError("gemini", "unknown")
