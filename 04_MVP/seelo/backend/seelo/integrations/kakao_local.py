"""카카오 로컬 키워드 검색 어댑터(07 4.2, 2026-10-23 공식 문서로 확인).

**저장 금지**: 응답 중 id·place_url 말고는 DB·작업 인자·스냅샷에 넣지 않는다. Place.raw는 메모리에서만 쓴다.
"""

import time
from typing import Any

import httpx
import structlog

from seelo.config import get_settings
from seelo.integrations import Place
from seelo.integrations.http import MAP_API_TIMEOUT_S, ExternalApiError, make_client

log = structlog.get_logger()

URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def to_place(doc: dict[str, Any]) -> Place:
    return Place(
        provider="kakao",
        external_id=str(doc.get("id")) if doc.get("id") is not None else None,
        name=doc.get("place_name", ""),
        address=doc.get("road_address_name") or doc.get("address_name") or None,
        lat=float(doc["y"]) if doc.get("y") else None,
        lng=float(doc["x"]) if doc.get("x") else None,
        phone=doc.get("phone") or None,
        category_raw=[doc.get("category_group_code", ""), doc.get("category_name", "")],
        url=doc.get("place_url"),
        raw=doc,
    )


class KakaoLocal:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def keyword(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
        sort: str = "accuracy",
        page: int = 1,
        size: int = 15,
    ) -> tuple[list[Place], bool]:
        """(결과, meta.is_end). x·y는 경도·위도, radius는 0~20000m, distance 정렬은 x·y가 있어야 한다."""
        key = get_settings().kakao_rest_api_key.get_secret_value()
        if not key:
            raise ExternalApiError("kakao", "not_configured")
        params: dict[str, Any] = {"query": query, "page": page, "size": size, "sort": sort}
        if x is not None and y is not None:
            params.update({"x": x, "y": y})
            if radius is not None:
                params["radius"] = radius
        started = time.perf_counter()
        try:
            async with make_client(MAP_API_TIMEOUT_S, transport=self._transport) as c:
                resp = await c.get(URL, params=params, headers={"Authorization": f"KakaoAK {key}"})
        except httpx.HTTPError as e:
            raise ExternalApiError("kakao", type(e).__name__) from e
        log.info(
            "kakao_local_call", status=resp.status_code, ms=round((time.perf_counter() - started) * 1000)
        )
        if resp.status_code != 200:
            raise ExternalApiError("kakao", "search_failed", resp.status_code)
        data = resp.json()
        return [to_place(d) for d in data.get("documents") or []], bool(
            (data.get("meta") or {}).get("is_end", True)
        )
