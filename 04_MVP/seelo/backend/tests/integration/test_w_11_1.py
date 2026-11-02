"""W-11-1 다른 사용자의 모든 ID 경로·민감 정보 로그(05 11·12장)."""

import re

import pytest
from sqlalchemy import select

from seelo.models.fix import MapConnection
from seelo.models.report import ComparisonReport
from seelo.services import remeasure_service, report_service
from tests.report_world import completed_remeasure
from tests.support import capture_all_logs, login, make_user, signup

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


async def assert_other_ids_denied(db, client):
    """OpenAPI의 정수 ID 경로를 전부 대조해 새 경로가 빠지면 실패시킨다(11 4장)."""
    from seelo.main import app

    w = await completed_remeasure(db)
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    report_id = await db.scalar(select(ComparisonReport.id))
    await report_service.generate(report_id)
    connection_id = await db.scalar(select(MapConnection.id).limit(1))
    ids = {
        "run_id": w["run_id"],
        "plan_id": w["plan_id"],
        "report_id": report_id,
        "request_id": w["request_id"],
        "fix_log_id": next(iter(w["logs"].values())),
        "connection_id": connection_id,
    }
    bodies = {
        "/api/fix/plans/{plan_id}/approve": {"items": []},
        "/api/admin/fix-requests/{request_id}/reject": {"reason": "검사"},
        "/api/admin/connections/{connection_id}/verify": {"manualResult": "connected"},
        "/api/admin/fix-logs/{fix_log_id}/manual-done": {},
    }
    await make_user(db, "other@seelo.test")
    await login(client, "other@seelo.test")
    seen = []
    for path, methods in app.openapi()["paths"].items():
        integer_ids = re.findall(r"\{(\w+_id)\}", path)
        assert set(integer_ids) <= ids.keys(), ("미검증 ID 경로", path)
        if not integer_ids:
            continue
        url = path.format(**ids)
        for method in methods:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            kwargs = {"json": bodies.get(path, {})} if method != "get" else {}
            r = await client.request(method, url, **kwargs)
            assert r.status_code in {403, 404}, (method, path, r.status_code, r.text)
            assert not any(
                value in r.text for value in ("명동교자", "owner@seelo.test", "Seelo cafe", "02-123-4567")
            )
            seen.append((method, path))
    # 저장소에 있는 모든 ID 경로가 최소한 한 번 검증됐는지 확인한다.
    assert len(seen) >= 14
    r = await client.post("/api/stores/current/not-mine", json={"runId": w["run_id"]})
    assert r.status_code == 404
    for path in ("/api/home", "/api/stores/current", "/api/stores/history", "/api/fix/plans"):
        r = await client.get(path)
        assert "명동교자" not in r.text and "Seelo cafe" not in r.text


async def test_all_id_paths_deny_other_owner(db, client, settings_env):
    settings_env(AUTO_FIX_ENABLED="false")
    await assert_other_ids_denied(db, client)


async def test_sensitive_inputs_and_query_are_absent_from_raw_logs(client, db):
    email = "private-log-check@seelo.test"
    password = "PrivateLogPassword8"
    query = "PRIVATE-OAUTH-CODE"
    with capture_all_logs() as entries:
        r = await signup(client, email, password)
        assert r.status_code == 201
        await client.get(f"/api/oauth/google/callback?code={query}&state=PRIVATE-STATE")
        await client.post("/api/auth/login", json={"email": email, "password": "WrongPrivatePassword9"})
    text = str(entries)
    for private in (email, password, query, "PRIVATE-STATE", "WrongPrivatePassword9"):
        assert private not in text


async def test_secret_and_password_absent_from_db_and_logs(make_client, db, fake_mailer):
    from tests.integration.test_w_01_2 import test_no_plaintext_token_or_password_in_db_or_logs

    await test_no_plaintext_token_or_password_in_db_or_logs(make_client, db, fake_mailer)


async def test_kakao_field_values_stay_in_fix_logs_only(db, map_admin, settings_env):
    from sqlalchemy import text

    from seelo.models.fix import FixLog
    from seelo.models.user import User
    from tests.map_world import approved_plan

    settings_env(AUTO_FIX_ENABLED="true", KAKAO_FIX_ENABLED="true")
    w = await completed_remeasure(db)
    plan = await approved_plan(db, w, "kakao", {"intro": "KAKAO-APPROVED-PRIVATE"}, status="manual_done")
    lg = await db.get(FixLog, plan["logs"]["intro"])
    lg.before_value = "KAKAO-BEFORE-PRIVATE"
    await db.execute(
        text("UPDATE fix_requests SET status='remeasuring' WHERE id=:id"), {"id": w["request_id"]}
    )
    await db.commit()
    map_admin["kakao"].values["intro"] = "KAKAO-APPROVED-PRIVATE"
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    report_id = await db.scalar(select(ComparisonReport.id))
    await report_service.generate(report_id)
    db.expire_all()
    report = await db.get(ComparisonReport, report_id)
    assert report.status == "completed"
    assert "KAKAO-" not in str(report.content)
    owner = await db.get(User, w["owner_id"])
    response = await report_service.get(db, owner, report_id)
    change = next(c for c in response.content.changes if c.provider == "kakao")
    assert change.before_value == "KAKAO-BEFORE-PRIVATE"
    assert change.applied_value == "KAKAO-APPROVED-PRIVATE" and change.remeasure_match == "match"
    assert "KAKAO-" not in str(report.content)
