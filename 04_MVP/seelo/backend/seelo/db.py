"""DB 엔진·세션(13 2장). 커밋은 항상 명시적으로 한다(01 7.2)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from seelo.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _factory
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=5
        )
        _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _factory is not None
    return _factory


async def dispose_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine, _factory = None, None


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성. 커밋은 서비스 함수가 직접 한다. 남은 트랜잭션은 버린다."""
    async with session_factory()() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """작업(worker)용. 블록 안에서 필요한 곳마다 await session.commit()."""
    async with session_factory()() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()
