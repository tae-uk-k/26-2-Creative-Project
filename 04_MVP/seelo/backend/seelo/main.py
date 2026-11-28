"""FastAPI 앱(13 6장). uvicorn seelo.main:app"""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.sessions import SessionMiddleware

from seelo.api.router import api_router
from seelo.config import get_settings
from seelo.db import dispose_engine
from seelo.errors import install_handlers
from seelo.logging import setup_logging

access_log = structlog.get_logger("access")


def allow_test_email_domain() -> None:
    """email-validator는 예약 도메인 .test를 거부한다.

    시드 계정(@seelo.test, 17 2장)으로 로그인하려고 개발·테스트에서만 허용한다(운영은 그대로 거부).
    """
    import email_validator

    if "test" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
        email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("test")


def create_app(*, with_queue: bool = True) -> FastAPI:
    """with_queue=False는 테스트용: 작업 큐 연결 없이 앱만 만든다."""
    s = get_settings()
    setup_logging(s.log_level, cache=s.app_env != "test")
    if s.app_env != "prod":
        allow_test_email_domain()
    if s.sentry_dsn:
        sentry_sdk.init(dsn=s.sentry_dsn, send_default_pii=False, traces_sample_rate=0.0)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if with_queue:
            from seelo.worker.app import app as queue_app

            async with queue_app.open_async():
                yield
        else:
            yield
        await dispose_engine()

    app = FastAPI(
        title="seelo API",
        lifespan=lifespan,
        docs_url="/api/docs" if s.app_env != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if s.app_env != "prod" else None,
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """요청 번호를 붙이고 접근 로그를 남긴다. uvicorn 접근 로그는 끈다(--no-access-log).

        쿼리 문자열은 남기지 않는다: OAuth 콜백의 code·state, 메일 티켓이 들어 있다(05 12장).
        """
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            ms = round((time.perf_counter() - started) * 1000)
            access_log.info("http_request", method=request.method, status=status, ms=ms)
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-Id"] = rid
        return response

    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key.get_secret_value(),
        session_cookie="seelo_oauth",
        max_age=600,
        same_site="lax",
        https_only=s.cookie_secure,
    )
    install_handlers(app)
    app.include_router(api_router, prefix="/api")
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn seelo.main:app`일 때만 앱을 만든다(테스트에서 import만 해도 설정을 읽지 않게).
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
