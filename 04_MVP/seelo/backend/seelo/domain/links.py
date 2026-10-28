"""링크 뽑기·판별(07 2장, 14 2.2, W-02-2). IO 없음. 짧은 링크 따라가기는 integrations/http.py."""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote_plus, urlsplit

from seelo.errors import AppError

_URL = re.compile(r"https?://[^\s<>\"'　]+")
_BARE_SHORT = re.compile(r"(?<![\w/.])((?:maps\.app\.goo\.gl|goo\.gl/maps|naver\.me|kko\.to)/[^\s<>\"'　]+)")
_TRAIL = ".,!?)]}>\"'」』】》"
_GOOGLE_HOSTS = {"google.com", "www.google.com", "maps.google.com", "google.co.kr", "www.google.co.kr"}
_PIN = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_CENTER = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")


@dataclass
class LinkInfo:
    provider: Literal["google", "kakao", "naver"]
    kind: Literal["long", "short"]
    url: str
    external_id: str | None = None
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    place_id: str | None = None


def extract_urls(text: str) -> list[str]:
    """공유 문구에서 URL을 순서대로 뽑는다. 스킴 없는 짧은 링크도 받는다(07 2.1)."""
    found: list[tuple[int, str]] = []
    for m in _URL.finditer(text):
        found.append((m.start(), m.group(0).rstrip(_TRAIL)))
    for m in _BARE_SHORT.finditer(text):
        # https://가 붙은 것은 위에서 이미 뽑았다
        if not text[max(0, m.start() - 8) : m.start()].endswith("://"):
            found.append((m.start(), "https://" + m.group(1).rstrip(_TRAIL)))
    return [u for _, u in sorted(found)]


def _q(query: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query).items() if v}


def _google(url: str, host: str, path: str, q: dict[str, str]) -> LinkInfo | None:
    if host in ("maps.app.goo.gl",) or (host == "goo.gl" and path.startswith("/maps")):
        return LinkInfo("google", "short", url)
    if host not in _GOOGLE_HOSTS or not path.startswith("/maps"):
        return None
    if q.get("query_place_id"):
        return LinkInfo("google", "long", url, place_id=q["query_place_id"])
    m = re.match(r"/maps/place/([^/]+)", path)
    if m:
        info = LinkInfo("google", "long", url, name=unquote_plus(m.group(1)))
        coord = _PIN.search(url) or _CENTER.search(url)  # 가게 위치(!3d!4d)를 지도 중심(@)보다 먼저
        if coord:
            info.lat, info.lng = float(coord.group(1)), float(coord.group(2))
        return info
    m = re.match(r"/maps/search/([^/]+)", path)
    if m:
        return LinkInfo("google", "long", url, name=unquote_plus(m.group(1)))
    if q.get("q") or q.get("query"):
        return LinkInfo("google", "long", url, name=q.get("q") or q.get("query"))
    return None


def _kakao(url: str, host: str, path: str, q: dict[str, str]) -> LinkInfo | None:
    if host == "kko.to":
        return LinkInfo("kakao", "short", url)
    pid: str | None = None
    if host == "place.map.kakao.com":
        m = re.match(r"/(?:m/)?(\d+)", path)
        pid = m.group(1) if m else None
    elif host == "map.kakao.com":
        m = re.match(r"/link/map/(\d+)", path)
        pid = q.get("itemId") if q.get("itemId", "").isdigit() else (m.group(1) if m else None)
    elif host == "m.map.kakao.com":
        pid = q.get("id") if q.get("id", "").isdigit() else None  # [확인 필요] 07 2.2
    return LinkInfo("kakao", "long", url, external_id=pid) if pid else None


def _naver(url: str, host: str, path: str) -> LinkInfo | None:
    if host == "naver.me":
        return LinkInfo("naver", "short", url)
    m = None
    if host == "map.naver.com":
        m = re.search(r"/place/(\d+)", path)
    elif host in ("m.place.naver.com", "place.naver.com", "pcmap.place.naver.com"):
        m = re.match(r"/[A-Za-z]+/(\d+)", path)
    return LinkInfo("naver", "long", url, external_id=m.group(1)) if m else None


def classify(url: str) -> LinkInfo | None:
    """지원하는 지도 링크면 LinkInfo. 가게를 가리키지 않는 지도 링크(번호 없음)도 None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    q = _q(parts.query)
    return (
        _google(url, host, parts.path, q) or _kakao(url, host, parts.path, q) or _naver(url, host, parts.path)
    )


def pick_supported(text: str) -> LinkInfo:
    """첫 지원 링크. URL이 없으면 NO_LINK, 지원하는 것이 없으면 UNSUPPORTED_LINK."""
    urls = extract_urls(text)
    if not urls:
        raise AppError("NO_LINK")
    for u in urls:
        info = classify(u)
        if info is not None:
            return info
    raise AppError("UNSUPPORTED_LINK")
