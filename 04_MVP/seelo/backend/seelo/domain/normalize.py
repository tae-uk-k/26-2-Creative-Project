"""정규화(07 1장, 14 2.1). IO 없음."""

import re
import unicodedata
from typing import Literal
from urllib.parse import urlsplit

from rapidfuzz import fuzz

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOT_WORD = re.compile(r"[^0-9a-z가-힣]")  # casefold 뒤라 영문은 소문자만
_KO_SUFFIX = re.compile(r"(본점|직영점)$")
_EN_BRANCH = re.compile(r"\s+(?:main\s+branch|branch|\S+\s+branch|\S+\s+store)$", re.IGNORECASE)
_ADDRESS = re.compile(r"([가-힣A-Za-z0-9]+(?:로|길))\s*(\d+(?:-\d+)?)")


def _strip_branch(s: str) -> str:
    tokens = s.split()
    # 공백으로 나눈 마지막 토큰이 "점"으로 끝나고 2자 이상이면 지점 표기(예: "명동본점", "명동점")
    if len(tokens) >= 2 and tokens[-1].endswith("점") and len(tokens[-1]) >= 2:
        tokens = tokens[:-1]
    s = " ".join(tokens)
    s = _KO_SUFFIX.sub("", s).strip()
    prev = None
    while prev != s:  # "Seongsu Branch" 같은 끝 표기를 한 번 더 지울 수 있게
        prev = s
        s = _EN_BRANCH.sub("", s).strip()
    return s


def _only_words(s: str) -> str:
    return _NOT_WORD.sub("", s.casefold())


def normalize_name(s: str) -> str:
    """① NFKC ② 괄호 삭제 ③ 지점 표기 삭제 ④ casefold ⑤ 한글·영문·숫자만. 빈 문자열이면 ⑤만."""
    base = unicodedata.normalize("NFKC", s or "")
    cleaned = _only_words(_strip_branch(_BRACKETS.sub(" ", base)))
    return cleaned or _only_words(base)


def normalize_phone(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip()
    digits = re.sub(r"\D", "", s)
    if s.startswith("+82"):
        digits = "0" + digits[2:]
    return digits


def normalize_address(s: str | None) -> tuple[str, str] | None:
    """도로명 주소에서 (도로명, 건물번호). 지번 주소 등 못 뽑으면 None(비교하지 않음)."""
    if not s:
        return None
    m = _ADDRESS.search(unicodedata.normalize("NFKC", s))
    return (m.group(1), m.group(2)) if m else None


def domain_of(url: str) -> str:
    host = (urlsplit(url if "://" in url else f"https://{url}").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def map_kind(domain: str, url: str = "") -> Literal["google_maps", "kakao_map", "naver_map"] | None:
    d = domain.lower().removeprefix("www.")
    path = urlsplit(url).path if url else ""
    if d in ("maps.google.com", "maps.app.goo.gl") or (d == "goo.gl" and path.startswith("/maps")):
        return "google_maps"
    if d in ("google.com", "google.co.kr") and path.startswith("/maps"):
        return "google_maps"
    if d in ("map.kakao.com", "place.map.kakao.com", "m.map.kakao.com", "kko.to"):
        return "kakao_map"
    if d in ("map.naver.com", "m.place.naver.com", "place.naver.com", "pcmap.place.naver.com", "naver.me"):
        return "naver_map"
    return None


def name_similarity(a: str, b: str) -> int:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 2 and short in long_:
        return 100
    return round(fuzz.ratio(na, nb))


def same_name(a: str, b: str, threshold: int) -> bool:
    return name_similarity(a, b) >= threshold
