"""1단계: DB 스키마 확인(02, 11 4장 "공통").

- ORM 모델과 마이그레이션으로 만든 DB가 같다(Alembic compare_metadata).
- 상태 Enum 값 == DDL CHECK 값.
- 금지된 INSERT(카카오 스냅샷, 이름·주소 정비 칸, 보관 안 된 가게 2곳, 진행 중 신청 2건)가 DB에서 막힌다.
- 사용자 삭제가 CASCADE로 가게 아래를 모두 지운다.
"""

import re
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.domain.states import CHECK_ENUMS
from seelo.models import Base, FixPlan, FixPlanItem, FixRequest, MeasurementRun, Store, StoreSource, User


def _include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    return not (type_ == "table" and name and name.startswith("procrastinate_"))


async def test_models_match_database(db: AsyncSession) -> None:
    conn = await db.connection()

    def _diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn, opts={"include_object": _include_object})
        return compare_metadata(ctx, Base.metadata)

    diff = await conn.run_sync(_diff)
    assert diff == [], "\n".join(map(str, diff))


_ANY_RE = re.compile(r"\(?\(?(\w+)\)? = ANY \(\(?ARRAY\[(.*?)\]")
_EQ_RE = re.compile(r"^CHECK \(\((\w+) = '([^']*)'::text\)\)$")


async def _db_check_values(db: AsyncSession) -> dict[tuple[str, str], set[str]]:
    rows = await db.execute(
        text(
            "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
        )
    )
    out: dict[tuple[str, str], set[str]] = {}
    for table, definition in rows:
        if table.startswith("procrastinate_"):
            continue
        m = _ANY_RE.search(definition)
        if m and "NOT" not in definition[: m.start()]:
            out[(table, m.group(1))] = set(re.findall(r"'([^']*)'::text", m.group(2)))
            continue
        m = _EQ_RE.match(definition)
        if m:
            out[(table, m.group(1))] = {m.group(2)}
    return out


async def test_enum_values_match_check_constraints(db: AsyncSession) -> None:
    in_db = await _db_check_values(db)
    for key, enum in CHECK_ENUMS.items():
        assert key in in_db, f"DB에 {key} 값 목록 CHECK가 없음"
        assert {e.value for e in enum} == in_db[key], key
    assert set(in_db) == set(CHECK_ENUMS), f"Enum이 없는 CHECK: {set(in_db) - set(CHECK_ENUMS)}"


async def _owner_store(db: AsyncSession, email: str = "o@seelo.test") -> tuple[User, Store]:
    user = User(email=email)
    db.add(user)
    await db.flush()
    store = Store(
        owner_id=user.id,
        name="데모식당",
        input_url="https://place.map.kakao.com/1",
        input_provider="kakao",
        category="restaurant",
        status="collecting",
    )
    db.add(store)
    await db.flush()
    return user, store


async def test_kakao_and_naver_snapshots_are_rejected(db: AsyncSession) -> None:
    _, store = await _owner_store(db)
    src = StoreSource(store_id=store.id, provider="kakao", external_id="1", match_status="found")
    db.add(src)
    await db.flush()
    src_id, store_id = src.id, store.id  # rollback 뒤에는 객체가 만료되므로 ID를 미리 꺼내 둔다
    await db.commit()
    for provider in ("kakao", "naver"):
        with pytest.raises(IntegrityError):
            await db.execute(
                text(
                    "INSERT INTO source_snapshots (source_id, store_id, provider, status, expires_at) "
                    "VALUES (:s, :st, :p, 'ok', now())"
                ),
                {"s": src_id, "st": store_id, "p": provider},
            )
        await db.rollback()
    # 허용된 provider는 들어간다
    await db.execute(
        text(
            "INSERT INTO source_snapshots (source_id, store_id, provider, status, expires_at) "
            "VALUES (:s, :st, 'google', 'ok', now())"
        ),
        {"s": src_id, "st": store_id},
    )


async def test_forbidden_fix_plan_item_fields_are_rejected(db: AsyncSession) -> None:
    user, store = await _owner_store(db)
    req = FixRequest(user_id=user.id, store_id=store.id, status="connecting")
    db.add(req)
    await db.flush()
    plan = FixPlan(fix_request_id=req.id, provider="google", version=1, status="generating")
    db.add(plan)
    await db.flush()
    plan_id = plan.id
    await db.commit()
    for field in ("name", "address", "category", "listing"):
        db.add(FixPlanItem(fix_plan_id=plan_id, order_no=1, field=field))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
    db.add(FixPlanItem(fix_plan_id=plan_id, order_no=1, field="description"))
    await db.flush()


async def test_only_one_active_store_per_owner(db: AsyncSession) -> None:
    user, store = await _owner_store(db)
    user_id, store_id = user.id, store.id
    await db.commit()
    db.add(
        Store(
            owner_id=user_id,
            name="두번째",
            input_url="u",
            input_provider="google",
            category="cafe",
            status="collecting",
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
    # 기존 가게를 보관하면 새 가게를 만들 수 있다
    await db.execute(
        text("UPDATE stores SET status = 'archived', archived_at = now() WHERE id = :id"), {"id": store_id}
    )
    db.add(
        Store(
            owner_id=user_id,
            name="두번째",
            input_url="u",
            input_provider="google",
            category="cafe",
            status="collecting",
        )
    )
    await db.flush()


async def test_only_one_non_rejected_request_per_store(db: AsyncSession) -> None:
    user, store = await _owner_store(db)
    db.add(FixRequest(user_id=user.id, store_id=store.id, status="rejected", reject_reason="사유"))
    db.add(FixRequest(user_id=user.id, store_id=store.id, status="requested"))
    await db.flush()
    await db.commit()
    db.add(FixRequest(user_id=user.id, store_id=store.id, status="requested"))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_rejected_request_needs_reason(db: AsyncSession) -> None:
    user, store = await _owner_store(db)
    db.add(FixRequest(user_id=user.id, store_id=store.id, status="rejected"))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_updated_at_trigger(db: AsyncSession) -> None:
    _, store = await _owner_store(db)
    await db.commit()
    before = (
        await db.execute(text("SELECT updated_at FROM stores WHERE id = :id"), {"id": store.id})
    ).scalar()
    await db.execute(text("SELECT pg_sleep(0.01)"))
    await db.execute(text("UPDATE stores SET name = '바뀜' WHERE id = :id"), {"id": store.id})
    await db.commit()
    after = (
        await db.execute(text("SELECT updated_at FROM stores WHERE id = :id"), {"id": store.id})
    ).scalar()
    assert after > before


async def test_deleting_user_cascades(db: AsyncSession) -> None:
    user, store = await _owner_store(db)
    run = MeasurementRun(
        store_id=store.id, kind="diagnosis", trigger="initial", status="queued", is_free=True
    )
    db.add(run)
    await db.flush()
    req = FixRequest(user_id=user.id, store_id=store.id, status="requested", base_run_id=run.id)
    db.add(req)
    await db.flush()
    run.fix_request_id = req.id
    await db.flush()
    await db.execute(text("INSERT INTO free_usage_ledger (email_hash) VALUES ('h')"))
    await db.commit()

    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    await db.commit()
    for table in ("stores", "measurement_runs", "fix_requests"):
        n = (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
        assert n == 0, table
    assert (await db.execute(text("SELECT count(*) FROM free_usage_ledger"))).scalar() == 1
