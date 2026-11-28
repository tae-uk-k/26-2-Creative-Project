"""NAVER API HUB 지역 검색 어댑터(07 4.3, 2026-10-23 네이버 클라우드 문서로 확인).

- 주소: NAVER_LOCAL_SEARCH_URL(기본 https://naverapihub.apigw.ntruss.com/search/v1/local).
- telephone은 값이 오지 않는 필드라 쓰지 않는다. 장소 번호도 주지 않는다(external_id 없음).
- **저장 금지·AI 입력 금지**: 응답 값은 DB에 넣지 않고 OpenAI·Gemini 요청에도 넣지 않는다.
"""

import html
import re
import time
from typing import Any

import httpx
import structlog

from seelo.config import get_settings
from seelo.domain.geo import parse_naver_coord
from seelo.integrations import Place
from seelo.integrations.http import MAP_API_TIMEOUT_S, ExternalApiError, make_client

log = structlog.get_logger()

_TAG = re.compile(r"<[^>]+>")


def clean_title(s: str) -> str:
    return html.unescape(_TAG.sub("", s or "")).strip()


def to_place(item: dict[str, Any]) -> Place:
    def coord(key: str) -> float | None:
        try:
            return parse_naver_coord(item[key]) if item.get(key) not in (None, "") else None
        except ValueError:
            return None

    title = clean_title(item.get("title", ""))
    return Place(
        provider="naver",
        external_id=None,
        name=title,
        address=item.get("roadAddress") or item.get("address") or None,
        lat=coord("mapy"),
        lng=coord("mapx"),
        phone=None,
        category_raw=[item.get("category", "")],
        url=None,
        raw={**item, "title": title},
    )


class NaverLocal:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def search(self, query: str, *, display: int = 5) -> list[Place]:
        s = get_settings()
        key = s.naver_api_key.get_secret_value()
        if not s.naver_api_key_id or not key:
            raise ExternalApiError("naver", "not_configured")
        headers = {"X-NCP-APIGW-API-KEY-ID": s.naver_api_key_id, "X-NCP-APIGW-API-KEY": key}
        params = {"query": query, "display": display, "start": 1, "sort": "random"}
        started = time.perf_counter()
        try:
            async with make_client(MAP_API_TIMEOUT_S, transport=self._transport) as c:
                resp = await c.get(s.naver_local_search_url, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise ExternalApiError("naver", type(e).__name__) from e
        log.info(
            "naver_local_call", status=resp.status_code, ms=round((time.perf_counter() - started) * 1000)
        )
        if resp.status_code in (400, 404):
            # 설정·코드 오류(SE01~SE06). Sentry로 가도록 error
            log.error("naver_local_bad_request", status=resp.status_code)
        if resp.status_code != 200:
            raise ExternalApiError("naver", "search_failed", resp.status_code)
        return [to_place(i) for i in resp.json().get("items") or []]
