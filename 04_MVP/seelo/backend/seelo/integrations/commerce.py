"""공식 상품 API. 외부 주소는 고정하고 쓰기는 자동 재시도하지 않는다."""

import asyncio
import base64
import copy
import time
from typing import Any

import httpx

from seelo.config import get_settings
from seelo.domain.commerce import CAFE_FIELDS, SEO_FIELDS, check_fields


class CommerceApiError(Exception):
    def __init__(self, reason: str, *, uncertain: bool = False) -> None:
        self.reason, self.uncertain = reason, uncertain
        super().__init__(reason)


async def request(method: str, url: str, **kwargs) -> dict[str, Any]:
    """공급자 응답·토큰·요청 본문을 로그/사용자 오류로 내보내지 않는다."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            async with client.stream(method, url, **kwargs) as response:
                if response.status_code not in (200, 201):
                    status = response.status_code
                    raise CommerceApiError(
                        {
                            401: "auth_required",
                            403: "permission_denied",
                            404: "not_found",
                            429: "rate_limited",
                        }.get(status, "provider_rejected"),
                        uncertain=method == "PUT" and (status >= 500 or 300 <= status < 400),
                    )
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 4 * 1024 * 1024:
                        raise CommerceApiError("response_too_large", uncertain=method == "PUT")
                import json

                value = json.loads(payload)
                if not isinstance(value, dict):
                    raise ValueError("object_required")
                return value
    except CommerceApiError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise CommerceApiError("transport_or_response_error", uncertain=method == "PUT") from error


def cafe_base(mall_id: str) -> str:
    # 호출자는 등록 시 검사한 mall_id만 전달한다. 이 함수도 독립적으로 경계를 검사한다.
    import re

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,49}", mall_id):
        raise CommerceApiError("invalid_mall_id")
    return f"https://{mall_id}.cafe24api.com/api/v2"


async def cafe_token(mall_id: str, *, code: str | None = None, refresh_token: str | None = None) -> dict:
    s = get_settings()
    if not s.cafe24_client_id or not s.cafe24_client_secret.get_secret_value():
        raise CommerceApiError("not_configured")
    data = (
        {"grant_type": "authorization_code", "code": code, "redirect_uri": cafe_redirect()}
        if code is not None
        else {"grant_type": "refresh_token", "refresh_token": refresh_token}
    )
    result = await request(
        "POST",
        cafe_base(mall_id) + "/oauth/token",
        data=data,
        auth=httpx.BasicAuth(s.cafe24_client_id, s.cafe24_client_secret.get_secret_value()),
    )
    if result.get("mall_id") != mall_id or not result.get("access_token") or not result.get("refresh_token"):
        raise CommerceApiError("token_identity_mismatch")
    scope = result.get("scopes", result.get("scope", []))
    if isinstance(scope, str):
        scope = scope.replace(",", " ").split()
    if not {"mall.read_product", "mall.write_product"}.issubset(scope):
        raise CommerceApiError("product_scopes_required")
    result["scopes"] = scope
    return result


def cafe_redirect() -> str:
    return get_settings().app_base_url.rstrip("/") + "/api/commerce/cafe24/callback"


async def smartstore_token(account_id: str) -> dict:
    s = get_settings()
    if (
        not s.smartstore_solution_enabled
        or not s.smartstore_client_id
        or not s.smartstore_client_secret.get_secret_value()
    ):
        raise CommerceApiError("official_seller_connection_required")
    # 커머스솔루션 SELLER 경로. 개인용 SELF 키를 판매자에게 받지 않는다.
    import bcrypt

    stamp = int(time.time() * 1000)
    password = f"{s.smartstore_client_id}_{stamp}".encode()
    try:
        hashed = await asyncio.to_thread(
            bcrypt.hashpw, password, s.smartstore_client_secret.get_secret_value().encode()
        )
    except ValueError as error:
        raise CommerceApiError("invalid_solution_credentials") from error
    result = await request(
        "POST",
        "https://api.commerce.naver.com/external/v1/oauth2/token",
        data={
            "client_id": s.smartstore_client_id,
            "timestamp": stamp,
            "client_secret_sign": base64.b64encode(hashed).decode(),
            "grant_type": "client_credentials",
            "type": "SELLER",
            "account_id": account_id,
        },
    )
    if not result.get("access_token") or not isinstance(result.get("expires_in"), int):
        raise CommerceApiError("invalid_token_response")
    return {**result, "account_id": account_id}


class ProductApi:
    def __init__(self, platform: str, external_id: str, shop_no: int, token: str) -> None:
        if platform not in {"cafe24", "smartstore"}:
            raise CommerceApiError("unsupported_platform")
        self.platform, self.shop_no = platform, shop_no
        self.base = (
            cafe_base(external_id) + "/admin"
            if platform == "cafe24"
            else "https://api.commerce.naver.com/external"
        )
        self.headers = {"Authorization": "Bearer " + token}
        if platform == "cafe24":
            self.headers["X-Cafe24-Api-Version"] = get_settings().cafe24_api_version

    async def fetch(self, product_no: str) -> dict:
        if not product_no.isdecimal() or len(product_no) > 19:
            raise CommerceApiError("invalid_product_id")
        if self.platform == "cafe24":
            value = await request(
                "GET",
                self.base + f"/products/{product_no}",
                headers=self.headers,
                params={"shop_no": self.shop_no},
            )
            product = value.get("product")
            if not isinstance(product, dict) or str(product.get("product_no")) != product_no:
                raise CommerceApiError("product_identity_mismatch")
            seo = await request(
                "GET",
                self.base + f"/products/{product_no}/seo",
                headers=self.headers,
                params={"shop_no": self.shop_no},
            )
            return {"product": product, "seo": seo.get("seo", {})}
        value = await request(
            "GET", self.base + f"/v2/products/origin-products/{product_no}", headers=self.headers
        )
        if not isinstance(value.get("originProduct"), dict):
            raise CommerceApiError("product_identity_mismatch")
        return value

    def fields(self, raw: dict) -> dict[str, str]:
        if self.platform == "cafe24":
            p = raw["product"]
            return {
                **{k: p.get(k) or "" for k in CAFE_FIELDS},
                **{k: (raw.get("seo") or {}).get(k.split(".")[1]) or "" for k in SEO_FIELDS},
            }
        p = raw["originProduct"]
        return {"description": p.get("detailContent") or "", "attributes": ""}

    def identity(self, raw: dict) -> tuple[str, str]:
        p = raw["product"] if self.platform == "cafe24" else raw["originProduct"]
        name = p.get("product_name") if self.platform == "cafe24" else p.get("name")
        model = (
            p.get("model_name")
            if self.platform == "cafe24"
            else (p.get("detailAttribute") or {}).get("modelName")
        )
        if not isinstance(name, str) or not name.strip():
            raise CommerceApiError("product_name_required")
        return name, f"{name} | {model}" if model else name

    async def write(self, product_no: str, fresh: dict, changes: dict[str, str]) -> None:
        check_fields(self.platform, changes)
        if "attributes" in changes:
            raise CommerceApiError("attributes_require_manual_mapping")
        if self.platform == "cafe24":
            main = {k: v for k, v in changes.items() if k in CAFE_FIELDS}
            seo = {k.split(".")[1]: v for k, v in changes.items() if k in SEO_FIELDS}
            wrote = False
            for suffix, fields in (("", main), ("/seo", seo)):
                if not fields:
                    continue
                try:
                    await request(
                        "PUT",
                        self.base + f"/products/{product_no}" + suffix,
                        headers=self.headers,
                        json={"shop_no": self.shop_no, "request": fields},
                    )
                except CommerceApiError as error:
                    # 본문 저장 후 SEO 실패도 부분 성공일 수 있다. 전체를 자동 재전송하지 않는다.
                    raise CommerceApiError(error.reason, uncertain=wrote or error.uncertain) from error
                wrote = True
            return
        # 원상품 PUT은 전체 구조를 요구한다. 바로 재조회한 가격·재고·옵션·배송 조건을 보존한다.
        payload = {
            k: copy.deepcopy(v)
            for k, v in fresh.items()
            if k in {"originProduct", "smartstoreChannelProduct", "windowChannelProduct"}
        }
        payload["originProduct"]["detailContent"] = changes["description"]
        await request(
            "PUT",
            self.base + f"/v2/products/origin-products/{product_no}",
            headers=self.headers,
            json=payload,
        )
