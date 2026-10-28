"""W-09-2 정비안 만들기(09 6장, 03 E13·E14·E23).

지금 값 읽기(수동 모드는 읽지 않음·자동 모드는 관리 화면), 칸별 바꿀 값(사실만),
finding 없는 칸은 만들지 않음,
이름·주소는 칸 대신 안내, 글 사실 검사·글자 수, 생성 실패 재시도 1번 뒤 generation_failed, 관리자 다시 생성.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.finding import Finding
from seelo.models.fix import FixPlan, FixPlanItem, FixRequest, MapConnection
from seelo.models.ops import AuditLog, EmailLog
from seelo.schemas.llm import PlanTextsOut, SentenceRefOut
from seelo.services import connection_service, fix_plan_service
from tests.map_world import PLAN_SITE, new_plan, seed_plan_world
from tests.support import login, make_user

pytestmark = pytest.mark.usefixtures("queue_app")


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(ADMIN_NOTIFY_EMAILS="ops@seelo.test", OPENAI_PLAN_MODEL="m-plan")


async def _items(db: AsyncSession, plan_id: int) -> dict[str, FixPlanItem]:
    db.expire_all()
    rows = await db.scalars(
        select(FixPlanItem).where(FixPlanItem.fix_plan_id == plan_id).order_by(FixPlanItem.order_no)
    )
    return {i.field: i for i in rows}


async def _plan(db: AsyncSession, plan_id: int) -> FixPlan:
    db.expire_all()
    return await db.get(FixPlan, plan_id)


async def _jobs(db: AsyncSession, name: str) -> list[tuple[Any, str, str | None]]:
    rows = await db.execute(
        text("SELECT args, queue_name, lock FROM procrastinate_jobs WHERE task_name = :n ORDER BY id"),
        {"n": name},
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _plan_calls(ai: Any) -> list[dict[str, Any]]:
    return [c for c in ai.openai.calls if c.get("schema") == "PlanTextsOut"]


# --- 수동 모드(AUTO_FIX_ENABLED=false, 기본) ---------------------------------------------------


async def test_manual_mode_read_queue_and_null_values(db: AsyncSession, ai: Any) -> None:
    w = await seed_plan_world(db)
    req = await db.get(FixRequest, w["request_id"])
    plan_id = await connection_service.maybe_create_plan(db, req, "google")
    await db.commit()
    # 읽지 않는 모드는 브라우저가 필요 없어 plan 큐(기본 워커), lock 없음
    assert await _jobs(db, "readCurrentValues") == [({"fix_plan_id": plan_id}, "plan", None)]
    await fix_plan_service.read_current_values(plan_id)
    items = await _items(db, plan_id)
    assert set(items) == {"description", "regular_hours", "website", "phone", "menu", "attributes"}
    assert all(i.current_value is None for i in items.values())
    assert await _jobs(db, "generateFixPlan") == [({"fix_plan_id": plan_id}, "plan", None)]


async def test_generate_items_from_facts_and_findings(db: AsyncSession, ai: Any) -> None:
    w = await seed_plan_world(db)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    await fix_plan_service.generate(plan_id)
    plan = await _plan(db, plan_id)
    assert (plan.status, plan.generation_attempts) == ("awaiting_approval", 1)
    items = await _items(db, plan_id)
    # 근거(finding)가 있는 칸만, finding 우선순위 순. 이름 다름은 칸 대신 안내(09 4장)
    assert list(items) == ["website", "attributes", "phone", "menu"]
    assert [i.order_no for i in items.values()] == [1, 2, 3, 4]
    assert items["website"].proposed_value == "https://demo.example/"
    assert items["attributes"].proposed_value == {"vegetarian": None, "card_payment": None}
    assert items["attributes"].needs_owner_input is True
    assert items["phone"].proposed_value == "02-776-0000"
    assert items["phone"].reason == "공식 웹사이트와 Google 지도의 전화번호가 달라요"
    menu = items["menu"].proposed_value
    assert [(m["name"], m["price"], m["nameEn"]) for m in menu] == [
        ("칼국수", 11000, "House dish A"),
        ("만두", 10000, "House dish B"),
    ]
    finding_ids = {f.title_key: f.id for f in await db.scalars(select(Finding))}
    assert items["menu"].finding_ids == [finding_ids["condition_missing.budget"]]
    assert items["phone"].evidence["factIds"] and "responseIds" in items["phone"].evidence
    # 글 LLM에는 사실만(카카오·네이버 값 없음), 한 번 호출
    (call,) = _plan_calls(ai)
    assert call["model"] == "m-plan" and "02-776-0000" in call["prompt"] and "칼국수" in call["prompt"]
    mail = await db.scalar(select(EmailLog).where(EmailLog.type == "fix_plan_ready"))
    assert mail.template_params == {"plan_id": plan_id, "provider": "google", "item_count": 4}


async def test_kakao_plan_empty_in_manual_mode(db: AsyncSession, ai: Any) -> None:
    """수동 모드는 카카오 지금 값을 읽지 않아 정비안 단계 판정(08 6.5)을 건너뛴다.

    → 근거 없는 칸은 만들지 않으므로 칸이 없다.
    """
    w = await seed_plan_world(db)
    plan_id = await new_plan(db, w["request_id"], "kakao", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    await fix_plan_service.generate(plan_id)
    assert (await _plan(db, plan_id)).status == "awaiting_approval"
    assert await _items(db, plan_id) == {}
    assert _plan_calls(ai) == []


async def test_failure_retried_once_then_failed(db: AsyncSession, ai: Any) -> None:
    w = await seed_plan_world(db)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    ai.openai.fail_next(2, "api_error", only="PlanTextsOut")
    await fix_plan_service.generate(plan_id)
    plan = await _plan(db, plan_id)
    assert (plan.status, plan.generation_attempts) == ("generating", 1)  # 1번째 실패: 다시 등록
    await fix_plan_service.generate(plan_id)
    plan = await _plan(db, plan_id)
    assert (plan.status, plan.last_error, plan.generation_attempts) == ("generation_failed", "api_error", 2)
    assert (
        await db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.type == "fix_plan_ready"))
        == 0
    )


async def test_long_description_rewritten_once_then_trimmed(db: AsyncSession, ai: Any) -> None:
    findings = [("google", "description", "map_missing", "map_missing.description", 1, {})]
    w = await seed_plan_world(db, findings=findings)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    sentence = "This is a cozy neighborhood noodle place loved by locals and visitors alike in the area."
    ai.openai.results["PlanTextsOut"] = PlanTextsOut(
        google_description=[SentenceRefOut(text=sentence, fact_ids=[]) for _ in range(12)],
        kakao_intro=None,
        menu_texts=[],
        kakao_tags=[],
    )
    await fix_plan_service.generate(plan_id)
    assert len(_plan_calls(ai)) == 2  # 제한을 넘어 짧게 1번 더
    assert "shorter" in _plan_calls(ai)[1]["prompt"]
    desc = (await _items(db, plan_id))["description"].proposed_value
    assert len(desc) <= 750 and desc.endswith(".")  # 문장 단위로 줄임


async def test_text_fact_check_applied(db: AsyncSession, ai: Any) -> None:
    findings = [("google", "description", "map_missing", "map_missing.description", 1, {})]
    w = await seed_plan_world(db, findings=findings)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    ai.openai.results["PlanTextsOut"] = PlanTextsOut(
        google_description=[
            SentenceRefOut(text="Handmade noodles since 1966.", fact_ids=[]),
            SentenceRefOut(text="Call 02-776-0000 to book.", fact_ids=[]),
            SentenceRefOut(text="All dishes are halal.", fact_ids=[]),
            SentenceRefOut(text="Takeout available.", fact_ids=[]),  # Google 스냅샷 포장 참
        ],
        kakao_intro=None,
        menu_texts=[],
        kakao_tags=[],
    )
    await fix_plan_service.generate(plan_id)
    item = (await _items(db, plan_id))["description"]
    assert item.proposed_value == "Handmade noodles since [ ]. Takeout available."
    assert item.needs_owner_input is True


# --- 자동 모드(관리 화면을 읽음) ---------------------------------------------------------------


async def test_auto_mode_reads_values_and_adds_plan_findings(
    db: AsyncSession, ai: Any, map_admin: Any, settings_env: Any
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    w = await seed_plan_world(db, findings=[])
    map_admin["google"].values = {"description": "", "menu": [], "phone": "02-776-5348", "attributes": {}}
    req = await db.get(FixRequest, w["request_id"])
    plan_id = await connection_service.maybe_create_plan(db, req, "google")
    await db.commit()
    assert await _jobs(db, "readCurrentValues") == [({"fix_plan_id": plan_id}, "fix", "fix:google")]
    await fix_plan_service.read_current_values(plan_id)
    items = await _items(db, plan_id)
    assert items["phone"].current_value == "02-776-5348" and items["regular_hours"].current_value is None
    await fix_plan_service.generate(plan_id)
    plan_findings = (await db.scalars(select(Finding).where(Finding.stage == "plan"))).all()
    desc_finding = next(f.id for f in plan_findings if f.field == "description")  # expire_all 전에 읽어 둔다
    assert {(f.title_key, f.fix_plan_id, f.run_id) for f in plan_findings} == {
        ("map_missing.description", plan_id, w["run_id"]),
        ("map_missing.menu", plan_id, w["run_id"]),
    }
    items = await _items(db, plan_id)
    assert set(items) == {"description", "menu"}
    assert "Myeong" not in items["description"].proposed_value  # 가짜 LLM은 사실(지역·업종)만 씀
    assert items["description"].finding_ids == [desc_finding]


async def test_auto_mode_kakao_values_not_in_findings(
    db: AsyncSession, ai: Any, map_admin: Any, settings_env: Any
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    w = await seed_plan_world(db, findings=[])
    map_admin["kakao"].values = {
        "intro": "",
        "hours": None,
        "price_items": [],
        "links": [],
        "services": [],
        "tags": ["카카오만있는태그"],
    }
    plan_id = await new_plan(db, w["request_id"], "kakao", w["run_id"])
    await fix_plan_service.read_current_values(plan_id)
    await fix_plan_service.generate(plan_id)
    items = await _items(db, plan_id)
    assert set(items) == {"intro", "hours", "price_items", "links", "services"}  # 태그는 있어 판정 안 함
    assert items["links"].proposed_value == ["https://demo.example/"]
    assert items["services"].proposed_value == ["포장"]  # Google 스냅샷 포장 참 → 카카오 키워드
    assert [m["featured"] for m in items["price_items"].proposed_value] == [True, True]
    evidence = str([f.evidence for f in await db.scalars(select(Finding))])
    assert "카카오만있는태그" not in evidence  # 카카오 지금 값은 current_value로만
    assert items["hours"].proposed_value == PLAN_SITE["hours"]


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        (lambda a: a.block_on("open"), "automation_blocked"),
        (lambda a: a.transient_on("read", 2), "read_failed"),
        (lambda a: a.not_visible(), "store_not_visible"),
    ],
)
async def test_read_errors(
    db: AsyncSession, ai: Any, map_admin: Any, settings_env: Any, setup: Any, error: str
) -> None:
    settings_env(AUTO_FIX_ENABLED="true")
    w = await seed_plan_world(db)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    setup(map_admin["google"])
    await fix_plan_service.read_current_values(plan_id)
    plan = await _plan(db, plan_id)
    assert (plan.status, plan.last_error) == ("generation_failed", error)
    conn = await db.get(MapConnection, w["connections"]["google"])
    assert conn.status == (
        "revoked" if error == "store_not_visible" else "connected"
    )  # 안 보이면 권한 회수(E18)


async def test_skip_when_not_generating_or_not_connected(db: AsyncSession, ai: Any) -> None:
    w = await seed_plan_world(db)
    plan_id = await new_plan(db, w["request_id"], "google", w["run_id"])
    await db.execute(
        text("UPDATE map_connections SET status = 'revoked' WHERE id = :i"), {"i": w["connections"]["google"]}
    )
    await db.commit()
    await fix_plan_service.read_current_values(plan_id)
    assert await _items(db, plan_id) == {} and (await _plan(db, plan_id)).status == "generating"


# --- E23 관리자 다시 생성 --------------------------------------------------------------------


async def test_admin_regenerate(client: httpx.AsyncClient, db: AsyncSession, ai: Any) -> None:
    admin = await make_user(db, "admin@seelo.test")
    await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :i"), {"i": admin.id})
    w = await seed_plan_world(db)
    with_items = await new_plan(db, w["request_id"], "google", w["run_id"])
    await fix_plan_service.read_current_values(with_items)
    no_items = await new_plan(db, w["request_id"], "kakao", w["run_id"])
    await db.execute(
        text("UPDATE fix_plans SET status = 'generation_failed', generation_attempts = 2, last_error = 'x'")
    )
    await db.commit()
    await login(client, "owner@seelo.test")
    assert (await client.post(f"/api/admin/fix-plans/{with_items}/regenerate")).status_code == 403
    await login(client, "admin@seelo.test")
    for pid in (with_items, no_items):
        r = await client.post(f"/api/admin/fix-plans/{pid}/regenerate")
        assert r.status_code == 202 and r.json() == {}
        plan = await _plan(db, pid)
        assert (plan.status, plan.generation_attempts, plan.last_error) == ("generating", 0, None)
    assert [a for a, *_ in await _jobs(db, "generateFixPlan")][-1] == {"fix_plan_id": with_items}
    assert [a for a, *_ in await _jobs(db, "readCurrentValues")][-1] == {
        "fix_plan_id": no_items
    }  # 칸이 없으면 읽기부터
    assert (
        await db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "fix_plan.regenerate")
        )
        == 2
    )
    r = await client.post(f"/api/admin/fix-plans/{with_items}/regenerate")
    assert r.status_code == 409  # generation_failed만
    assert (await client.post("/api/admin/fix-plans/999/regenerate")).status_code == 404
