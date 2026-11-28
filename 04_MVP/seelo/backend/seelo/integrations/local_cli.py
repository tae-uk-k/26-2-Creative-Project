"""SSH Unix socket으로 PC의 공식 CLI에 연결한다. API 경로로 자동 대체하지 않는다."""

import time
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from seelo.config import get_settings
from seelo.integrations import LlmResult, StructuredResult
from seelo.integrations.llm import LlmError


class LocalCliClient:
    def __init__(self, provider: str) -> None:
        if provider not in {"openai", "gemini"}:
            raise ValueError("unsupported local CLI provider")
        self.provider = provider

    async def _call(self, prompt: str, model: str, operation: str, schema: dict | None = None) -> dict:
        s = get_settings()
        prefix = "codex-cli/" if self.provider == "openai" else "gemini-cli/"
        if not model.startswith(prefix) or not s.local_ai_token.get_secret_value():
            raise LlmError(self.provider, "not_configured")
        if s.local_ai_socket:
            transport = httpx.AsyncHTTPTransport(uds=s.local_ai_socket, retries=0)
            url = "http://seelo-ai.local"
        else:
            parsed = urlsplit(s.local_ai_url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username:
                raise LlmError(self.provider, "not_configured")
            transport, url = httpx.AsyncHTTPTransport(retries=0), s.local_ai_url
        try:
            async with httpx.AsyncClient(
                base_url=url,
                transport=transport,
                timeout=s.local_ai_timeout_s,
                trust_env=False,
            ) as client:
                response = await client.post(
                    "/call",
                    headers={"Authorization": "Bearer " + s.local_ai_token.get_secret_value()},
                    json={
                        "provider": self.provider,
                        "model": model,
                        "operation": operation,
                        "prompt": prompt,
                        "output_schema": schema,
                    },
                )
        except httpx.TimeoutException as e:
            raise LlmError(self.provider, "timeout") from e
        except httpx.HTTPError as e:
            raise LlmError(self.provider, "server_error") from e
        if response.status_code != 200:
            reason = {401: "auth_error", 403: "auth_error", 429: "rate_limited"}.get(
                response.status_code, "server_error"
            )
            try:
                code = response.json().get("error")
                if code in {"auth_error", "not_configured", "parse_failed", "refused", "timeout"}:
                    reason = code
            except ValueError:
                pass
            raise LlmError(self.provider, reason)
        try:
            result = response.json()
            if not result["model_id"].startswith(prefix):
                raise ValueError("provider mismatch")
            return result
        except (ValueError, KeyError, TypeError) as e:
            raise LlmError(self.provider, "parse_failed") from e

    async def structured(self, prompt: str, schema: type[BaseModel], *, model: str) -> StructuredResult:
        started = time.perf_counter()
        data = await self._call(prompt, model, "structured", schema.model_json_schema())
        try:
            parsed = schema.model_validate(data["output"])
        except (KeyError, ValidationError) as e:
            raise LlmError(self.provider, "parse_failed") from e
        return StructuredResult(
            parsed=parsed,
            model_id=data["model_id"],
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    async def web_answer(self, prompt: str, *, model: str) -> LlmResult:
        started = time.perf_counter()
        data = await self._call(prompt, model, "web")
        try:
            output = data["output"]
            text = output["text"]
            if not isinstance(text, str) or not text.strip() or data["search_calls"] < 1:
                raise ValueError("missing real web-search evidence")
            sources = []
            for i, source in enumerate(output["sources"], 1):
                url = urlsplit(source["url"])
                if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
                    raise ValueError("invalid citation URL")
                sources.append(
                    {"n": i, "url": source["url"], "title": source["title"], "domain": url.hostname}
                )
            if not sources:
                raise ValueError("missing sources")
        except (KeyError, TypeError, ValueError) as e:
            raise LlmError(self.provider, "parse_failed") from e
        raw = {
            "_seelo": {
                "transport": "local_cli",
                "options": "local-cli-web/v1",
                "citation_mode": "cli_reported_reference_list",
                "billing_mode": "subscription_quota_not_api_invoice",
            },
            "model_id": data["model_id"],
            "search_calls": data["search_calls"],
        }
        return LlmResult(
            text=text,
            sources=sources,
            raw=raw,
            model_id=data["model_id"],
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            search_calls=data["search_calls"],
            latency_ms=round((time.perf_counter() - started) * 1000),
            annotated_text=text,
        )
