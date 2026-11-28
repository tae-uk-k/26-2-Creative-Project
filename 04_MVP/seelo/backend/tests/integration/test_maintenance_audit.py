"""2단계: 정리 작업(cleanupUnverified)·감사 기록·주기 작업 등록."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from seelo.models.ops import AuditLog
from seelo.models.user import AuthToken, RateLimit, User
from seelo.models.user import Session as SessionRow
from seelo.security.sessions import create_session
from seelo.security.tokens import hash_token, new_token
from seelo.services import audit
from seelo.services.maintenance import cleanup_unverified
from seelo.timeutil import now_utc


async def test_cleanup_unverified(db: AsyncSession) -> None:
    now = now_utc()
    old = User(email="old@seelo.test", created_at=now - timedelta(hours=25))
    fresh = User(email="fresh@seelo.test", created_at=now - timedelta(hours=1))
    verified = User(
        email="ok@seelo.test", email_verified_at=now, terms_agreed_at=now, created_at=now - timedelta(days=3)
    )
    db.add_all([old, fresh, verified])
    await db.flush()
    live = await create_session(db, verified, Response())
    expired = await create_session(db, verified, Response())
    expired.expires_at = now - timedelta(seconds=1)
    db.add_all(
        [
            RateLimit(key="signup:203.0.113.5", window_start=now - timedelta(hours=2), count=3),
            RateLimit(key="signup:203.0.113.6", window_start=now, count=1),
            AuthToken(
                user_id=verified.id,
                type="verify",
                token_hash=hash_token(new_token()),
                expires_at=now - timedelta(days=8),
            ),
            AuthToken(
                user_id=verified.id,
                type="reset",
                token_hash=hash_token(new_token()),
                expires_at=now + timedelta(hours=1),
            ),
        ]
    )
    await db.flush()
    live_id = live.id
    await db.commit()

    counts = await cleanup_unverified(db, now)
    await db.commit()
    assert counts == {
        "users": 1,
        "sessions": 1,
        "pending_signups": 0,
        "identify_sessions": 0,
        "rate_limits": 1,
        "auth_links": 1,
    }
    emails = set((await db.scalars(select(User.email))).all())
    assert emails == {"fresh@seelo.test", "ok@seelo.test"}
    assert (await db.scalars(select(SessionRow.id))).all() == [live_id]


async def test_audit_record(db: AsyncSession) -> None:
    row = audit.record(
        db,
        actor_id=None,
        action="fix_request.reject",
        target_type="fix_request",
        target_id=3,
        detail={"reason": "x"},
    )
    await db.commit()
    saved = await db.get(AuditLog, row.id)
    assert saved is not None and saved.action == "fix_request.reject" and saved.detail == {"reason": "x"}
    with pytest.raises(ValueError):
        audit.record(db, actor_id=None, action="not_an_action", target_type="x")


def test_periodic_tasks_registered() -> None:
    import seelo.worker.periodic  # noqa: F401
    import seelo.worker.tasks_email  # noqa: F401
    from seelo.worker.app import app

    names = {t.task.name for t in app.periodic_registry.periodic_tasks.values()}
    assert "cleanupUnverified" in names
    assert {"sendEmail", "cleanupUnverified"} <= set(app.tasks)
