"""인스타그램 Business Discovery(07 6.5 4번). INSTAGRAM_BUSINESS_DISCOVERY_ENABLED=true일 때만 부른다.

- GET https://graph.facebook.com/{버전}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}?fields=business_discovery.username(...)
  Graph API 버전은 `[확인 필요]`(설정 INSTAGRAM_GRAPH_VERSION). 값이 비면 not_configured.
- 토큰은 주소의 access_token으로 보낸다. 요청 주소는 로그에 남기지 않는다(httpx 로그는 WARNING부터).
- 개인 계정·없는 계정은 Graph가 오류로 답한다(PoC 대기: 오류 원문 확인, 17 3장). ExternalApiError로 올린다.
"""

import time
from typing import Any

import httpx
import structlog

from seelo.config import get_settings
from seelo.integrations.http import ExternalApiError, make_client

log = structlog.get_logger()

GRAPH_URL = "https://graph.facebook.com"
TIMEOUT_S = 10.0
BD_FIELDS = (
    "business_discovery.username({u})"
    "{{username,biography,website,followers_count,media_count,media.limit(10){{caption,timestamp,permalink}}}}"
)


class GraphInstagram:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def business_discovery(self, username: str) -> dict[str, Any] | None:
        s = get_settings()
        token = s.instagram_graph_token.get_secret_value()
        if not (token and s.instagram_business_account_id and s.instagram_graph_version):
            raise ExternalApiError("instagram", "not_configured")
        url = f"{GRAPH_URL}/{s.instagram_graph_version}/{s.instagram_business_account_id}"
        params = {"fields": BD_FIELDS.format(u=username), "access_token": token}
        started = time.perf_counter()
        try:
            async with make_client(TIMEOUT_S, transport=self._transport) as c:
                resp = await c.get(url, params=params)
        except httpx.HTTPError as e:
            raise ExternalApiError("instagram", type(e).__name__) from e
        ms = round((time.perf_counter() - started) * 1000)
        if resp.status_code != 200:
            err = _error(resp)
            log.info("instagram_bd_failed", status=resp.status_code, graph_code=err.get("code"), ms=ms)
            reason = f"graph_{err['code']}" if err.get("code") is not None else "request_failed"
            raise ExternalApiError("instagram", reason, resp.status_code)
        log.info("instagram_bd_call", status=resp.status_code, ms=ms)
        return resp.json().get("business_discovery")


def _error(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        return {}
    err = body.get("error") if isinstance(body, dict) else None
    return err if isinstance(err, dict) else {}
