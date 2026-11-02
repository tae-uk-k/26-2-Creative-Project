"""17 2장 카드 시드: API 표시·보존·중복·운영 차단. 외부 호출·작업 등록 없음."""

import asyncio

import pytest
from sqlalchemy import func, select

from scripts import demo_scenarios
from scripts.seed_demo import ACCOUNTS, DEMO_PASSWORD, main, seed_accounts
from seelo.models.fix import FixLog, FixRequest
from seelo.models.measurement import MeasurementRun
from seelo.models.ops import EmailLog, JobLink
from seelo.models.store import Store
from seelo.models.user import User
from seelo.security.passwords import hash_password, verify_password
from tests.support import PW, login

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


async def test_every_card_and_related_apis(db, client):
    assert await seed_accounts() == 17
    assert await demo_scenarios.seed_scenarios() == {"created": 15, "skipped": 0, "protected": 0}
    for email, role, expected in ACCOUNTS:
        if role == "admin":
            continue
        assert (await login(client, email, DEMO_PASSWORD)).status_code == 200
        response = await client.get("/api/home")
        assert response.status_code == 200, response.text
        home = response.json()
        assert home["card"] == expected.split("+")[0], email
        if expected == "measuring":
            assert (home["data"]["progressDone"], home["data"]["progressTotal"]) == (23, 60)
        if expected == "fixing+revoked":
            assert home["revokedProviders"] == ["google"]
        if expected == "fixing":
            assert home["manualInProgress"] is True
        if expected == "diagnosed":
            diag = (await client.get(f"/api/diagnosis/{home['data']['runId']}")).json()
            assert diag["findingsCount"] == 5 and len(diag["competitors"]) == 5
            assert diag["conditions"]["repeatCount"] == 10
            assert diag["providers"]["openai"]["rate"] == 0.3
            assert "findings" not in diag
        if expected == "free_used_store_changed":
            history = (await client.get("/api/stores/history")).json()
            assert home["hasHistory"] is True and history["stores"][0]["diagnosisRunId"]
            assert not await db.scalar(
                select(MeasurementRun.id).where(MeasurementRun.store_id == home["store"]["id"])
            )
        if expected == "plan_needs_approval":
            plan_id = home["data"]["planIds"][0]
            plan = (await client.get(f"/api/fix/plans/{plan_id}")).json()
            assert plan["readOnly"] is False and len(plan["items"]) == 3
            assert any(i["needsOwnerInput"] for i in plan["items"])
            assert any(i["sensitive"] for i in plan["items"])
            assert (await client.get(f"/api/fix/plans/{plan_id}/evidence")).status_code == 200
        if expected == "report_ready":
            report = await client.get("/api/fix/report")
            assert report.status_code == 200, report.text
            content = report.json()["content"]
            assert content["intervalDays"] == 14 and len(content["questions"]) == 3
            assert content["summary"]["providers"]["openai"]["rateDeltaPp"] == 20.0
    assert await db.scalar(select(func.count()).select_from(JobLink)) == 0
    assert await db.scalar(select(func.count()).select_from(EmailLog)) == 0
    admin_id = await db.scalar(select(User.id).where(User.email == "admin@seelo.test"))
    for log in await db.scalars(select(FixLog).where(FixLog.status == "manual_done")):
        assert log.handled_by == admin_id
        request = await db.get(FixRequest, log.fix_request_id)
        assert log.handled_at == request.fix_completed_at


async def test_existing_data_and_non_demo_account_are_preserved(db):
    await seed_accounts()
    protected = await db.scalar(select(User).where(User.email == "failed@seelo.test"))
    protected.password_hash = hash_password(PW)
    protected_id = protected.id
    owner = await db.scalar(select(User).where(User.email == "waiting@seelo.test"))
    existing = Store(
        owner_id=owner.id,
        name="보존할 가게",
        input_url="https://place.map.kakao.com/1",
        input_provider="kakao",
        category="restaurant",
        status="collected",
    )
    db.add(existing)
    await db.flush()
    existing_id = existing.id
    await db.commit()
    result = await demo_scenarios.seed_scenarios()
    assert result == {"created": 13, "skipped": 1, "protected": 1}
    counts = await db.scalar(select(func.count()).select_from(Store))
    assert await demo_scenarios.seed_scenarios() == {"created": 0, "skipped": 14, "protected": 1}
    db.expire_all()
    assert (await db.get(Store, existing_id)).name == "보존할 가게"
    assert verify_password((await db.get(User, protected_id)).password_hash, PW)
    assert await db.scalar(select(func.count()).select_from(Store)) == counts


async def test_concurrent_seed_only_creates_each_scenario_once(db):
    await seed_accounts()
    results = await asyncio.gather(demo_scenarios.seed_scenarios(), demo_scenarios.seed_scenarios())
    assert sum(r["created"] for r in results) == 15
    assert await db.scalar(select(func.count()).select_from(Store).where(Store.archived_at.is_(None))) == 15
    assert await db.scalar(select(func.count()).select_from(FixLog)) == 6


async def test_concurrent_account_creation_preserves_existing_accounts(db):
    results = await asyncio.gather(seed_accounts(), seed_accounts())
    assert sum(results) == 17
    assert await db.scalar(select(func.count()).select_from(User)) == 17
    from seelo.models.user import AuthIdentity

    assert await db.scalar(select(func.count()).select_from(AuthIdentity)) == 17
    assert await seed_accounts() == 0


async def test_failed_scenario_rolls_back_new_rows(db, monkeypatch):
    await seed_accounts()
    original = demo_scenarios._scenario

    async def fail_after_insert(s, owner, card):
        await original(s, owner, card)
        raise RuntimeError("demo_fixture_failure")

    monkeypatch.setattr(demo_scenarios, "_scenario", fail_after_insert)
    with pytest.raises(RuntimeError, match="demo_fixture_failure"):
        await demo_scenarios.seed_scenarios()
    assert await db.scalar(select(func.count()).select_from(Store)) == 0
    assert await db.scalar(select(func.count()).select_from(MeasurementRun)) == 0
    assert await db.scalar(select(func.count()).select_from(User)) == 17


@pytest.mark.parametrize("mode", ["prod", "real"])
async def test_seed_rejects_production_or_real_externals(db, settings_env, mode, capsys):
    settings_env(
        APP_ENV="prod" if mode == "prod" else "test",
        FAKE_EXTERNALS="false",
        COOKIE_SECURE="true",
        APP_BASE_URL="https://localhost",
    )
    with pytest.raises(ValueError, match="demo_scenarios_require"):
        await demo_scenarios.seed_scenarios()
    assert await main(False, scenarios=True) == 1
    assert await db.scalar(select(func.count()).select_from(User)) == 0
    assert DEMO_PASSWORD not in capsys.readouterr().out
