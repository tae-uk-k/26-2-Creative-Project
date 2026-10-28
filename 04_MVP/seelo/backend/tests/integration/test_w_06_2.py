"""W-06-2 무료 진단 결과 GET /api/diagnosis/{runId}(04 6장).

응답 JSON 키를 재귀로 모아 고쳐야 할 점 내용 키(findings·title·evidence…)가 없고 findingsCount만 있는지,
남의 측정·끝나지 않은 측정·재측정은 404인지, 지표가 화면 형식(rate 4자리·avgRank 1자리)으로 오는지.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.finding import Finding
from seelo.models.measurement import Question
from tests.map_world import g_detail, measure_to_end, seed_google_snapshot, seed_measuring
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")
BANNED_KEYS = {"findings", "title", "titleKey", "evidence", "category", "field", "priority"}


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        AI_REPEAT_COUNT="2", OPENAI_MEASURE_MODEL="m", GEMINI_MEASURE_MODEL="m", OPENAI_CHEAP_MODEL="c"
    )


def _keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


async def _diagnosed(db: AsyncSession, email: str = "owner@seelo.test") -> tuple[int, int]:
    store_id, run_id, _ = await seed_measuring(db, name="데모식당", email=email)
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "데모식당"))
    await measure_to_end(db, run_id)
    return store_id, run_id


async def test_response_has_count_only_and_metrics(
    client: httpx.AsyncClient, db: AsyncSession, ai: Any
) -> None:
    store_id, run_id = await _diagnosed(db)
    q3 = await db.scalar(select(Question.id).where(Question.order_no == 3))
    await db.execute(  # 질문 3의 Gemini 답변을 하나도 못 읽었다고 치면 그 칸은 "측정하지 못함"(null)
        text(
            "UPDATE metrics SET value = 0 WHERE run_id = :r AND question_id = :q AND provider = 'gemini' "
            "AND metric_name = 'success_count'"
        ),
        {"r": run_id, "q": q3},
    )
    await db.commit()
    await login(client, "owner@seelo.test")
    r = await client.get(f"/api/diagnosis/{run_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert not (_keys(body) & BANNED_KEYS)  # 고쳐야 할 점 내용은 응답에 없다
    count = await db.scalar(select(func.count()).select_from(Finding).where(Finding.run_id == run_id))
    assert body["findingsCount"] == count and count > 0
    assert (body["runId"], body["storeId"], body["storeName"]) == (run_id, store_id, "데모식당")
    rate = {"successCount": 6, "appearanceCount": 3, "rate": 0.5, "avgRank": 2.0}
    assert body["providers"] == {"openai": rate, "gemini": rate} == body["target"]["providers"]
    assert body["target"]["name"] == "데모식당"
    assert [c["rankOrder"] for c in body["competitors"]] == [1, 2, 3, 4, 5]
    assert body["competitors"][0]["name"] == "명동칼국수"
    assert body["competitors"][0]["providers"]["openai"] == {
        "successCount": 6, "appearanceCount": 6, "rate": 1.0, "avgRank": 1.0,
    }  # fmt: skip
    qs = body["questions"]
    assert [q["orderNo"] for q in qs] == [1, 2, 3] and qs[0]["lang"] == "en"
    assert qs[0]["providers"]["openai"] == {"appearanceCount": 1, "successCount": 2}
    assert qs[2]["providers"]["gemini"] is None
    assert body["sources"]["top"] == [  # 가짜 답변은 세 출처를 모두 인용 → 같으면 도메인 이름순
        {"domain": d, "count": 12} for d in ("google.com", "korean.visitkorea.or.kr", "tripadvisor.com")
    ]
    assert body["sources"]["targetSources"] == [{"domain": "korean.visitkorea.or.kr", "count": 6}]
    cond = body["conditions"]
    assert (cond["questionCount"], cond["repeatCount"], cond["providers"]) == (3, 2, ["openai", "gemini"])
    assert cond["measuredAt"] == body["measuredAt"] and body["measuredAt"].endswith("Z")


async def test_other_owner_gets_404_and_admin_can_view(
    client: httpx.AsyncClient, db: AsyncSession, ai: Any
) -> None:
    _, run_id = await _diagnosed(db)
    await make_user(db, "other@seelo.test")
    admin = await make_user(db, "admin@seelo.test")
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": admin.id})
    await db.commit()
    await login(client, "other@seelo.test")
    r = await client.get(f"/api/diagnosis/{run_id}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert "데모식당" not in r.text
    await login(client, "admin@seelo.test")
    assert (await client.get(f"/api/diagnosis/{run_id}")).status_code == 200


async def test_only_completed_diagnosis(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    _, run_id, _ = await seed_measuring(db, name="데모식당")
    await login(client, "owner@seelo.test")
    assert (await client.get(f"/api/diagnosis/{run_id}")).status_code == 404  # 아직 running
    await db.execute(
        text(
            "UPDATE measurement_runs SET status = 'completed', kind = 'remeasure', is_free = false "
            "WHERE id = :i"
        ),
        {"i": run_id},
    )
    await db.commit()
    assert (await client.get(f"/api/diagnosis/{run_id}")).status_code == 404  # 재측정은 보고서로
    assert (await client.get("/api/diagnosis/999999")).status_code == 404


async def test_login_required(api: httpx.AsyncClient) -> None:
    r = await api.get("/api/diagnosis/1")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"
