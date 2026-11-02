"""PC 전용 loopback 서버. GCP에서는 기존 SSH의 Unix socket으로만 접근한다."""

import argparse
import hmac
import os
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from seelo.integrations.llm import LlmError
from seelo.local_ai.runner import CliRunner


class Call(BaseModel):
    provider: Literal["openai", "gemini"]
    model: str = Field(min_length=1, max_length=100)
    operation: Literal["web", "structured"]
    prompt: str = Field(min_length=1, max_length=100_000)
    output_schema: dict | None = None


def create_app(runner: CliRunner, token: str) -> FastAPI:
    if len(token) < 32:
        raise ValueError("LOCAL_AI_TOKEN must contain at least 32 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse({"error": "bad_request"}, status_code=422)

    def authenticate(request: Request, authorization: str | None) -> None:
        if request.headers.get("origin") or not hmac.compare_digest(authorization or "", "Bearer " + token):
            raise HTTPException(401, "unauthorized")

    @app.get("/health")
    async def health(request: Request, authorization: str | None = Header(default=None)):
        authenticate(request, authorization)
        return {"status": "ok", "mode": "local_cli", "measurement_profile": "local-cli-web/v1"}

    @app.post("/call")
    async def call(body: Call, request: Request, authorization: str | None = Header(default=None)):
        authenticate(request, authorization)
        if body.output_schema and len(str(body.output_schema)) > 80_000:
            return JSONResponse({"error": "bad_request"}, status_code=422)
        try:
            return await runner.call(
                body.provider, body.model, body.prompt, body.operation, body.output_schema
            )
        except LlmError as error:
            status = 429 if error.reason == "rate_limited" else 503
            return JSONResponse({"error": error.reason}, status_code=status)
        except OSError:
            return JSONResponse({"error": "not_configured"}, status_code=503)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="seelo local AI bridge (loopback only)")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=False)
    token = os.environ.get("LOCAL_AI_TOKEN", "")
    directory = Path(os.environ["LOCAL_AI_DATA_DIR"])
    runner = CliRunner(directory, daily_limit=int(os.environ.get("LOCAL_AI_DAILY_LIMIT", "120")))
    uvicorn.run(
        create_app(runner, token),
        host="127.0.0.1",
        port=int(os.environ.get("LOCAL_AI_PORT", "18765")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
