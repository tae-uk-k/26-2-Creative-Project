"""W-12-4 현재·지난 보고서의 소유권과 완료 상태(04 7.4)."""

import pytest
from sqlalchemy import select, text

from seelo.models.report import ComparisonReport
from seelo.services import remeasure_service, report_service
from tests.report_world import completed_remeasure
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


async def test_current_not_ready_and_other_report_is_hidden(db, client):
    await make_user(db, "other@seelo.test")
    await login(client, "other@seelo.test")
    r = await client.get("/api/fix/report")
    assert r.status_code == 404 and r.json()["error"]["code"] == "REPORT_NOT_READY"
    w = await completed_remeasure(db)
    await remeasure_service.compare_fix_values(w["request_id"], w["after_id"])
    rid = await db.scalar(select(ComparisonReport.id))
    assert (await client.get(f"/api/reports/{rid}")).status_code == 404
    await report_service.generate(rid)
    r = await client.get(f"/api/reports/{rid}")
    assert r.status_code == 404 and "Seelo cafe" not in r.text
    await login(client, "owner@seelo.test")
    r = await client.get("/api/fix/report")
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"reportId", "fixRequestId", "version", "createdAt", "content"}
    assert (await client.get(f"/api/reports/{rid}")).json() == r.json()
    await db.execute(
        text("UPDATE stores SET status='archived', archived_at=now() WHERE id=:id"), {"id": w["store_id"]}
    )
    await db.commit()
    assert (await client.get("/api/fix/report")).status_code == 404
    assert (await client.get(f"/api/reports/{rid}")).status_code == 200
    admin = await make_user(db, "admin@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, "admin@seelo.test")
    assert (await client.get(f"/api/reports/{rid}")).status_code == 200
