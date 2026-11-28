"""질문에 쓸 지역(07 6.6 derive_region). IO 없음."""

import re
from typing import Any

_KO_GA = re.compile(r"\d+가$")
_KO_DONG = re.compile(r"^(\D+?)\d+동$")
_EN_TAIL = re.compile(r"[-\s]?\d.*$")
_ORDER = ("sublocality_level_2", "sublocality_level_1", "locality")


def trim_ko(s: str) -> str:
    """예: 명동2가 → 명동, 성수1동 → 성수동."""
    s = s.strip()
    s = _KO_GA.sub("", s)
    return _KO_DONG.sub(r"\1동", s)


def trim_en(s: str) -> str:
    """예: Myeong-dong 2(i)-ga → Myeong-dong."""
    return _EN_TAIL.sub("", s.strip()).strip()


def _component(payload: dict[str, Any] | None) -> str | None:
    comps = (payload or {}).get("addressComponents") or []
    for t in _ORDER:
        for c in comps:
            if t in (c.get("types") or []) and c.get("longText"):
                return c["longText"]
    return None


def from_google(ko: dict[str, Any] | None, en: dict[str, Any] | None) -> tuple[str | None, str | None]:
    k, e = _component(ko), _component(en)
    return (trim_ko(k) if k else None) or None, (trim_en(e) if e else None) or None


def from_kakao_address(address_name: str | None) -> str | None:
    """카카오 지번 주소의 세 번째 토큰("서울 중구 명동2가 25-2" → "명동")."""
    tokens = (address_name or "").split()
    return (trim_ko(tokens[2]) or None) if len(tokens) >= 3 else None
