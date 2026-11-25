"""쇼핑몰 실제 PostgreSQL 통합 시험. 외부 상품·메일·AI는 시험 대역을 쓴다."""

import asyncio
import copy
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from seelo.config import get_settings
from seelo.integrations import commerce as provider
from seelo.models.commerce import CommercePlan, CommerceProduct, CommerceShop, CommerceWrite
from seelo.schemas.commerce import FactOrder
from seelo.security.crypto import encrypt_json
from seelo.timeutil import now_utc
from tests.support import login, make_user, signup_verified

pytestmark = pytest.mark.usefixtures("fake_mailer")


async def world(client, db, monkeypatch, *, api=True, platform="cafe24"):
    monkeypatch.setattr(get_settings(), "commerce_edit_mode", "api")
    user = await signup_verified(client, db, "commerce-owner@seelo.test")
    response = await client.post(
        "/api/commerce/shops",
        json={
            "platform": platform,
            "externalId": "demo",
            "name": "시험몰",
        },
    )
    assert response.status_code == 201, response.text
    shop_id = response.json()["id"]
    state = {
        "product": {
            "product_no": 123,
            "product_name": "시험 셔츠",
            "model_name": "A-100",
            "description": '<img src="https://cdn.example.com/original.jpg">',
            "mobile_description": "",
            "summary_description": "",
            "simple_description": "",
            "price": "10000",
            "selling": "F",
            "display": "T",
        },
        "seo": {},
    }
    counter = {"writes": 0, "reads": 0, "timeout": False, "reflect": True, "fail_readback": False}

    async def fetch(self, product_no):
        counter["reads"] += 1
        if counter["fail_readback"] and counter["writes"]:
            raise provider.CommerceApiError("transport_or_response_error")
        return copy.deepcopy(state)

    async def write(self, product_no, fresh, changes):
        counter["writes"] += 1
        if counter["reflect"]:
            for key, value in changes.items():
                target, field = (
                    (state["seo"], key.split(".")[1]) if key.startswith("seo.") else (state["product"], key)
                )
                target[field] = value
        if counter["timeout"]:
            raise provider.CommerceApiError("transport_or_response_error", uncertain=True)

    monkeypatch.setattr(provider.ProductApi, "fetch", fetch)
    monkeypatch.setattr(provider.ProductApi, "write", write)
    if api:
        shop = await db.get(CommerceShop, shop_id)
        shop.api_status = "authorized"
        shop.credentials = encrypt_json(
            {"access_token": "never-show-private-token", "refresh_token": "refresh"}
        )
        shop.access_expires_at = now_utc() + timedelta(hours=1)
        await db.commit()
        response = await client.post(
            f"/api/commerce/shops/{shop_id}/products/import", json={"externalId": "123"}
        )
    else:
        response = await client.post(
            f"/api/commerce/shops/{shop_id}/products/manual-snapshot",
            json={
                "externalId": "123",
                "name": "시험 셔츠",
                "identity": "시험 셔츠 | A-100",
                "fields": {"description": state["product"]["description"]},
            },
        )
    assert response.status_code == 201, response.text
    product = response.json()
    response = await client.post(
        f"/api/commerce/products/{product['id']}/facts",
        json={
            "facts": [
                {
                    "key": "material",
                    "value": "면 100%",
                    "identity": product["identity"],
                    "sourceUrl": "https://maker.example.com/a100",
                    "quote": "이 상품의 소재: 면 100%",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    return SimpleNamespace(user=user, shop_id=shop_id, product=product, state=state, counter=counter)


async def plan(client, w, **kwargs):
    response = await client.post(
        f"/api/commerce/products/{w.product['id']}/plans", json={"useAi": False, **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_browser_delegation_import_apply_and_rollback_without_api(client, db, monkeypatch):
    from seelo.integrations.browser import commerce as browser

    w = await world(client, db, monkeypatch, api=False)
    monkeypatch.setattr(get_settings(), "commerce_edit_mode", "browser")
    monkeypatch.setattr(get_settings(), "commerce_browser_runner", "inline")
    adapter = provider.ProductApi("cafe24", "demo", 1, "")
    adapter.source = "browser"
    monkeypatch.setattr(browser, "BrowserProduct", lambda *args, **kwargs: adapter)
    endpoint = f"/api/commerce/shops/{w.shop_id}/products/import"
    denied = await client.post(endpoint, json={"externalId": "123"})
    assert denied.status_code != 201
    shop = await db.get(CommerceShop, w.shop_id)
    shop.manager_status = "verified"
    await db.commit()
    response = await client.post(endpoint, json={"externalId": "123"})
    assert response.status_code == 201, response.text
    assert response.json()["snapshotSource"] == "browser"
    p = await plan(client, w, fields=["description"])
    assert p["changes"][0]["method"] == "browser"
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).json()["status"] == "applied"
    assert (await client.post(f"/api/commerce/plans/{p['id']}/rollback")).json()["status"] == "rolled_back"
    await db.refresh(shop)
    assert shop.api_status == "not_connected" and shop.credentials is None
    assert w.counter["writes"] == 2 and w.state["product"]["price"] == "10000"


async def browser_world(client, db, monkeypatch, runner="inline"):
    from seelo.integrations.browser import commerce as browser

    w = await world(client, db, monkeypatch, api=False)
    monkeypatch.setattr(get_settings(), "commerce_edit_mode", "browser")
    monkeypatch.setattr(get_settings(), "commerce_browser_runner", runner)
    adapter = provider.ProductApi("cafe24", "demo", 1, "")
    adapter.source = "browser"
    monkeypatch.setattr(browser, "BrowserProduct", lambda *args, **kwargs: adapter)
    w.adapter = adapter
    shop = await db.get(CommerceShop, w.shop_id)
    shop.manager_status = "verified"
    await db.commit()
    if runner == "inline":
        response = await client.post(
            f"/api/commerce/shops/{w.shop_id}/products/import", json={"externalId": "123"}
        )
        assert response.status_code == 201, response.text
        w.product = response.json()
    return w


async def test_browser_mode_rejects_field_runner_cannot_write(client, db, monkeypatch):
    w = await browser_world(client, db, monkeypatch)
    support = w.product["fieldSupport"]
    assert support["mode"] == "browser" and "mobile_description" not in support["automatic"]
    shop_view = (await client.get(f"/api/commerce/shops/{w.shop_id}")).json()
    assert shop_view["fieldSupport"]["automatic"] == support["automatic"]
    before = await db.scalar(select(func.count()).select_from(CommercePlan))
    response = await client.post(
        f"/api/commerce/products/{w.product['id']}/plans",
        json={"useAi": False, "fields": ["description", "mobile_description"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {
        "reason": "field_not_supported",
        "fields": ["mobile_description"],
        "mode": "browser",
    }
    assert await db.scalar(select(func.count()).select_from(CommercePlan)) == before
    # 수정 전에 만든 옛 정비안도 승인·저장하지 않는다.
    p = await plan(client, w, fields=["description"])
    row = await db.get(CommercePlan, p["id"])
    row.changes = [
        *row.changes,
        {**row.changes[0], "field": "mobile_description", "before": "", "method": "api"},
    ]
    await db.commit()
    response = await client.post(
        f"/api/commerce/plans/{p['id']}/approve",
        json={"snapshotHash": p["snapshotHash"], "fields": ["description", "mobile_description"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"] == ["mobile_description"]
    assert w.counter["writes"] == 0


async def test_store_url_registration_and_imported_product_search(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    response = await client.post(
        "/api/commerce/shops", json={"storeUrl": "https://smartstore.naver.com/seelo/products/13892740658"}
    )
    assert response.status_code == 201, response.text
    expected = {"platform": "smartstore", "externalId": "seelo", "shopNo": 1, "name": "seelo"}
    assert expected.items() <= response.json().items()
    response = await client.post(
        "/api/commerce/shops",
        json={
            "storeUrl": "https://other01.cafe24.com/disp/admin/shop2/product/ProductManage",
            "name": "두번째",
        },
    )
    assert response.status_code == 201 and response.json()["shopNo"] == 2
    mismatch = await client.post(
        "/api/commerce/shops",
        json={"storeUrl": "https://other02.cafe24.com/", "platform": "smartstore"},
    )
    assert mismatch.status_code == 422
    custom = await client.post("/api/commerce/shops", json={"storeUrl": "https://www.mybrand.co.kr/"})
    assert custom.json()["error"]["details"]["reason"] == "custom_domain_requires_mall_id"
    # 카페24 상품 주소는 같은 몰일 때만 상품번호로 바꾼다.
    other = await client.post(
        f"/api/commerce/shops/{w.shop_id}/products/import",
        json={"productUrl": "https://another.cafe24.com/product/detail.html?product_no=123"},
    )
    assert other.json()["error"]["details"]["reason"] == "product_url_other_shop"
    same = await client.post(
        f"/api/commerce/shops/{w.shop_id}/products/import",
        json={"productUrl": "https://demo.cafe24.com/product/detail.html?product_no=123"},
    )
    assert same.status_code == 201 and same.json()["externalId"] == "123"
    for number in range(124, 149):
        db.add(
            CommerceProduct(
                shop_id=w.shop_id,
                external_id=str(number),
                name=f"검색 대상 {number}" if number % 2 else f"다른 상품 {number}",
                identity=f"ID-{number}",
                snapshot={"fields": {"description": ""}, "raw": {}},
                snapshot_hash="0" * 64,
                snapshot_source="api",
                facts=[],
                asked_fields=[],
            )
        )
    await db.commit()
    page = (await client.get(f"/api/commerce/shops/{w.shop_id}/products?query=검색&pageSize=5&page=2")).json()
    assert page["total"] == 12 and page["page"] == 2 and len(page["products"]) == 5
    assert page["scope"] == "imported"
    assert all("검색" in item["name"] for item in page["products"])
    literal = (await client.get(f"/api/commerce/shops/{w.shop_id}/products?query=%25")).json()
    assert literal["total"] == 0


async def approve(client, p):
    response = await client.post(
        f"/api/commerce/plans/{p['id']}/approve", json={"snapshotHash": p["snapshotHash"]}
    )
    assert response.status_code == 200, response.text


async def test_full_flow_readback_publication_and_rollback(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    original = w.state["product"]["description"]
    p = await plan(client, w, fields=["description", "summary_description", "seo.meta_description"])
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied" and response.json()["publication"] == {}
    assert w.state["product"]["description"].startswith(original)
    assert w.state["product"]["price"] == "10000" and w.state["product"]["selling"] == "F"
    again = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert again.status_code == 409 and w.counter["writes"] == 1
    logs = (await client.get(f"/api/commerce/plans/{p['id']}/writes")).json()["writes"]
    assert logs[0]["before"]["description"] == original and logs[0]["status"] == "applied"
    assert "never-show-private-token" not in str(logs)
    response = await client.post(f"/api/commerce/plans/{p['id']}/rollback")
    assert response.status_code == 200 and response.json()["status"] == "rolled_back"
    assert w.state["product"]["description"] == original
    assert w.state["seo"]["meta_description"] == ""


async def test_invitation_is_not_api_authentication(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False)
    response = await client.post(f"/api/commerce/shops/{w.shop_id}/manager", json={"status": "invited"})
    assert response.json()["managerStatus"] == "invited"
    assert response.json()["apiStatus"] == "not_connected"
    assert (
        await client.post(f"/api/commerce/shops/{w.shop_id}/manager", json={"status": "verified"})
    ).status_code == 403
    assert (
        await client.post(f"/api/commerce/shops/{w.shop_id}/products/import", json={"externalId": "123"})
    ).status_code == 409
    assert "credentials" not in response.json()


async def test_default_writes_off_and_owner_controls_approval(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).status_code == 409
    await approve(client, p)
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.status_code == 409 and response.json()["error"]["code"] == "COMMERCE_WRITES_DISABLED"
    assert w.counter["writes"] == 0


async def test_concurrent_approval_and_sending_are_single_use(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    replies = await asyncio.gather(
        *[
            client.post(f"/api/commerce/plans/{p['id']}/approve", json={"snapshotHash": p["snapshotHash"]})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in replies) == [200, 409]
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    replies = await asyncio.gather(*[client.post(f"/api/commerce/plans/{p['id']}/apply") for _ in range(2)])
    assert sorted(r.status_code for r in replies) == [200, 409]
    assert w.counter["writes"] == 1


async def test_changed_product_cannot_be_overwritten(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    w.state["product"]["price"] = "12000"
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.status_code == 409 and w.counter["writes"] == 0
    assert (await client.get(f"/api/commerce/plans/{p['id']}")).json()["status"] == "conflict"


async def test_timeout_reconciliation_never_resends(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    w.counter["timeout"] = True
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.json()["status"] == "uncertain"
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).status_code == 409
    response = await client.post(f"/api/commerce/plans/{p['id']}/verify")
    assert response.json()["status"] == "applied" and w.counter["writes"] == 1


async def test_accepted_but_not_reflected_is_pending(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    w.counter["reflect"] = False
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.json()["status"] == "pending_reflection"
    assert (await client.post(f"/api/commerce/plans/{p['id']}/verify")).json()[
        "status"
    ] == "pending_reflection"
    assert w.counter["writes"] == 1


async def test_failed_readback_does_not_repeat_write(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    w.counter["fail_readback"] = True
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).json()["status"] == "uncertain"
    assert w.counter["writes"] == 1


async def test_question_budget_and_deferred_facts_do_not_block_ready_changes(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False)
    p = await plan(client, w, requiredFacts=["size", "power", "components", "care"])
    assert len(p["questions"]) == 2 and "fact:care" in p["deferred"]
    response = await client.post(
        f"/api/commerce/products/{w.product['id']}/answers", json={"answers": {"size": "10cm"}}
    )
    assert response.status_code == 200
    again = await plan(client, w, requiredFacts=["weight", "components", "power"])
    assert [q["field"] for q in again["questions"]] == ["power", "weight"]
    assert (
        await client.post(
            f"/api/commerce/products/{w.product['id']}/answers", json={"answers": {"care": "손세탁"}}
        )
    ).status_code == 422
    await approve(client, p)  # 보류한 새 사실이 남아 있어도 근거 있는 변경은 승인한다.


async def test_no_facts_is_not_completed_work(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    row = await db.get(CommerceProduct, w.product["id"])
    row.facts = []
    await db.commit()
    p = await plan(client, w, requiredFacts=["size"])
    assert p["status"] == "no_changes" and p["changes"] == []
    assert (
        await client.post(f"/api/commerce/plans/{p['id']}/approve", json={"snapshotHash": p["snapshotHash"]})
    ).status_code == 409
    assert await db.scalar(select(func.count()).select_from(CommerceWrite)) == 0


async def test_smartstore_editor_and_manual_permission_are_explicit(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False, platform="smartstore")
    p = await plan(client, w)
    await approve(client, p)
    response = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert response.json()["status"] == "manual_required" and w.counter["writes"] == 0
    instructions = await client.get(f"/api/commerce/plans/{p['id']}/instructions")
    assert instructions.json()["changes"][0]["before"] == w.product["fields"]["description"]
    admin = await make_user(db, "commerce-admin@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, admin.email)
    values = {c["field"]: c["proposed"] for c in p["changes"]}
    url = f"/api/commerce/plans/{p['id']}/manual-result"
    assert (await client.post(url, json={"values": values, "note": "저장 후 조회"})).status_code == 409
    await client.post(f"/api/commerce/shops/{w.shop_id}/manager", json={"status": "verified"})
    response = await client.post(url, json={"values": values, "note": "저장 후 조회"})
    assert response.json()["status"] == "manual_recorded" and response.json()["publication"] == {}
    shop = (await client.get(f"/api/commerce/shops/{w.shop_id}")).json()
    assert shop["apiStatus"] == "not_connected" and shop["writeVerifiedAt"] is None


async def test_other_owner_cannot_read_or_change_shop_product_plan(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await make_user(db, "commerce-other@seelo.test")
    await login(client, "commerce-other@seelo.test")
    paths = [f"shops/{w.shop_id}", f"products/{w.product['id']}", f"plans/{p['id']}"]
    for path in paths:
        response = await client.get("/api/commerce/" + path)
        assert response.status_code == 404 and "시험 셔츠" not in response.text
    response = await client.post(
        f"/api/commerce/plans/{p['id']}/approve", json={"snapshotHash": p["snapshotHash"]}
    )
    assert response.status_code == 404


async def test_cafe24_oauth_state_single_use_scopes_and_encrypted_storage(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "cafe24_client_id", "app")
    monkeypatch.setattr(settings, "cafe24_client_secret", SecretStr("private-secret"))

    async def token(mall_id, **kwargs):
        return {
            "access_token": "private-access-token",
            "refresh_token": "private-refresh-token",
            "mall_id": mall_id,
            "scopes": ["mall.read_product", "mall.write_product"],
            "expires_at": (now_utc() + timedelta(hours=2)).isoformat(),
        }

    monkeypatch.setattr(provider, "cafe_token", token)
    start = (await client.post(f"/api/commerce/shops/{w.shop_id}/cafe24/authorize")).json()
    query = parse_qs(urlsplit(start["authorizationUrl"]).query)
    assert query["scope"] == ["mall.read_product,mall.write_product"]
    state = query["state"][0]
    response = await client.get(
        "/api/commerce/cafe24/callback", params={"state": state, "code": "private-code"}
    )
    assert response.status_code == 200 and response.json()["apiStatus"] == "authorized"
    assert "private-" not in response.text
    row = await db.get(CommerceShop, w.shop_id, populate_existing=True)
    assert b"private-access-token" not in row.credentials and row.oauth_state_hash is None
    assert (
        await client.get("/api/commerce/cafe24/callback", params={"state": state, "code": "code"})
    ).status_code == 400
    await client.post(f"/api/commerce/shops/{w.shop_id}/disconnect")
    row = await db.get(CommerceShop, w.shop_id, populate_existing=True)
    assert row.credentials is None and row.api_status == "revoked"
    start = (await client.post(f"/api/commerce/shops/{w.shop_id}/cafe24/authorize")).json()
    state = parse_qs(urlsplit(start["authorizationUrl"]).query)["state"][0]
    response = await client.get(
        "/api/commerce/cafe24/callback",
        params={"state": state, "code": "code"},
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 303
    assert response.headers["Location"] == f"/stores/{w.shop_id}/products"


async def test_ai_uses_existing_local_adapter_and_rejects_invented_fact(client, db, monkeypatch):
    from seelo.services import commerce_service

    w = await world(client, db, monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_plan_model", "codex-cli/test-model")

    async def structured(prompt, schema, *, model):
        from seelo.schemas.commerce import FactNeeds

        assert model == "codex-cli/test-model"
        if schema is FactNeeds:
            # 필요한 사실 종류만 고른다. 이미 확인한 소재만 필요하다고 답한다.
            assert '"found": ["material"]' in prompt
            return SimpleNamespace(parsed=FactNeeds(required=["material"]), model_id=model)
        assert "면 100%" in prompt
        return SimpleNamespace(parsed=FactOrder(fact_keys=["material"]), model_id=model)

    monkeypatch.setattr(
        commerce_service,
        "get_clients",
        lambda: SimpleNamespace(openai=SimpleNamespace(structured=structured)),
    )
    response = await client.post(f"/api/commerce/products/{w.product['id']}/plans", json={"useAi": True})
    assert response.status_code == 201 and response.json()["modelId"] == "codex-cli/test-model"

    async def invented(prompt, schema, *, model):
        from seelo.schemas.commerce import FactNeeds

        if schema is FactNeeds:
            return SimpleNamespace(parsed=FactNeeds(required=[]), model_id=model)
        return SimpleNamespace(parsed=FactOrder(fact_keys=["power"]), model_id="codex-cli/test-model")

    monkeypatch.setattr(
        commerce_service, "get_clients", lambda: SimpleNamespace(openai=SimpleNamespace(structured=invented))
    )
    response = await client.post(f"/api/commerce/products/{w.product['id']}/plans", json={"useAi": True})
    assert response.status_code == 503


async def test_selected_approval_limits_write_and_rollback(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w, fields=["description", "summary_description"])
    response = await client.post(
        f"/api/commerce/plans/{p['id']}/approve",
        json={
            "snapshotHash": p["snapshotHash"],
            "fields": ["summary_description"],
        },
    )
    assert response.status_code == 200
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).json()["status"] == "applied"
    assert "data-seelo" not in w.state["product"]["description"]
    assert w.state["product"]["summary_description"] == "소재: 면 100%"
    writes = (await client.get(f"/api/commerce/plans/{p['id']}/writes")).json()["writes"]
    assert set(writes[0]["after"]) == {"summary_description"}
    assert (await client.post(f"/api/commerce/plans/{p['id']}/rollback")).json()["status"] == "rolled_back"
    assert w.state["product"]["summary_description"] == ""


async def test_rollback_keeps_later_seller_edits(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    await client.post(f"/api/commerce/plans/{p['id']}/apply")
    w.state["product"]["description"] = "판매자가 나중에 바꾼 내용"
    response = await client.post(f"/api/commerce/plans/{p['id']}/rollback")
    assert response.status_code == 409 and w.counter["writes"] == 1
    assert w.state["product"]["description"] == "판매자가 나중에 바꾼 내용"


async def test_smart_editor_confirmation_at_approval(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False, platform="smartstore")
    p = await plan(client, w, allowEditorConversion=True)
    url = f"/api/commerce/plans/{p['id']}/approve"
    assert (
        await client.post(url, json={"snapshotHash": p["snapshotHash"], "editorConversionConfirmed": False})
    ).status_code == 422
    response = await client.post(
        url, json={"snapshotHash": p["snapshotHash"], "editorConversionConfirmed": True}
    )
    assert response.status_code == 200


async def test_editor_conversion_checkbox_is_bound_to_approved_plan(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False, platform="smartstore")
    p = await plan(client, w, allowEditorConversion=True)
    response = await client.post(
        f"/api/commerce/plans/{p['id']}/approve", json={"snapshotHash": p["snapshotHash"]}
    )
    assert response.status_code == 200
    assert response.json()["approval"]["editorConversionConfirmed"] is True


async def test_ai_research_requires_literal_source_and_correct_model(client, db, monkeypatch):
    from seelo.schemas.commerce import ExtractedFact, FactExtraction
    from seelo.services import commerce_service

    w = await world(client, db, monkeypatch)
    row = await db.get(CommerceProduct, w.product["id"])
    row.snapshot = {**row.snapshot, "fields": {"description": "A-100 크기는 10cm입니다."}}
    await db.commit()
    monkeypatch.setattr(get_settings(), "openai_plan_model", "codex-cli/test-model")
    invalid = {"value": False}

    async def structured(prompt, schema, *, model):
        value = "100cm" if invalid["value"] else "10cm"
        return SimpleNamespace(
            parsed=FactExtraction(
                facts=[
                    ExtractedFact(
                        key="size",
                        value=value,
                        identity=w.product["identity"],
                        source_index=0,
                        quote="크기는 10cm입니다.",
                    )
                ]
            ),
            model_id=model,
        )

    monkeypatch.setattr(
        commerce_service,
        "get_clients",
        lambda: SimpleNamespace(
            openai=SimpleNamespace(structured=structured),
            website=SimpleNamespace(),
        ),
    )
    url = f"/api/commerce/products/{w.product['id']}/research"
    response = await client.post(url, json={})
    assert response.status_code == 200, response.text
    size = next(f for f in response.json()["facts"] if f["key"] == "size")
    assert size["value"] == "10cm" and size["source_url"].startswith("https://demo.cafe24api.com/")
    invalid["value"] = True
    assert (await client.post(url, json={})).status_code == 422


async def test_cafe_expired_state_and_other_browser_owner_denied(client, db, monkeypatch):
    w = await world(client, db, monkeypatch, api=False)
    monkeypatch.setattr(get_settings(), "cafe24_client_id", "app")
    monkeypatch.setattr(get_settings(), "cafe24_client_secret", SecretStr("secret"))
    result = (await client.post(f"/api/commerce/shops/{w.shop_id}/cafe24/authorize")).json()
    state = parse_qs(urlsplit(result["authorizationUrl"]).query)["state"][0]
    shop = await db.get(CommerceShop, w.shop_id, populate_existing=True)
    shop.oauth_expires_at = now_utc() - timedelta(seconds=1)
    await db.commit()
    assert (
        await client.get("/api/commerce/cafe24/callback", params={"state": state, "code": "test"})
    ).status_code == 400
    await make_user(db, "another-cafe-owner@seelo.test")
    await login(client, "another-cafe-owner@seelo.test")
    assert (
        await client.get("/api/commerce/cafe24/callback", params={"state": state, "code": "test"})
    ).status_code == 400


async def test_product_rows_and_tokens_follow_account_deletion(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    await plan(client, w)
    from seelo.domain.labels import ACCOUNT_DELETE_CONFIRM_TEXT

    response = await client.request(
        "DELETE", "/api/account", json={"confirmText": ACCOUNT_DELETE_CONFIRM_TEXT}
    )
    assert response.status_code == 204, response.text
    for model in (CommerceShop, CommerceProduct, CommercePlan, CommerceWrite):
        assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_refresh_does_not_release_duplicate_write_guard(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w)
    await approve(client, p)
    shop = await db.get(CommerceShop, w.shop_id, populate_existing=True)
    shop.access_expires_at = now_utc() - timedelta(seconds=1)
    await db.commit()
    refreshed = []

    async def refresh(mall_id, **kwargs):
        refreshed.append(mall_id)
        await asyncio.sleep(0.03)
        return {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "scopes": ["mall.read_product", "mall.write_product"],
            "expires_at": (now_utc() + timedelta(hours=2)).isoformat(),
        }

    monkeypatch.setattr(provider, "cafe_token", refresh)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    replies = await asyncio.gather(*[client.post(f"/api/commerce/plans/{p['id']}/apply") for _ in range(2)])
    assert sorted(r.status_code for r in replies) == [200, 409]
    assert w.counter["writes"] == 1 and len(refreshed) == 1


async def test_generation_reads_original_before_asking_seller(client, db, monkeypatch):
    from seelo.schemas.commerce import ExtractedFact, FactExtraction
    from seelo.services import commerce_service

    w = await world(client, db, monkeypatch)
    product = await db.get(CommerceProduct, w.product["id"])
    product.facts = []
    product.snapshot = {**product.snapshot, "fields": {"description": "A-100 소재: 면 100%"}}
    await db.commit()
    monkeypatch.setattr(get_settings(), "openai_plan_model", "codex-cli/test-model")
    calls = []

    async def structured(prompt, output_schema, *, model):
        calls.append(output_schema)
        parsed = (
            FactExtraction(
                facts=[
                    ExtractedFact(
                        key="material",
                        value="면 100%",
                        identity=w.product["identity"],
                        source_index=0,
                        quote="소재: 면 100%",
                    )
                ]
            )
            if output_schema is FactExtraction
            else FactOrder(fact_keys=["material"])
        )
        return SimpleNamespace(parsed=parsed, model_id=model)

    monkeypatch.setattr(
        commerce_service,
        "get_clients",
        lambda: SimpleNamespace(
            openai=SimpleNamespace(structured=structured),
            website=SimpleNamespace(),
        ),
    )
    response = await client.post(
        f"/api/commerce/products/{w.product['id']}/plans",
        json={
            "useAi": True,
            "requiredFacts": ["material"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["questions"] == [] and response.json()["changes"]
    assert calls == [FactExtraction, FactOrder]


async def test_operator_sees_all_customers_but_only_executes_customer_approval(client, db, monkeypatch):
    w = await world(client, db, monkeypatch)
    p = await plan(client, w, fields=["description"])
    draft = await plan(client, w, fields=["summary_description"])
    await approve(client, p)
    await make_user(db, "commerce-second@seelo.test")
    await login(client, "commerce-second@seelo.test")
    other = await client.post("/api/commerce/shops", json={"storeUrl": "https://smartstore.naver.com/second"})
    await client.post(f"/api/commerce/shops/{other.json()['id']}/manager", json={"status": "invited"})
    assert (await client.get("/api/commerce/operator/shops")).status_code == 403
    assert (await client.get("/api/commerce/shops")).json()["shops"][0]["externalId"] == "second"
    admin = await make_user(db, "commerce-operator@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, admin.email)
    # 관리자도 /shops에서는 자기 스토어만 본다. 고객 목록은 운영자 경로로만 본다.
    assert (await client.get("/api/commerce/shops")).json()["shops"] == []
    listing = (await client.get("/api/commerce/operator/shops")).json()
    assert listing["total"] == 2 and listing["invited"] == 1
    assert listing["shops"][0]["managerStatus"] == "invited"
    assert {s["ownerEmail"] for s in listing["shops"]} == {
        "commerce-owner@seelo.test",
        "commerce-second@seelo.test",
    }
    first = next(s for s in listing["shops"] if s["id"] == w.shop_id)
    assert first["work"] == {
        "products": 1,
        "customerApproval": 1,
        "operatorExecute": 1,
        "manualEdit": 0,
        "checkResult": 0,
    }
    invited = (await client.get("/api/commerce/operator/shops?managerStatus=invited")).json()
    assert [s["externalId"] for s in invited["shops"]] == ["second"]
    tasks = {t["planId"]: t for t in (await client.get("/api/commerce/operator/tasks")).json()["tasks"]}
    assert tasks[p["id"]]["next"] == "execute" and tasks[p["id"]]["customerApproved"] is True
    assert tasks[draft["id"]]["next"] == "customer_approval"
    # 운영자는 고객 승인을 대신하지 않는다.
    response = await client.post(
        f"/api/commerce/plans/{draft['id']}/approve", json={"snapshotHash": draft["snapshotHash"]}
    )
    assert response.status_code == 403
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    row = await db.get(CommercePlan, p["id"])
    original = dict(row.approval)
    row.approval = {k: v for k, v in original.items() if k != "approvedBy"}
    await db.commit()
    denied = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "customer_approval_required"
    assert w.counter["writes"] == 0
    row = await db.get(CommercePlan, p["id"], populate_existing=True)
    row.approval = original
    await db.commit()
    applied = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert applied.json()["status"] == "applied" and w.counter["writes"] == 1
    assert set(applied.json()["approval"]["fields"]) == {"description"}
    restored = await client.post(f"/api/commerce/plans/{p['id']}/rollback")
    assert restored.json()["status"] == "rolled_back" and w.counter["writes"] == 2


async def drain_commerce(queue_app, db, queues=("commerce_browser",)):
    """실제 Procrastinate 워커로 쇼핑몰 작업을 끝까지 처리한다."""
    from sqlalchemy import text

    for _ in range(10):
        await queue_app.run_worker_async(queues=list(queues), wait=False, install_signal_handlers=False)
        left = await db.scalar(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status IN ('todo','doing') AND queue_name = ANY(:q)"
            ),
            {"q": list(queues)},
        )
        if not left:
            return
    raise AssertionError("쇼핑몰 작업이 끝나지 않음")


async def test_worker_runs_browser_jobs_without_resending(client, db, monkeypatch, queue_app):
    from seelo.models.commerce import CommerceJob

    w = await browser_world(client, db, monkeypatch, runner="worker")
    endpoint = f"/api/commerce/shops/{w.shop_id}/products/import"
    queued = await client.post(endpoint, json={"externalId": "123"})
    assert queued.status_code == 202, queued.text
    job = queued.json()["job"]
    assert job["kind"] == "collect" and job["status"] == "queued"
    duplicate = await client.post(endpoint, json={"externalId": "123"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["reason"] == "job_in_progress"
    assert w.counter["reads"] == 0
    await drain_commerce(queue_app, db)
    done = (await client.get(f"/api/commerce/jobs/{job['id']}")).json()
    assert done["status"] == "succeeded" and done["result"]["productId"]
    shop_view = (await client.get(f"/api/commerce/shops/{w.shop_id}")).json()
    assert shop_view["browserSession"]["status"] == "ok" and shop_view["browserRunner"] == "worker"
    w.product = (await client.get(f"/api/commerce/products/{done['result']['productId']}")).json()
    assert w.product["snapshotSource"] == "browser"
    p = await plan(client, w, fields=["description"])
    await approve(client, p)
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    applying = await client.post(f"/api/commerce/plans/{p['id']}/apply")
    assert applying.status_code == 202
    assert applying.json()["status"] == "approved" and applying.json()["job"]["status"] == "queued"
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).status_code == 409
    assert w.counter["writes"] == 0
    await drain_commerce(queue_app, db)
    applied = (await client.get(f"/api/commerce/plans/{p['id']}")).json()
    assert applied["status"] == "applied" and applied["job"]["status"] == "succeeded"
    assert w.counter["writes"] == 1
    # 로그인 만료: 복구 작업이 브라우저를 열자마자 멈추고 같은 몰 세션 상태를 표시한다.
    original_fetch = provider.ProductApi.fetch

    async def expired(self, product_no):
        raise provider.CommerceApiError("login_required")

    monkeypatch.setattr(provider.ProductApi, "fetch", expired)
    assert (await client.post(f"/api/commerce/plans/{p['id']}/rollback")).status_code == 202
    await drain_commerce(queue_app, db)
    failed = (await client.get(f"/api/commerce/plans/{p['id']}")).json()
    assert failed["status"] == "applied" and failed["job"]["errorCode"] == "login_required"
    shop_view = (await client.get(f"/api/commerce/shops/{w.shop_id}")).json()
    assert shop_view["browserSession"]["status"] == "login_required"
    assert w.counter["writes"] == 1
    # 재로그인 후: 복구 저장 결과가 불명확하면 uncertain으로 두고, 재조회만 받는다.
    monkeypatch.setattr(provider.ProductApi, "fetch", original_fetch)
    w.counter["timeout"] = True
    assert (await client.post(f"/api/commerce/plans/{p['id']}/rollback")).status_code == 202
    await drain_commerce(queue_app, db)
    uncertain = (await client.get(f"/api/commerce/plans/{p['id']}")).json()
    assert uncertain["status"] == "uncertain" and w.counter["writes"] == 2
    assert (await client.post(f"/api/commerce/plans/{p['id']}/rollback")).status_code == 409
    assert (await client.post(f"/api/commerce/plans/{p['id']}/apply")).status_code == 409
    w.counter["timeout"] = False
    # 중단 의심 작업은 실패로 정리하고 새 재조회 작업을 받는다. 저장은 다시 보내지 않는다.
    stuck = CommerceJob(
        shop_id=w.shop_id,
        plan_id=p["id"],
        product_id=w.product["id"],
        kind="verify",
        status="running",
        dedupe_key=f"plan:{p['id']}",
        input={},
        result={},
        started_at=now_utc() - timedelta(hours=1),
    )
    db.add(stuck)
    await db.commit()
    assert (await client.post(f"/api/commerce/plans/{p['id']}/verify")).status_code == 202
    await db.refresh(stuck)
    assert stuck.status == "failed" and stuck.error_code == "stalled"
    await drain_commerce(queue_app, db)
    verified = (await client.get(f"/api/commerce/plans/{p['id']}")).json()
    assert verified["status"] == "rolled_back" and w.counter["writes"] == 2
    jobs = (await client.get(f"/api/commerce/shops/{w.shop_id}/jobs")).json()["jobs"]
    assert [j["kind"] for j in jobs][:2] == ["verify", "verify"]


async def test_disconnect_cancels_queued_browser_jobs_and_forgets_session(
    client, db, monkeypatch, queue_app, tmp_path
):
    from seelo.models.commerce import CommerceJob

    monkeypatch.setattr(get_settings(), "commerce_browser_profile_root", str(tmp_path))
    w = await browser_world(client, db, monkeypatch, runner="worker")
    profile = tmp_path / "cafe24" / "demo" / "1"
    profile.mkdir(parents=True)
    (profile / ".seelo-session.enc").write_bytes(b"encrypted-session")
    queued = await client.post(f"/api/commerce/shops/{w.shop_id}/products/import", json={"externalId": "123"})
    job_id = queued.json()["job"]["id"]
    response = await client.post(f"/api/commerce/shops/{w.shop_id}/disconnect")
    assert response.json()["managerStatus"] == "revoked"
    await drain_commerce(queue_app, db)
    job = await db.get(CommerceJob, job_id, populate_existing=True)
    assert job.status == "failed" and job.error_code == "disconnected"
    assert w.counter["reads"] == 0
    forget = await db.scalar(select(CommerceJob).where(CommerceJob.kind == "forget_session"))
    assert forget.status == "succeeded" and not profile.exists()


async def test_operator_records_delegated_identity_and_reads_platform_catalog(
    client, db, monkeypatch, queue_app
):
    from seelo.integrations.browser import commerce as browser

    w = await browser_world(client, db, monkeypatch, runner="worker")
    seen = []

    async def catalog(max_items=500):
        return {
            "items": [{"productNo": "123", "name": "시험 셔츠"}, {"productNo": "456", "name": "다른 상품"}],
            "pages": 1,
            "skipped": 0,
            "truncated": False,
        }

    w.adapter.catalog = catalog

    def build(*args, **kwargs):
        seen.append(kwargs.get("identity"))
        return w.adapter

    monkeypatch.setattr(browser, "BrowserProduct", build)
    # 고객은 가게 고유값을 기록할 수 없다.
    denied = await client.post(
        f"/api/commerce/shops/{w.shop_id}/manager", json={"status": "invited", "storeName": "남의 가게"}
    )
    assert denied.status_code == 403
    queued = await client.post(f"/api/commerce/shops/{w.shop_id}/products/import", json={"externalId": "123"})
    assert queued.status_code == 202
    await drain_commerce(queue_app, db)
    admin = await make_user(db, "commerce-identity-admin@seelo.test")
    admin.role = "admin"
    await db.commit()
    await login(client, admin.email)
    verified = await client.post(
        f"/api/commerce/shops/{w.shop_id}/manager",
        json={"status": "verified", "storeName": "시험몰 공식", "storeId": "ch-1001"},
    )
    assert verified.json()["delegatedIdentity"]["storeName"] == "시험몰 공식"
    response = await client.post(f"/api/commerce/shops/{w.shop_id}/catalog")
    assert response.status_code == 202 and response.json()["job"]["kind"] == "catalog"
    assert (await client.post(f"/api/commerce/shops/{w.shop_id}/catalog")).status_code == 409
    await drain_commerce(queue_app, db)
    assert seen[-1]["storeName"] == "시험몰 공식" and seen[-1]["storeId"] == "ch-1001"
    listing = (await client.get(f"/api/commerce/shops/{w.shop_id}/catalog")).json()
    assert listing["scope"] == "platform" and [i["productNo"] for i in listing["items"]] == ["123", "456"]
    imported = {i["productNo"]: i["importedProductId"] for i in listing["items"]}
    assert imported["123"] is not None and imported["456"] is None
    # 권한 회수 후에는 기록한 가게 값을 지우고 목록 조회도 받지 않는다.
    revoked = await client.post(f"/api/commerce/shops/{w.shop_id}/manager", json={"status": "revoked"})
    assert revoked.json()["delegatedIdentity"] is None
    assert (await client.post(f"/api/commerce/shops/{w.shop_id}/catalog")).status_code == 409


async def test_collect_runs_ai_research_needs_and_minimal_questions(client, db, monkeypatch, queue_app):
    from seelo.schemas.commerce import ExtractedFact, FactExtraction, FactNeeds
    from seelo.services import commerce_service

    w = await browser_world(client, db, monkeypatch, runner="worker")
    w.state["product"]["description"] = (
        '<p>A-100 원재료: 사차인치 100%</p><a href="https://maker.example.com/a100">제조사 자료</a>'
    )
    # 실제 브라우저 원본처럼 관리 화면 주소를 원본 출처로 남긴다.
    w.state["source_url"] = "https://demo.cafe24.com/disp/admin/shop1/product/ProductRegister?product_no=123"
    monkeypatch.setattr(get_settings(), "openai_plan_model", "codex-cli/test-model")
    fetched, needs_prompts = [], []
    maker = "<p>A-100 영양성분 1회 30g당 단백질 12g</p><p>A-100 섭취 방법: 1회 30g</p>"

    async def robots_allows(url):
        return SimpleNamespace(allowed=True)

    async def fetch(url):
        fetched.append(url)
        return SimpleNamespace(status=200, url=url, html=maker)

    async def structured(prompt, output_schema, *, model):
        identity = w.product_identity
        if output_schema is FactExtraction:
            facts = [
                ExtractedFact(
                    key="ingredients",
                    value="사차인치 100%",
                    identity=identity,
                    source_index=0,
                    quote="원재료: 사차인치 100%",
                ),
                ExtractedFact(
                    key="nutrition",
                    value="1회 30g당 단백질 12g",
                    identity=identity,
                    source_index=1,
                    quote="영양성분 1회 30g당 단백질 12g",
                ),
                # 단위 없는 함량은 인용문에 있어도 저장하지 않는다.
                ExtractedFact(
                    key="serving", value="1회 30", identity=identity, source_index=1, quote="1회 30g"
                ),
            ]
            return SimpleNamespace(parsed=FactExtraction(facts=facts), model_id=model)
        if output_schema is FactNeeds:
            needs_prompts.append(prompt)
            return SimpleNamespace(
                parsed=FactNeeds(required=["ingredients", "nutrition", "allergens"]), model_id=model
            )
        return SimpleNamespace(parsed=FactOrder(fact_keys=["nutrition", "ingredients"]), model_id=model)

    monkeypatch.setattr(
        commerce_service,
        "get_clients",
        lambda: SimpleNamespace(
            openai=SimpleNamespace(structured=structured),
            website=SimpleNamespace(robots_allows=robots_allows, fetch=fetch),
        ),
    )
    w.product_identity = "시험 셔츠 | A-100"
    queued = await client.post(f"/api/commerce/shops/{w.shop_id}/products/import", json={"externalId": "123"})
    product_id = None
    await drain_commerce(queue_app, db)
    job = (await client.get(f"/api/commerce/jobs/{queued.json()['job']['id']}")).json()
    product_id = job["result"]["productId"]
    product = (await client.get(f"/api/commerce/products/{product_id}")).json()
    assert product["prepareJob"]["status"] == "queued" and product["identity"] == w.product_identity
    await drain_commerce(queue_app, db, queues=("plan",))
    product = (await client.get(f"/api/commerce/products/{product_id}")).json()
    assert product["prepareJob"]["status"] == "succeeded", (
        product["prepareJob"]["errorCode"],
        product["prepareJob"]["result"],
    )
    facts = {f["key"]: f for f in product["facts"]}
    assert facts["nutrition"]["source_url"] == "https://maker.example.com/a100"
    assert "serving" not in facts and fetched == ["https://maker.example.com/a100"]
    plans = (await client.get(f"/api/commerce/products/{product_id}/plans")).json()["plans"]
    latest = plans[0]
    # 사장님이 필드·필수 사실을 고르지 않았다. 확인하지 못한 알레르기 정보만 묻는다.
    assert latest["status"] == "draft" and [q["field"] for q in latest["questions"]] == ["allergens"]
    assert latest["changes"][0]["field"] == "description" and "단백질 12g" in latest["changes"][0]["proposed"]
    assert latest["modelId"] == "codex-cli/test-model" and needs_prompts
    # 함량은 단위·출처를 함께 검사한다.
    bad = await client.post(
        f"/api/commerce/products/{product_id}/facts",
        json={
            "facts": [
                {
                    "key": "nutrition",
                    "value": "단백질 15g",
                    "identity": w.product_identity,
                    "sourceUrl": "https://maker.example.com/a100",
                    "quote": "단백질 15g 이상 함유를 목표로",
                },
                {
                    "key": "serving",
                    "value": "1회 한 스푼",
                    "identity": w.product_identity,
                    "sourceUrl": "https://maker.example.com/a100",
                    "quote": "1회 한 스푼",
                },
            ]
        },
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"]["reason"] == "quantity_unit_required"
    answer = await client.post(
        f"/api/commerce/products/{product_id}/answers", json={"answers": {"allergens": "없음"}}
    )
    assert answer.status_code == 200
    again = await client.post(f"/api/commerce/products/{product_id}/prepare", json={})
    assert again.status_code == 202 and again.json()["job"]["kind"] == "prepare"
    await drain_commerce(queue_app, db, queues=("plan",))
    plans = (await client.get(f"/api/commerce/products/{product_id}/plans")).json()["plans"]
    assert plans[0]["id"] != latest["id"] and plans[0]["questions"] == []


async def test_measure_runs_store_raw_answers_and_compare_same_condition(client, db, monkeypatch, queue_app):
    from seelo.integrations.llm import LlmError
    from seelo.models.commerce import CommerceMeasureAnswer
    from seelo.services import commerce_measure

    w = await world(client, db, monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_measure_model", "m-openai")
    monkeypatch.setattr(get_settings(), "gemini_measure_model", "m-gemini")
    url = f"/api/commerce/products/{w.product['id']}/measure-sets"
    target = "https://demo.cafe24.com/product/detail.html?product_no=123"
    rejected = await client.post(
        url,
        json={
            "name": "B",
            "queries": [{"id": "G01", "question": "시험 셔츠를 찾아줘"}],
            "targetUrls": [target],
        },
    )
    assert rejected.json()["error"]["details"]["reason"] == "query_contains_target"
    created = await client.post(
        url,
        json={
            "name": "면 셔츠 기본",
            "queries": [
                {"id": "G01", "question": "면 100% 셔츠를 찾아줘."},
                {"id": "G02", "family": "material", "question": "통기성 좋은 셔츠를 찾아줘."},
            ],
            "targetUrls": [target],
        },
    )
    assert created.status_code == 201, created.text
    measure_set = created.json()
    assert measure_set["targets"]["names"] == ["시험 셔츠"] and "추정하지 마" in measure_set["commonSuffix"]
    calls = []

    async def web_answer(prompt, *, model):
        calls.append((prompt, model))
        n = len(calls)
        if "통기성" in prompt and n % 2 == 0:
            raise LlmError("openai", "timeout")
        if "통기성" in prompt:
            return SimpleNamespace(text="1. 다른 셔츠\n2. 또 다른 셔츠", sources=[], model_id=model)
        return SimpleNamespace(
            text="1. 시험 셔츠 - 시험몰\n2. 다른 셔츠",
            sources=[{"url": target}],
            model_id=model,
        )

    clients = SimpleNamespace(
        openai=SimpleNamespace(web_answer=web_answer), gemini=SimpleNamespace(web_answer=web_answer)
    )
    monkeypatch.setattr(commerce_measure, "get_clients", lambda: clients)
    first = await client.post(
        f"/api/commerce/measure-sets/{measure_set['id']}/runs",
        json={"label": "B0", "provider": "openai", "repeats": 2},
    )
    assert first.status_code == 202 and first.json()["job"]["status"] == "queued"
    assert (
        first.json()["condition"]["model"] == "m-openai"
        and first.json()["snapshotHash"] == w.product["snapshotHash"]
    )
    await drain_commerce(queue_app, db, queues=("ai_openai",))
    run = (await client.get(f"/api/commerce/measure-runs/{first.json()['id']}")).json()
    assert all(prompt.endswith("추정하지 마.") and "demo.cafe24.com" not in prompt for prompt, _ in calls)
    g01, g02 = run["summary"]["queries"]
    assert (g01["valid"], g01["identified"], g01["recommended"], g01["cited"]) == (2, 2, 2, 2)
    # 실패 응답은 노출 0이 아니라 무효다. 1회만 다시 실행하고 최초 실패도 원문 기록에 남긴다.
    assert g02["valid"] + g02["missing"] == 2 and g02["failedAttempts"] >= 1 and g02["identified"] == 0
    failed = await db.scalar(
        select(func.count())
        .select_from(CommerceMeasureAnswer)
        .where(CommerceMeasureAnswer.status == "failed")
    )
    assert failed == g02["failedAttempts"]
    assert run["status"] in {"completed", "partial"} and run["answers"][0]["rawText"]
    second = await client.post(
        f"/api/commerce/measure-sets/{measure_set['id']}/runs",
        json={"label": "P1", "provider": "openai", "repeats": 2},
    )
    await drain_commerce(queue_app, db, queues=("ai_openai",))
    compared = await client.get(
        f"/api/commerce/measure-compare?before={first.json()['id']}&after={second.json()['id']}"
    )
    assert compared.status_code == 200, compared.text
    assert (
        compared.json()["sameSnapshot"] is True and compared.json()["queries"][0]["before"]["identified"] == 2
    )
    other = await client.post(
        f"/api/commerce/measure-sets/{measure_set['id']}/runs",
        json={"label": "G1", "provider": "gemini", "repeats": 2},
    )
    await drain_commerce(queue_app, db, queues=("ai_gemini",))
    mismatch = await client.get(
        f"/api/commerce/measure-compare?before={first.json()['id']}&after={other.json()['id']}"
    )
    assert mismatch.status_code == 422
    assert set(mismatch.json()["error"]["details"]["fields"]) == {"provider", "model"}
    await make_user(db, "commerce-measure-other@seelo.test")
    await login(client, "commerce-measure-other@seelo.test")
    assert (await client.get(f"/api/commerce/measure-runs/{first.json()['id']}")).status_code == 404
