"""웹 페이지 해석(07 6.3 5~7번, 6.5 2번). IO 없음. 원문 HTML은 저장하지 않는다."""

import re
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

TEXT_LIMIT = 20_000
_MENU = re.compile(r"(?i)(menu|메뉴|food|price|가격|dining)")
_SPACE = re.compile(r"\s+")
_INSTAGRAM = re.compile(r"^https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?(?:\?.*)?$")
_RESERVED = {"p", "reel", "reels", "explore", "stories", "accounts", "tv"}


def page_text(html: str, limit: int = TEXT_LIMIT) -> str:
    """script·style·noscript를 뺀 본문 텍스트, 공백 정리, limit자까지."""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    root = tree.body or tree.root
    text = root.text(separator=" ") if root is not None else ""
    return _SPACE.sub(" ", text).strip()[:limit]


def links(html: str, base_url: str) -> list[tuple[str, str]]:
    """(절대 주소, 링크 글자) 목록. 문서 순서."""
    out = []
    for a in HTMLParser(html).css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        out.append((urljoin(base_url, href), _SPACE.sub(" ", a.text() or "").strip()))
    return out


def find_menu_link(html: str, base_url: str) -> str | None:
    """같은 host의 링크 중 글자나 주소가 메뉴·가격 패턴에 맞는 첫 링크(자기 자신 제외)."""
    host = urlsplit(base_url).hostname
    for url, text in links(html, base_url):
        if urlsplit(url).hostname != host or url.split("#")[0] == base_url.split("#")[0]:
            continue
        if _MENU.search(text) or _MENU.search(urlsplit(url).path):
            return url
    return None


def has_english_page(html: str, base_url: str) -> bool:
    tree = HTMLParser(html)
    html_node = tree.css_first("html")
    if html_node is not None and (html_node.attributes.get("lang") or "").lower().startswith("en"):
        return True
    if tree.css_first('[hreflang^="en"]') is not None:
        return True
    for url, text in links(html, base_url):
        path = urlsplit(url).path
        if "/en/" in path or path.endswith("/en") or text.strip().lower() == "english":
            return True
    return False


def instagram_username(url: str | None) -> str | None:
    """인스타그램 프로필 주소면 사용자 이름. 게시물·탐색 등 예약 경로는 None."""
    if not url:
        return None
    m = _INSTAGRAM.match(url.strip())
    if m is None or m.group(1).lower() in _RESERVED:
        return None
    return m.group(1)
