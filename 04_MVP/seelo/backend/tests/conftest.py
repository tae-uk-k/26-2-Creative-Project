"""테스트 공통 장치(11 2장).

- DB 테스트는 실제 PostgreSQL에서 돈다. TEST_DATABASE_URL(postgresql+psycopg://...)이 있으면 그 DB를,
  없으면 testcontainers로 postgres:16 컨테이너를 고정 포트(TEST_PG_PORT, 기본 55432)에 띄운다(Docker 필요).
- 포트를 고정하는 이유: Procrastinate 앱(seelo.worker.app)은 import될 때 DB 주소를 읽는다. 주소를
  conftest import 시점에 확정해 두면 어떤 테스트 모듈이 먼저 import돼도 같은 DB를 쓴다.
- 세션 시작 때 alembic upgrade head와 Procrastinate 스키마를 적용하고, 테스트마다 모든 테이블을 비운다.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND = Path(__file__).resolve().parents[1]
TEST_PG_PORT = int(os.environ.get("TEST_PG_PORT", "55432"))
_EXTERNAL_DB = os.environ.get("TEST_DATABASE_URL")
# localhost가 아니라 127.0.0.1: Windows에서 localhost가 ::1(IPv6)로 먼저 풀리면 Docker 포트 연결이
# 응답 없이 멈출 때가 있다(2026-10-27 Docker Desktop 재시작 뒤 확인)
TEST_DB_URL = _EXTERNAL_DB or f"postgresql+psycopg://test:test@127.0.0.1:{TEST_PG_PORT}/test"

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DB_URL,
        "QUEUE_DATABASE_DSN": TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://", 1),
        "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789",
        "EMAIL_HMAC_KEY": "test-email-hmac-key",
        "MAIL_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
        "FAKE_EXTERNALS": "true",
        "LOG_LEVEL": "WARNING",
        "APP_BASE_URL": "http://seelo.test",
        "ADMIN_NOTIFY_EMAILS": "admin1@seelo.test,admin2@seelo.test",
    }
)


@pytest.fixture(scope="session")
def pg() -> Iterator[dict[str, str]]:
    container: Any = None
    if not _EXTERNAL_DB:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer(
            "postgres:16", username="test", password="test", dbname="test", driver="psycopg"
        ).with_bind_ports(5432, TEST_PG_PORT)
        container.start()
    from seelo.config import get_settings

    get_settings.cache_clear()
    env = {**os.environ}
    try:  # 준비가 실패해도 컨테이너를 지운다(남으면 다음 실행이 같은 포트를 못 쓴다)
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, env=env)
        subprocess.run([sys.executable, "scripts/init_queue_schema.py"], cwd=BACKEND, check=True, env=env)
        yield {"url": os.environ["DATABASE_URL"], "dsn": os.environ["QUEUE_DATABASE_DSN"]}
    finally:
        if container is not None:
            container.stop()


async def _truncate_all(session: AsyncSession) -> None:
    rows = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
    )
    tables = [r[0] for r in rows]
    if tables:
        await session.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await session.commit()


@pytest.fixture
async def db(pg: dict[str, str]) -> AsyncIterator[AsyncSession]:
    """비운 DB에 연결된 세션. 엔진은 테스트마다 새로 만든다."""
    from seelo.db import dispose_engine, session_factory

    await dispose_engine()
    async with session_factory()() as session:
        await _truncate_all(session)
        yield session
        if session.in_transaction():
            await session.rollback()
    await dispose_engine()


@pytest.fixture
async def queue_app(db: AsyncSession) -> AsyncIterator[Any]:
    """작업 등록·실행이 필요한 테스트용: 열린 Procrastinate 앱."""
    from seelo.worker.app import app

    async with app.open_async():
        yield app


@pytest.fixture
async def api(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    from seelo.main import create_app

    app = create_app(with_queue=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def make_client(queue_app: Any) -> AsyncIterator[Callable[[], Awaitable[httpx.AsyncClient]]]:
    """브라우저 하나 = 클라이언트 하나. CSRF 쿠키를 먼저 받고, 상태를 바꾸는 요청에 헤더를 자동으로 붙인다."""
    from seelo.main import create_app
    from tests.support import build_client

    app = create_app(with_queue=False)
    made: list[httpx.AsyncClient] = []

    async def factory() -> httpx.AsyncClient:
        c = build_client(app)
        made.append(c)
        await c.get("/api/auth/csrf")
        return c

    yield factory
    for c in made:
        await c.aclose()


@pytest.fixture
async def client(make_client: Callable[[], Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client()


@dataclass
class FakeMailer:
    """보낸 메일을 모으고, fail_times만큼 먼저 실패한다(11 3장)."""

    fail_times: int = 0
    sent: list[dict[str, Any]] = field(default_factory=list)
    calls: int = 0

    async def send(self, *, to: list[str], subject: str, text: str, html: str) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError(f"smtp down (to {to[0]})")
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


@pytest.fixture
def fake_mailer() -> Iterator[FakeMailer]:
    import dataclasses

    from seelo.integrations import set_clients
    from seelo.integrations.fakes import build_fake_clients

    mailer = FakeMailer()
    set_clients(dataclasses.replace(build_fake_clients(), mailer=mailer))
    try:
        yield mailer
    finally:
        set_clients(None)


@pytest.fixture
def fake_oauth(fake_mailer: FakeMailer) -> Iterator[Any]:
    """가짜 구글·카카오 로그인. profiles[code] = OAuthProfile로 사용자를 정한다(메일은 fake_mailer)."""
    import dataclasses

    from seelo.integrations import get_clients, set_clients
    from seelo.integrations.fakes import FakeOAuth

    oauth = FakeOAuth()
    set_clients(dataclasses.replace(get_clients(), oauth=oauth))
    yield oauth


@pytest.fixture
def maps(fake_mailer: FakeMailer) -> Iterator[Any]:
    """빈 가짜 지도 세계(Places·카카오·네이버·짧은 링크). 테스트가 world·fail_next를 채운다."""
    import dataclasses
    from types import SimpleNamespace

    from seelo.integrations import get_clients, set_clients
    from seelo.integrations.fake_maps import FakeKakao, FakeNaver, FakePlaces, FakeShortLinks

    world = SimpleNamespace(
        places=FakePlaces(), kakao=FakeKakao(), naver=FakeNaver(), short_links=FakeShortLinks()
    )
    set_clients(dataclasses.replace(get_clients(), **vars(world)))
    yield world


@pytest.fixture
def web(maps: Any) -> Iterator[Any]:
    """가짜 웹 서버(진짜 HttpWebsiteFetcher 규칙으로 읽힘)와 가짜 LLM. maps 위에 얹는다."""
    import dataclasses
    from types import SimpleNamespace

    from seelo.integrations import get_clients, set_clients
    from seelo.integrations.fake_web import FakeLlm, FakeWebServer, fake_website

    server, llm = FakeWebServer(), FakeLlm()
    set_clients(dataclasses.replace(get_clients(), website=fake_website(server), openai=llm))
    yield SimpleNamespace(server=server, llm=llm)


@pytest.fixture
def ai(maps: Any) -> Iterator[Any]:
    """가짜 OpenAI·Gemini(FakeLlm). maps 위에 얹는다. ai.openai·ai.gemini로 결과·실패를 정한다."""
    import dataclasses
    from types import SimpleNamespace

    from seelo.integrations import get_clients, set_clients
    from seelo.integrations.fake_web import FakeLlm

    ns = SimpleNamespace(openai=FakeLlm(provider="openai"), gemini=FakeLlm(provider="gemini"))
    set_clients(dataclasses.replace(get_clients(), openai=ns.openai, gemini=ns.gemini))
    yield ns


@pytest.fixture
def map_admin(fake_mailer: FakeMailer) -> Iterator[Any]:
    """가짜 지도 관리 화면(FakeMapAdmins). map_admin["google"].not_visible()처럼 상황을 만든다."""
    import dataclasses

    from seelo.integrations import get_clients, set_clients
    from seelo.integrations.fake_admin import FakeMapAdmins

    admins = FakeMapAdmins()
    set_clients(dataclasses.replace(get_clients(), map_admin=admins))
    yield admins


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """테스트 동안 설정 값을 바꾼다: settings_env(AI_REPEAT_COUNT="2"). 끝나면 원래대로."""
    from seelo.config import get_settings
    from seelo.integrations import llm

    def setter(**values: str) -> None:
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        llm._pricing.cache_clear()

    yield setter
    get_settings.cache_clear()
    llm._pricing.cache_clear()


@pytest.fixture
def frozen_time() -> Iterator[Any]:
    """시계를 어느 분의 10초에 멈춘다(11 2장). 분 단위 요청 제한이 분 경계에서 나뉘지 않게.

    traveller.shift(초)로 옮길 수 있다. 단조 시계(asyncio)는 멈추지 않는다.
    """
    import time_machine

    from seelo.timeutil import now_utc

    start = now_utc().replace(second=10, microsecond=0)
    with time_machine.travel(start, tick=False) as traveller:
        yield traveller
