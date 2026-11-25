"""공식 HTTP 계약과 안전한 부분 수정. 응답은 가짜 HTTP transport다."""

import copy
import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from seelo.config import get_settings
from seelo.integrations.commerce import CommerceApiError, ProductApi, cafe_token, smartstore_token


async def test_cafe24_payload_only_approved_fields():
    api = ProductApi("cafe24", "demo", 1, "private-token")
    original = {"product": {"product_no": 123, "price": "10000", "selling": "F"}, "seo": {}}
    with respx.mock as mock:
        main = mock.put("https://demo.cafe24api.com/api/v2/admin/products/123").respond(
            200, json={"product": {}}
        )
        seo = mock.put("https://demo.cafe24api.com/api/v2/admin/products/123/seo").respond(
            200, json={"seo": {}}
        )
        await api.write("123", original, {"description": "승인 HTML", "seo.meta_description": "승인 요약"})
        assert json.loads(main.calls[0].request.content) == {
            "shop_no": 1,
            "request": {"description": "승인 HTML"},
        }
        assert json.loads(seo.calls[0].request.content) == {
            "shop_no": 1,
            "request": {"meta_description": "승인 요약"},
        }
        assert main.calls[0].request.headers["Authorization"] == "Bearer private-token"
        assert original["product"]["selling"] == "F"


async def test_cafe24_partial_success_is_uncertain_without_retry():
    api = ProductApi("cafe24", "demo", 1, "token")
    with respx.mock as mock:
        main = mock.put("https://demo.cafe24api.com/api/v2/admin/products/123").respond(200, json={})
        seo = mock.put("https://demo.cafe24api.com/api/v2/admin/products/123/seo").respond(
            403, json={"secret": "hidden"}
        )
        with pytest.raises(CommerceApiError) as caught:
            await api.write("123", {}, {"description": "설명", "seo.meta_title": "제목"})
        assert caught.value.uncertain and "hidden" not in str(caught.value)
        assert main.call_count == seo.call_count == 1


async def test_smartstore_preserves_price_options_delivery_and_channel():
    raw = {
        "originProduct": {
            "name": "상품",
            "salePrice": 999,
            "stockQuantity": 7,
            "detailContent": "원본",
            "detailAttribute": {"optionInfo": {"options": [1, 2]}},
            "deliveryInfo": {"deliveryFee": {"baseFee": 3000}},
        },
        "smartstoreChannelProduct": {"channelProductNo": 123, "channelProductDisplayStatusType": "ON"},
        "originProductNo": 321,
    }
    original = copy.deepcopy(raw)
    with respx.mock as mock:
        call = mock.put("https://api.commerce.naver.com/external/v2/products/origin-products/321").respond(
            200, json={}
        )
        await ProductApi("smartstore", "demo", 1, "token").write("321", raw, {"description": "정비 설명"})
        actual = json.loads(call.calls[0].request.content)
        assert actual["originProduct"]["detailContent"] == "정비 설명"
        actual["originProduct"]["detailContent"] = "원본"
        assert actual == {k: v for k, v in original.items() if k != "originProductNo"}
        assert raw == original


async def test_automatic_redirects_are_not_followed():
    api = ProductApi("cafe24", "demo", 1, "token")
    with respx.mock as mock:
        call = mock.get("https://demo.cafe24api.com/api/v2/admin/products/123").respond(
            302, headers={"Location": "https://attacker.example.com"}
        )
        with pytest.raises(CommerceApiError):
            await api.fetch("123")
        assert call.call_count == 1


async def test_cafe_token_checks_mall_scope_and_keeps_secrets_off_errors(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "cafe24_client_id", "app")
    monkeypatch.setattr(settings, "cafe24_client_secret", SecretStr("private-client-secret"))
    with respx.mock as mock:
        call = mock.post("https://demo.cafe24api.com/api/v2/oauth/token").respond(
            200,
            json={
                "mall_id": "different",
                "access_token": "private-access",
                "refresh_token": "private-refresh",
                "scopes": ["mall.read_product", "mall.write_product"],
            },
        )
        with pytest.raises(CommerceApiError, match="token_identity_mismatch"):
            await cafe_token("demo", code="private-code")
        assert "private-client-secret" not in call.calls[0].request.content.decode()
        call.respond(
            200,
            json={
                "mall_id": "demo",
                "access_token": "x",
                "refresh_token": "y",
                "scopes": ["mall.read_product"],
            },
        )
        with pytest.raises(CommerceApiError, match="product_scopes_required"):
            await cafe_token("demo", code="code")


async def test_smartstore_only_official_seller_tokens(monkeypatch):
    import bcrypt

    settings = get_settings()
    monkeypatch.setattr(settings, "smartstore_solution_enabled", False)
    with pytest.raises(CommerceApiError, match="official_seller_connection_required"):
        await smartstore_token("seller-a")
    monkeypatch.setattr(settings, "smartstore_solution_enabled", True)
    monkeypatch.setattr(settings, "smartstore_client_id", "official-app")
    monkeypatch.setattr(settings, "smartstore_client_secret", SecretStr(bcrypt.gensalt().decode()))
    with respx.mock as mock:
        call = mock.post("https://api.commerce.naver.com/external/v1/oauth2/token").respond(
            200, json={"access_token": "private-token", "expires_in": 10800}
        )
        result = await smartstore_token("seller-a")
        from urllib.parse import parse_qs

        data = parse_qs(call.calls[0].request.content.decode())
        assert data["type"] == ["SELLER"] and data["account_id"] == ["seller-a"]
        assert "client_secret" not in data and result["account_id"] == "seller-a"


async def test_put_timeout_is_uncertain():
    with respx.mock as mock:
        call = mock.put("https://demo.cafe24api.com/api/v2/admin/products/123").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )
        with pytest.raises(CommerceApiError) as caught:
            await ProductApi("cafe24", "demo", 1, "token").write("123", {}, {"description": "설명"})
        assert caught.value.uncertain and call.call_count == 1
