"""1단계: transition()(03 2장) — 허용·불허·동시 요청."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import session_factory
from seelo.domain.states import transition
from seelo.models import Store, User
from seelo.timeutil import now_utc


async def _store(db: AsyncSession) -> int:
    user = User(email="t@seelo.test")
    db.add(user)
    await db.flush()
    store = Store(
        owner_id=user.id,
        name="데모식당",
        input_url="u",
        input_provider="google",
        category="restaurant",
        status="collecting",
    )
    db.add(store)
    await db.flush()
    await db.commit()
    return store.id


async def test_allowed_transition_then_stale(db: AsyncSession) -> None:
    sid = await _store(db)
    assert await transition(db, Store, sid, from_={"collecting"}, to="measuring") is True
    await db.commit()
    # 이미 measuring이므로 같은 요청은 False(이미 처리됨)
    assert await transition(db, Store, sid, from_={"collecting"}, to="measuring") is False
    status = await db.scalar(select(Store.status).where(Store.id == sid))
    assert status == "measuring"


async def test_values_are_updated_together(db: AsyncSession) -> None:
    sid = await _store(db)
    ok = await transition(
        db, Store, sid, from_={"collecting"}, to="archived", values={"archived_at": now_utc()}
    )
    assert ok
    await db.commit()
    row = await db.get(Store, sid)
    await db.refresh(row)
    assert row.status == "archived" and row.archived_at is not None


async def test_illegal_transition_raises(db: AsyncSession) -> None:
    sid = await _store(db)
    with pytest.raises(ValueError):
        await transition(db, Store, sid, from_={"diagnosed"}, to="measuring")


async def test_concurrent_transitions_only_one_wins(db: AsyncSession) -> None:
    sid = await _store(db)
    factory = session_factory()
    async with factory() as a, factory() as b:
        assert await transition(a, Store, sid, from_={"collecting"}, to="measuring") is True
        # a가 커밋하기 전이므로 b는 행 잠금에서 기다린다
        task = asyncio.create_task(transition(b, Store, sid, from_={"collecting"}, to="measure_failed"))
        await asyncio.sleep(0.5)
        assert not task.done()
        await a.commit()
        assert await asyncio.wait_for(task, timeout=5) is False
        await b.rollback()
    assert await db.scalar(select(Store.status).where(Store.id == sid)) == "measuring"
