"""W-01-6 계정 설정·탈퇴(05 8·9장, 11 4장)."""

from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.measurement import MeasurementRun
from seelo.models.ops import AuditLog
from seelo.models.store import Store
from seelo.models.user import FreeUsageLedger, User
from seelo.models.user import Session as SessionRow
from seelo.security.tokens import email_hmac
from seelo.services import jobs
from seelo.services.eligibility import has_used_free
from seelo.worker.tasks_email import send_email
from tests.support import NEW_PW, PW, login, make_user, signup_verified

FK_TO_USERS = text(
    """
    SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass
    ORDER BY 1, 2
    """
)


def _change(current: str, new: str = NEW_PW, confirm: str | None = None) -> dict[str, str]:
    return {"currentPassword": current, "newPassword": new, "newPasswordConfirm": confirm or new}


async def test_account_info(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "a@seelo.test")
    await login(client, "a@seelo.test")
    r = await client.get("/api/account")
    body = r.json()
    assert r.status_code == 200 and body["email"] == "a@seelo.test"
    assert body["provider"] == "email" and body["canChangePassword"] is True and body["createdAt"]


async def test_change_password(make_client: Any, db: AsyncSession) -> None:
    await make_user(db, "p@seelo.test")
    here, there = await make_client(), await make_client()
    await login(here, "p@seelo.test")
    await login(there, "p@seelo.test")

    r = await here.post("/api/account/password", json=_change("wrongpass1"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "WRONG_PASSWORD"
    db.expire_all()
    assert (await db.scalar(select(User.failed_login_count))) == 0  # 잠금 횟수는 올리지 않는다
    r = await here.post("/api/account/password", json=_change(PW, confirm="other1234"))
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"] == {"newPasswordConfirm": "password_mismatch"}
    r = await here.post("/api/account/password", json=_change(PW, "weak"))
    assert r.json()["error"]["details"]["fields"] == {"newPassword": "weak_password"}

    r = await here.post("/api/account/password", json=_change(PW))
    assert r.status_code == 204
    assert (await here.get("/api/auth/me")).status_code == 200  # 지금 세션은 남는다
    assert (await there.get("/api/auth/me")).status_code == 401  # 다른 세션은 끊긴다
    assert await db.scalar(select(func.count()).select_from(SessionRow)) == 1
    assert (await login(there, "p@seelo.test", NEW_PW)).status_code == 200


async def test_social_account_cannot_change_password(client: httpx.AsyncClient, db: AsyncSession) -> None:
    from seelo.security.sessions import create_session

    user = await make_user(db, "k@seelo.test", password=None, provider="kakao", provider_user_id="k-1")
    # 소셜 계정은 비밀번호 로그인이 없으니 세션을 직접 만든다
    from starlette.responses import Response

    resp = Response()
    await create_session(db, user, resp)
    await db.commit()
    for h in resp.headers.getlist("set-cookie"):
        name, _, rest = h.partition("=")
        client.cookies.set(name, rest.split(";", 1)[0], domain="test.local")
    assert (await client.get("/api/account")).json()["canChangePassword"] is False
    r = await client.post("/api/account/password", json=_change("whatever1"))
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "PASSWORD_LOGIN_UNAVAILABLE",
        "message": "카카오로 가입한 계정은 비밀번호를 바꿀 수 없어요",
        "details": {"provider": "kakao"},
    }


async def _store_with_free_run(db: AsyncSession, owner_id: int) -> int:
    store = Store(
        owner_id=owner_id,
        name="데모식당",
        input_url="https://maps.app.goo.gl/x",
        input_provider="google",
        category="restaurant",
        status="diagnosed",
    )
    db.add(store)
    await db.flush()
    db.add(
        MeasurementRun(
            store_id=store.id, kind="diagnosis", is_free=True, trigger="initial", status="completed"
        )
    )
    await db.flush()
    return store.id


async def test_delete_account_removes_everything_and_cancels_jobs(make_client: Any, db: AsyncSession) -> None:
    c = await make_client()
    me = await signup_verified(c, db, "bye@seelo.test")
    user_id = me["id"]
    store_id = await _store_with_free_run(db, user_id)
    job_a = await jobs.defer(
        db, send_email, args={"email_log_id": 1}, links=jobs.JobLinks(store_id=store_id), queueing_lock="a"
    )
    job_b = await jobs.defer(
        db, send_email, args={"email_log_id": 2}, links=jobs.JobLinks(store_id=store_id), queueing_lock="b"
    )
    await db.commit()
    # 다른 사용자 데이터는 남아야 한다
    other_id = (await make_user(db, "stay@seelo.test")).id

    r = await c.request("DELETE", "/api/account", json={"confirmText": "탈퇴할게요"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CONFIRM_TEXT_MISMATCH"

    r = await c.request("DELETE", "/api/account", json={"confirmText": "탈퇴합니다"})
    assert r.status_code == 204
    assert "seelo_session" not in c.cookies
    assert (await c.get("/api/auth/me")).status_code == 401

    # 사용자를 가리키는 모든 외래 키 열에 그 사용자 ID가 0개(free_usage_ledger는 외래 키가 없다)
    db.expire_all()
    fks = (await db.execute(FK_TO_USERS)).all()
    assert len(fks) >= 10
    for tbl, col in fks:
        n = await db.scalar(text(f"SELECT count(*) FROM {tbl} WHERE {col} = :u"), {"u": user_id})
        assert n == 0, f"{tbl}.{col}"
    assert await db.scalar(select(func.count()).select_from(Store)) == 0
    assert await db.scalar(select(func.count()).select_from(User).where(User.id == other_id)) == 1

    # 작업 취소 요청이 job_links의 작업마다 갔다
    status = dict((await db.execute(text("SELECT id, status FROM procrastinate_jobs"))).all())
    assert status[job_a] == "cancelled" and status[job_b] == "cancelled"

    # 감사 기록: 행위자 NULL, 개인정보 없음
    audit = await db.scalar(select(AuditLog).where(AuditLog.action == "account.delete"))
    assert audit.actor_id is None and audit.target_id == user_id and audit.detail == {}
    # 무료 진단 기록이 남아 같은 이메일로 다시 가입해도 무료를 쓴 것으로 본다
    assert await db.scalar(select(FreeUsageLedger.email_hash)) == email_hmac("bye@seelo.test")
    c2 = await make_client()
    me2 = await signup_verified(c2, db, "bye@seelo.test")
    assert me2["id"] != user_id
    assert await has_used_free(db, "bye@seelo.test") is True
    assert await has_used_free(db, "stay@seelo.test") is False


async def test_delete_without_free_use_leaves_no_ledger(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, "nofree@seelo.test")
    await login(client, "nofree@seelo.test")
    r = await client.request("DELETE", "/api/account", json={"confirmText": "탈퇴합니다"})
    assert r.status_code == 204
    assert await db.scalar(select(func.count()).select_from(FreeUsageLedger)) == 0
