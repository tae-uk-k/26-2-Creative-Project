"""M1(12 8단계): 가짜 연동으로 가입 → 인증 → 가게 등록 → (실제 작업 큐) 수집·질문·AI 호출·추출·마무리
→ 진단 결과·홈 카드·결과 메일까지 한 테스트로.

외부 연동은 가짜 모드 기본 묶음(데모 지도·데모 웹사이트·가짜 LLM)이고, 작업은 Procrastinate 워커가 실제 PG에서
실행한다(run_worker_async, wait=False: 쌓인 작업을 다 처리하면 돌아온다).
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import seelo.worker.tasks_collect  # noqa: F401  작업 등록
import seelo.worker.tasks_email  # noqa: F401
import seelo.worker.tasks_measure  # noqa: F401
from tests.support import signup_verified

QUEUES = ["collect", "measure", "ai_openai", "ai_gemini", "email"]
EMAIL = "m1@seelo.test"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(AI_REPEAT_COUNT="2")


async def _run_jobs(queue_app: Any, db: AsyncSession, run_id: int) -> str:
    """측정이 끝날 때까지 워커를 돌린다(작업이 다음 작업을 등록하므로 여러 번)."""
    status = ""
    for _ in range(10):
        await queue_app.run_worker_async(queues=QUEUES, wait=False, install_signal_handlers=False)
        status = await db.scalar(text("SELECT status FROM measurement_runs WHERE id = :i"), {"i": run_id})
        todo = await db.scalar(
            text("SELECT count(*) FROM procrastinate_jobs WHERE status = 'todo' AND queue_name = ANY(:q)"),
            {"q": QUEUES},
        )
        if status in ("completed", "failed") and not todo:
            break
    return status


async def test_signup_to_diagnosis(
    client: httpx.AsyncClient, db: AsyncSession, queue_app: Any, fake_mailer: Any
) -> None:
    await signup_verified(client, db, EMAIL)
    home = (await client.get("/api/home")).json()
    assert home["card"] == "no_store"

    r = await client.post(
        "/api/stores/identify", json={"name": "데모식당", "link": "https://kko.to/x", "mode": "new"}
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["runId"]
    assert r.json()["next"] == f"/runs/{run_id}"
    assert (await client.get("/api/home")).json()["card"] == "measuring"

    assert await _run_jobs(queue_app, db, run_id) == "completed"
    progress = (await client.get(f"/api/runs/{run_id}/progress")).json()
    assert (progress["status"], progress["stage"], progress["next"]) == (
        "completed",
        "done",
        f"/diagnosis/{run_id}",
    )
    assert (progress["progressDone"], progress["progressTotal"]) == (12, 12)

    diag = (await client.get(f"/api/diagnosis/{run_id}")).json()
    assert diag["storeName"] == "데모식당"
    assert diag["providers"]["openai"]["rate"] == 0.5 and diag["providers"]["gemini"]["rate"] == 0.5
    assert len(diag["competitors"]) == 5 and len(diag["questions"]) == 3
    assert diag["findingsCount"] >= 1  # 데모 Google에 채식 정보가 없음

    home = (await client.get("/api/home")).json()
    assert home["card"] == "diagnosed" and home["data"]["runId"] == run_id
    assert home["data"]["findingsCount"] == diag["findingsCount"]

    subjects = [m["subject"] for m in fake_mailer.sent if m["to"] == [EMAIL]]
    assert "[seelo] 무료 진단 결과가 나왔어요" in subjects
    used = await db.scalar(text("SELECT count(*) FROM free_usage_ledger"))
    assert used == 1
