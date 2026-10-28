"""Google Places API(New) 어댑터(07 4.1, 2026-10-23 공식 문서로 확인).

- 키 헤더 X-Goog-Api-Key, 필드 마스크 X-Goog-FieldMask는 필수이고 공백 없이 쉼표로 잇는다.
- languageCode(기본 en)와 regionCode(기본 없음)는 항상 명시한다.
- 응답 원문은 로그에 남기지 않는다(상태 코드·지연 시간만).
"""

import time
from typing import Any

import httpx
import structlog

from seelo.config import get_settings
from seelo.integrations import Place
from seelo.integrations.http import MAP_API_TIMEOUT_S, ExternalApiError, make_client

log = structlog.get_logger()

BASE = "https://places.googleapis.com/v1"
IDENTIFY_FIELDS = "id,displayName,formattedAddress,location,types,primaryType,googleMapsUri"
SEARCH_FIELDS = ",".join(f"places.{f}" for f in IDENTIFY_FIELDS.split(","))


def to_place(raw: dict[str, Any]) -> Place:
    loc = raw.get("location") or {}
    return Place(
        provider="google",
        external_id=raw.get("id"),
        name=(raw.get("displayName") or {}).get("text", ""),
        address=raw.get("formattedAddress"),
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        phone=raw.get("nationalPhoneNumber"),
        category_raw=list(raw.get("types") or []),
        url=raw.get("googleMapsUri"),
        raw=raw,
    )


class GooglePlaces:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _headers(self, fields: str) -> dict[str, str]:
        key = get_settings().google_places_api_key.get_secret_value()
        if not key:
            raise ExternalApiError("google", "not_configured")
        return {"X-Goog-Api-Key": key, "X-Goog-FieldMask": fields}

    async def _call(self, method: str, url: str, fields: str, **kw: Any) -> httpx.Response:
        started = time.perf_counter()
        try:
            async with make_client(MAP_API_TIMEOUT_S, transport=self._transport) as c:
                resp = await c.request(method, url, headers=self._headers(fields), **kw)
        except httpx.HTTPError as e:
            raise ExternalApiError("google", type(e).__name__) from e
        log.info(
            "google_places_call",
            op=url.rsplit("/", 1)[-1].split("?")[0][:40],
            status=resp.status_code,
            ms=round((time.perf_counter() - started) * 1000),
        )
        return resp

    async def search_text(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        radius_m: float = 200.0,
        page_size: int = 5,
    ) -> list[Place]:
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": "ko",
            "regionCode": "KR",
            "pageSize": page_size,
        }
        if lat is not None and lng is not None:
            body["locationBias"] = {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": float(radius_m)}
            }
        resp = await self._call("POST", f"{BASE}/places:searchText", SEARCH_FIELDS, json=body)
        if resp.status_code != 200:
            raise ExternalApiError("google", "search_failed", resp.status_code)
        return [to_place(p) for p in resp.json().get("places") or []]

    async def details(self, place_id: str, *, fields: str, language: str = "ko") -> dict[str, Any] | None:
        """404면 None(없는 장소). 그 밖 오류는 ExternalApiError."""
        resp = await self._call(
            "GET", f"{BASE}/places/{place_id}", fields, params={"languageCode": language, "regionCode": "KR"}
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ExternalApiError("google", "details_failed", resp.status_code)
        return resp.json()
