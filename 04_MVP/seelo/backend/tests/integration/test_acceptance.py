"""명세서 10장 정상·실패 경계 22개(11 5장, W-11-1). 기존 W-ID 시험을 재사용한다."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from seelo.domain.metrics import ResponseView, compute_run_metrics
from seelo.domain.report_builder import assert_no_banned_terms
from seelo.models.fix import FixLog, FixRequest, RemeasureSchedule
from seelo.models.measurement import AiResponse, MeasurementRun
from seelo.models.ops import EmailLog
from seelo.models.report import ComparisonReport
from seelo.services import collect_service, measure_service, remeasure_service
from tests.integration import (
    test_w_01_2 as auth,
)
from tests.integration import (
    test_w_01_3 as oauth,
)
from tests.integration import (
    test_w_01_4 as sessions,
)
from tests.integration import (
    test_w_01_5 as reset,
)
from tests.integration import (
    test_w_01_6 as account,
)
from tests.integration import (
    test_w_02_3 as identify,
)
from tests.integration import (
    test_w_02_5 as stores,
)
from tests.integration import (
    test_w_03_2 as policy,
)
from tests.integration import (
    test_w_05_3 as finalize,
)
from tests.integration import (
    test_w_06_2 as diagnosis,
)
from tests.integration import (
    test_w_08_1 as requests,
)
from tests.integration import (
    test_w_09_4 as approve,
)
from tests.integration import (
    test_w_09_5 as apply,
)
from tests.map_world import measure_to_end
from tests.report_world import scheduled_world
from tests.support import NEW_PW, login, mail_secret, make_user, signup_verified
from tests.unit import test_fact_check as facts

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")
QUEUES = ["collect", "measure", "ai_openai", "ai_gemini", "plan", "fix", "report", "email"]


@pytest.fixture(autouse=True)
def _settings(settings_env, monkeypatch):
    settings_env(
        AI_REPEAT_COUNT="2",
        AUTO_FIX_ENABLED="true",
        KAKAO_FIX_ENABLED="true",
        ADMIN_NOTIFY_EMAILS="ops@seelo.test",
        OPENAI_MEASURE_MODEL="m-openai",
        GEMINI_MEASURE_MODEL="m-gemini",
        OPENAI_CHEAP_MODEL="m-cheap",
    )
    monkeypatch.setattr(measure_service, "BACKOFF_S", (0.0, 0.0))


async def drain(queue_app, db):
    """실제 Procrastinate 워커가 다음 작업까지 처리하게 한다(11 5.1)."""
    for _ in range(20):
        await queue_app.run_worker_async(queues=QUEUES, wait=False, install_signal_handlers=False)
        n = await db.scalar(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status IN ('todo','doing') AND queue_name=ANY(:q)"
            ),
            {"q": QUEUES},
        )
        if not n:
            return
    raise AssertionError("인수 테스트 작업이 끝나지 않음")


async def test_acceptance_normal_signup_to_report_and_password_reset(
    client, db, queue_app, make_client, fake_mailer, map_admin, settings_env
):
    settings_env(AI_REPEAT_COUNT="10")
    await signup_verified(client, db, "acceptance@seelo.test")
    r = await client.post(
        "/api/stores/identify", json={"name": "데모식당", "link": "https://kko.to/x", "mode": "new"}
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["runId"]
    await drain(queue_app, db)
    diag = (await client.get(f"/api/diagnosis/{run_id}")).json()
    assert len(diag["competitors"]) == 5 and len(diag["questions"]) == 3 and diag["findingsCount"] > 0
    assert await db.scalar(select(func.count()).select_from(AiResponse)) == 60
    r = await client.post("/api/fix/requests")
    assert r.status_code == 201, r.text
    request_id = r.json()["requestId"]
    admin_user = await make_user(db, "admin@seelo.test")
    admin_user.role = "admin"
    await db.commit()
    admin = await make_client()
    await login(admin, "admin@seelo.test")
    assert (await admin.post(f"/api/admin/fix-requests/{request_id}/approve")).status_code == 200
    assert (await client.post("/api/fix/connect/google/invited")).status_code == 200
    detail = (await admin.get(f"/api/admin/fix-requests/{request_id}")).json()
    conn_id = next(c["id"] for c in detail["connections"] if c["provider"] == "google")
    map_admin["google"].values["attributes"] = {"vegetarian": False}
    assert (await admin.post(f"/api/admin/connections/{conn_id}/verify")).status_code == 202
    await drain(queue_app, db)
    plans = (await client.get("/api/fix/plans")).json()["plans"]
    plan_id = next(p["planId"] for p in plans if p["provider"] == "google")
    plan = (await client.get(f"/api/fix/plans/{plan_id}")).json()
    items = []
    accepted = set()
    for item in plan["items"]:
        entry = {"itemId": item["itemId"], "excluded": item["needsOwnerInput"] or item["sensitive"]}
        if item["field"] == "attributes" and isinstance(item["proposedValue"], dict):
            entry.update(
                excluded=False, approvedValue={k: True for k in item["proposedValue"]}, ownerConfirmed=True
            )
        if not entry["excluded"]:
            accepted.add(item["field"])
        items.append(entry)
    assert accepted
    assert (await client.post(f"/api/fix/plans/{plan_id}/approve", json={"items": items})).status_code == 202
    await drain(queue_app, db)
    writes = [event[1] for event in map_admin["google"].events if event[0] == "write"]
    assert set(writes) == accepted and len(writes) == len(accepted)
    db.expire_all()
    logs = list(await db.scalars(select(FixLog).where(FixLog.fix_request_id == request_id)))
    assert all(lg.status == "applied" and lg.verified_at and lg.applied_at for lg in logs)
    assert next(lg for lg in logs if lg.field == "attributes").before_value == {"vegetarian": False}
    req = await db.get(FixRequest, request_id)
    schedule = await db.scalar(
        select(RemeasureSchedule).where(RemeasureSchedule.fix_request_id == request_id)
    )
    assert req.status == "remeasure_scheduled" and schedule.due_at - req.fix_completed_at == timedelta(
        days=14
    )
    base_qset = (await db.get(MeasurementRun, run_id)).question_set_id
    r = await admin.post(f"/api/admin/fix-requests/{request_id}/remeasure-now")
    assert r.status_code == 202, r.text
    after_id = r.json()["runId"]
    await drain(queue_app, db)
    report = (await client.get("/api/fix/report")).json()
    assert report["content"]["conditions"]["questionSetId"] == base_qset
    assert report["content"]["conditions"]["repeatCount"] == 10
    assert report["content"]["earlyRemeasure"] is True
    assert (await db.get(MeasurementRun, after_id)).question_set_id == base_qset
    assert_no_banned_terms(report["content"])
    assert len([e for e in map_admin["google"].events if e[0] == "write"]) == len(writes)
    assert (
        await client.post("/api/auth/password/forgot", json={"email": "acceptance@seelo.test"})
    ).status_code == 202
    token = (await mail_secret(db, "password_reset"))["token"]
    r = await client.post(
        "/api/auth/password/reset", json={"token": token, "password": NEW_PW, "passwordConfirm": NEW_PW}
    )
    assert r.status_code == 204, r.text
    assert (await login(client, "acceptance@seelo.test", NEW_PW)).status_code == 200
    await drain(queue_app, db)
    types = set(await db.scalars(select(EmailLog.type).where(EmailLog.status == "sent")))
    assert types >= {
        "verify_email",
        "diagnosis_result",
        "fix_requested",
        "fix_decided",
        "map_connection",
        "fix_plan_ready",
        "fix_completed",
        "report_ready",
        "password_reset",
    }
    # manual_required는 실패 18번, 전체 10종·소셜 변형은 W-10-2에서 함께 검증한다.
    assert fake_mailer.sent


async def test_acceptance_fail_01_signup_collision(client, fake_oauth, db):
    await oauth.test_email_account_blocks_google_and_kakao(client, fake_oauth, db)


async def test_acceptance_fail_02_expired_and_reused_links(client, db):
    await auth.test_token_reuse_and_expiry_are_410(client, db)
    # 재설정은 다른 계정으로 시험해 가입 시험의 세션·제한과 겹치지 않게 한다.
    await reset.test_reset_link_is_single_use_and_one_hour(client, db)


async def test_acceptance_fail_03_login_lock(client, db):
    await sessions.test_five_failures_lock_for_ten_minutes(client, db)


async def test_acceptance_fail_04_unsupported_link_and_category(client, db, maps):
    await identify.test_link_errors(client, db, "https://instagram.com/a", "UNSUPPORTED_LINK")
    maps.kakao.world = [
        {
            "id": "5",
            "place_name": "명동헤어",
            "category_group_code": "",
            "category_name": "미용 > 미용실",
            "x": "126.985",
            "y": "37.563",
        }
    ]
    r = await client.post(
        "/api/stores/identify",
        json={"name": "명동헤어", "link": "https://place.map.kakao.com/5", "mode": "new"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_TARGET_CATEGORY"


async def test_acceptance_fail_05_ambiguous_store(client, db, maps):
    await identify.test_google_candidates_and_select(client, db, maps)


async def test_acceptance_fail_06_failed_ai_is_not_nonappearance(db, ai):
    await finalize.test_failure_rate_over_30_percent_is_e5(db, ai)


def test_acceptance_fail_07_zero_rate_is_normal():
    rows = compute_run_metrics(
        [ResponseView(1, "openai", 1, True, [], [])], question_ids=[1], failed=0, total=1
    ).rows
    rate = next(
        r
        for r in rows
        if r.subject_type == "target"
        and r.provider == "openai"
        and r.question_id is None
        and r.metric_name == "appearance_rate"
    )
    assert rate.value == 0 and rate.denominator == 1


@pytest.mark.parametrize("mode", ["delete", "change"])
async def test_acceptance_fail_08_free_usage_persists(make_client, client, db, maps, mode):
    if mode == "delete":
        await account.test_delete_account_removes_everything_and_cancels_jobs(make_client, db)
    else:
        await stores.test_case_free_used_creates_no_run(client, db, maps)


async def test_acceptance_fail_09_other_users_ids(db, client, map_admin):
    from tests.integration.test_w_11_1 import assert_other_ids_denied

    await assert_other_ids_denied(db, client)


async def test_acceptance_fail_10_active_request_blocks_store_change(client, db, maps):
    await stores.test_case_active_request_blocks_change(client, db, maps, "remeasure_scheduled")


async def test_acceptance_fail_11_duplicate_request_and_rejected_retry(client, db):
    await requests.test_new_request_allowed_after_rejection(client, db)
    r = await client.post("/api/fix/requests")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_REQUESTED"


async def test_acceptance_fail_12_daily_retry_limit(client, db):
    await requests.test_retry_remeasure_e26(client, db)


async def test_acceptance_fail_13_free_response_omits_findings(client, db, ai):
    await diagnosis.test_response_has_count_only_and_metrics(client, db, ai)


async def test_acceptance_fail_14_map_data_policy(db, maps, web):
    await policy.test_kakao_naver_values_not_stored_nor_sent_to_llm(db, maps, web)


async def test_acceptance_fail_15_unsupported_facts_block_approval(client, db):
    for case in facts.CASES["cases"]:
        facts.test_wrong_20_all_caught(case)
    await approve.test_validation_order_and_nothing_saved(client, db)


def test_acceptance_fail_16_owner_only_fields_are_excluded():
    facts.test_dictionary_has_no_owner_only_fields()


async def test_acceptance_fail_17_concurrent_approval(make_client, db, settings_env):
    await approve.test_concurrent_approvals_one_wins(make_client, db, settings_env)


async def test_acceptance_fail_18_blocked_without_retry(db, map_admin):
    await apply.test_blocked_stops_without_retry(db, map_admin, "first_write")


async def test_acceptance_fail_19_revoked_stops_remaining_writes(db, map_admin):
    await apply.test_store_not_visible_revokes(db, map_admin)


async def test_acceptance_fail_20_no_writes_after_completion(db, map_admin):
    await apply.test_writes_approved_fields_and_reads_again(db, map_admin)


async def test_acceptance_fail_21_failed_remeasure_has_no_report(db, ai):
    w = await scheduled_world(db)
    run_id = (await remeasure_service.dispatch())[0]
    ai.openai.fail_next(100, "bad_request", only="web_answer")
    await collect_service.collect_store(w["store_id"], run_id)
    await measure_to_end(db, run_id)
    assert (await db.get(MeasurementRun, run_id)).question_set_id == w["question_set_id"]
    assert (await db.get(FixRequest, w["request_id"])).status == "remeasure_failed"
    assert await db.scalar(select(func.count()).select_from(ComparisonReport)) == 0


def test_acceptance_fail_22_report_has_no_guarantee():
    from seelo.domain.report_builder import build_report
    from tests.unit.test_report_builder import report_case

    for n in (1, 2, 3):
        _, args = report_case(n)
        assert_no_banned_terms(build_report(**args))
