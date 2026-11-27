"""상품 목록의 진행 요약. 화면이 상품마다 다음 할 일을 고르는 데 쓰는 값이다."""

import pytest
from sqlalchemy import select

from seelo.config import get_settings
from seelo.models.commerce import CommerceMeasureRun, CommerceMeasureSet
from tests.integration.test_commerce import approve, plan, world

pytestmark = pytest.mark.usefixtures("fake_mailer")


async def summary(client, w):
    response = await client.get(f"/api/commerce/shops/{w.shop_id}/products")
    assert response.status_code == 200, response.text
    return response.json()["products"][0]["summary"]


async def test_product_list_summary_follows_plan_and_measurement(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    first = await summary(client, w)
    assert first["planId"] is None and first["planStatus"] is None
    assert first["questions"] == 0 and first["published"] is False and first["prepare"] is None
    assert first["measure"] == {"runs": 0, "latestStatus": None, "baseline": False, "followUp": False}

    p = await plan(client, w, fields=["description"])
    drafted = await summary(client, w)
    assert drafted["planId"] == p["id"] and drafted["planStatus"] == "draft"

    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.status_code == 200, response.text
    applied = await summary(client, w)
    assert applied["planStatus"] == "applied" and applied["published"] is False

    # 정비 전 기준 회차(정비안 없음)와 정비 후 회차가 모두 끝나야 보고서를 만들 수 있다.
    measure_set = CommerceMeasureSet(
        product_id=w.product["id"], name="기본", common_suffix="", queries=[], targets={}
    )
    db.add(measure_set)
    await db.flush()
    condition = {"provider": "openai", "model": "m", "toolOptions": "web", "repeats": 1}
    db.add(
        CommerceMeasureRun(
            set_id=measure_set.id,
            product_id=w.product["id"],
            label="B0",
            status="completed",
            condition=condition,
            snapshot_hash=w.product["snapshotHash"],
        )
    )
    await db.commit()
    baseline = await summary(client, w)
    assert baseline["measure"]["baseline"] is True and baseline["measure"]["followUp"] is False
    db.add(
        CommerceMeasureRun(
            set_id=measure_set.id,
            product_id=w.product["id"],
            label="P1",
            status="running",
            condition=condition,
            snapshot_hash=w.product["snapshotHash"],
            plan_id=p["id"],
        )
    )
    await db.commit()
    running = await summary(client, w)
    # 아직 끝나지 않은 정비 후 회차는 보고서 근거로 세지 않는다.
    assert running["measure"]["runs"] == 2 and running["measure"]["latestStatus"] == "running"
    assert running["measure"]["followUp"] is False

    # 조건이 다른 정비 후 회차는 기준 회차와 비교할 수 없다.
    db.add(
        CommerceMeasureRun(
            set_id=measure_set.id,
            product_id=w.product["id"],
            label="P2",
            status="completed",
            condition={**condition, "repeats": 3},
            snapshot_hash=w.product["snapshotHash"],
            plan_id=p["id"],
        )
    )
    await db.commit()
    other = await summary(client, w)
    assert other["measure"]["followUp"] is False

    follow_up = await db.scalar(select(CommerceMeasureRun).where(CommerceMeasureRun.label == "P1"))
    follow_up.status = "completed"
    await db.commit()
    ready = await summary(client, w)
    assert ready["measure"]["baseline"] is True and ready["measure"]["followUp"] is True
