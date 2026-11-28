"""공식 웹사이트 읽기(07 6.3, W-03-3). 크롤링하지 않는다: 첫 페이지와 메뉴 페이지 1개만.

- robots.txt(RFC 9309): 2xx면 해석, 4xx면 모두 허용, 5xx·시간 초과·연결 오류면 모두 금지.
  금지면 본문 요청 0번.
- 본문: GET 10초, 리디렉션 최대 3번(옮겨 간 주소도 robots 확인), text/html만, 1MB 넘으면 중단.
- 공인 주소가 아니면(사설·루프백·링크 로컬 등) 요청하지 않는다.
  가게 정보의 websiteUri로 내부망을 찌르는 요청을 막으려고.
  DNS 응답이 요청 직전에 바뀌는 경우까지는 막지 못한다(추론: 베타 범위에서 감수).
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from seelo.integrations import FetchedPage, RobotsResult
from seelo.integrations.http import make_client

log = structlog.get_logger()

ROBOTS_AGENT = "SeeloBot"
ROBOTS_TIMEOUT_S = 5.0
ROBOTS_MAX_BYTES = 500 * 1024  # RFC 9309: 최소 500KiB까지 읽는다
ROBOTS_MAX_REDIRECTS = 5
PAGE_TIMEOUT_S = 10.0
PAGE_MAX_BYTES = 1_000_000
PAGE_MAX_REDIRECTS = 3
_META_CHARSET = re.compile(rb"""charset=["']?([A-Za-z0-9_-]+)""", re.IGNORECASE)

Resolver = Callable[[str], Awaitable[list[str]]]


class WebsiteError(Exception):
    """reason: robots_disallowed | blocked_host | timeout | connect_error | http_error | not_html | too_large
    | too_many_redirects"""

    def __init__(self, reason: str, status: int | None = None) -> None:
        self.reason, self.status = reason, status
        super().__init__(reason + (f" ({status})" if status else ""))


async def system_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


class HttpWebsiteFetcher:
    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, resolver: Resolver | None = None
    ) -> None:
        self._transport = transport
        self._resolve = resolver or system_resolver

    async def _public(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in ("http", "https") or not host:
            return False
        try:
            ips = [host] if _is_ip(host) else await self._resolve(host)
        except OSError:
            return False
        return bool(ips) and all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in ips)

    def _client(self, timeout_s: float) -> httpx.AsyncClient:
        return make_client(timeout_s, transport=self._transport)

    # --- robots.txt -----------------------------------------------------------------

    async def robots_allows(self, url: str) -> RobotsResult:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            async with asyncio.timeout(ROBOTS_TIMEOUT_S), self._client(ROBOTS_TIMEOUT_S) as c:
                for _ in range(ROBOTS_MAX_REDIRECTS + 1):
                    if not await self._public(robots_url):
                        return RobotsResult(False, "blocked_host")
                    async with c.stream("GET", robots_url) as resp:
                        if resp.is_redirect:
                            robots_url = urljoin(robots_url, resp.headers["location"])
                            continue
                        status = resp.status_code
                        body = (
                            await _read_limited(resp, ROBOTS_MAX_BYTES, truncate=True)
                            if status < 300
                            else b""
                        )
                    break
                else:  # 리디렉션이 5번을 넘으면 robots.txt가 없는 것으로 본다(RFC 9309 2.3.1.2)
                    return RobotsResult(True, "robots_unavailable")
        except (TimeoutError, httpx.HTTPError):
            return RobotsResult(False, "robots_error")
        if status >= 500:
            return RobotsResult(False, "robots_5xx")
        if status >= 400:
            return RobotsResult(True, "robots_4xx")
        parser = RobotFileParser()
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        allowed = parser.can_fetch(ROBOTS_AGENT, url)
        return RobotsResult(allowed, "ok" if allowed else "disallowed")

    # --- 본문 ----------------------------------------------------------------------

    async def fetch(self, url: str) -> FetchedPage:
        """robots 허용을 이미 확인한 첫 주소에서 시작한다.

        리디렉션으로 옮겨 간 주소의 robots는 여기서 다시 확인한다.
        """
        try:
            async with asyncio.timeout(PAGE_TIMEOUT_S), self._client(PAGE_TIMEOUT_S) as c:
                for hop in range(PAGE_MAX_REDIRECTS + 1):
                    if not await self._public(url):
                        raise WebsiteError("blocked_host")
                    if hop > 0 and not (await self.robots_allows(url)).allowed:
                        raise WebsiteError("robots_disallowed")
                    async with c.stream("GET", url) as resp:
                        if resp.is_redirect:
                            url = urljoin(url, resp.headers["location"])
                            continue
                        if resp.status_code >= 400:
                            raise WebsiteError("http_error", resp.status_code)
                        if "text/html" not in resp.headers.get("content-type", "").lower():
                            raise WebsiteError("not_html")
                        raw = await _read_limited(resp, PAGE_MAX_BYTES)
                        return FetchedPage(
                            url=str(resp.url), html=_decode(raw, resp), status=resp.status_code
                        )
                raise WebsiteError("too_many_redirects")
        except TimeoutError as e:
            raise WebsiteError("timeout") from e
        except httpx.HTTPError as e:
            raise WebsiteError("connect_error") from e


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


async def _read_limited(resp: httpx.Response, limit: int, *, truncate: bool = False) -> bytes:
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > limit:
            if truncate:
                return bytes(buf[:limit])
            raise WebsiteError("too_large")
    return bytes(buf)


def _decode(raw: bytes, resp: httpx.Response) -> str:
    """헤더 charset → HTML meta charset → utf-8 순. 한국 사이트의 euc-kr도 읽는다."""
    enc = resp.charset_encoding
    if not enc:
        m = _META_CHARSET.search(raw[:4096])
        enc = m.group(1).decode() if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")
