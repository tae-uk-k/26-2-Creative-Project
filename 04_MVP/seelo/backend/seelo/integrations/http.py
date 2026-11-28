"""공용 HTTP 클라이언트와 짧은 링크 따라가기(01 7.4, 07 2.3).

- 클라이언트는 make_client()로만 만든다(제한 시간·User-Agent 통일).
- 짧은 링크는 리디렉션을 자동으로 따라가지 않고, Location을 한 번에 하나씩 확인한다.
  지도·짧은 링크 호스트가 아닌 곳으로 가는 Location은 따라가지 않는다(내부 주소로 유도하는 요청 방지).
"""

import asyncio
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
import structlog

from seelo.config import get_settings
from seelo.domain.links import LinkInfo, classify
from seelo.domain.normalize import map_kind
from seelo.errors import AppError

log = structlog.get_logger()

MAP_API_TIMEOUT_S = 5.0
SHORT_LINK_MAX_HOPS = 3
SHORT_LINK_TIMEOUT_S = 5.0


class ExternalApiError(Exception):
    """지도 API 오류(5xx·429·연결·시간 초과·예상 밖 4xx). 가게 찾기에서는 503 TRY_LATER가 된다."""

    def __init__(self, provider: str, reason: str, status: int | None = None) -> None:
        self.provider, self.reason, self.status = provider, reason, status
        super().__init__(f"{provider}: {reason}" + (f" ({status})" if status else ""))


def make_client(
    timeout_s: float,
    *,
    follow_redirects: bool = False,
    headers: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout_s,
        follow_redirects=follow_redirects,
        headers={"User-Agent": get_settings().website_user_agent, **(headers or {})},
        transport=transport,
    )


def _may_follow(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and (
        map_kind(host, url) is not None or host == "consent.google.com"
    )


class HttpShortLinkResolver:
    """HEAD(안 되면 GET stream, 본문은 읽지 않음)로 Location만 본다. 최대 3번, 전체 5초."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def resolve(self, link: LinkInfo) -> LinkInfo:
        try:
            async with asyncio.timeout(SHORT_LINK_TIMEOUT_S):
                return await self._follow(link.url)
        except (TimeoutError, httpx.HTTPError) as e:
            log.info("short_link_unresolved", provider=link.provider, reason=type(e).__name__)
            raise AppError("LINK_UNRESOLVED") from e

    async def _location(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        resp = await client.head(url)
        if resp.status_code in (400, 405):
            async with client.stream("GET", url) as streamed:
                return streamed  # 상태·헤더만 쓰고 본문은 읽지 않는다
        return resp

    async def _follow(self, url: str) -> LinkInfo:
        async with make_client(SHORT_LINK_TIMEOUT_S, transport=self._transport) as client:
            for _ in range(SHORT_LINK_MAX_HOPS):
                resp = await self._location(client, url)
                location = resp.headers.get("location")
                if not resp.is_redirect or not location:
                    break
                nxt = urljoin(url, location)
                if (urlsplit(nxt).hostname or "").lower() == "consent.google.com":
                    nxt = parse_qs(urlsplit(nxt).query).get("continue", [""])[0]  # [확인 필요] 07 2.3
                if not _may_follow(nxt):
                    break
                info = classify(nxt)
                if info is not None and info.kind == "long":
                    return info
                url = nxt
        raise AppError("LINK_UNRESOLVED")
