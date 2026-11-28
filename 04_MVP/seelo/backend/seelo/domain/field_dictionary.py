"""지도별 칸 사전(09 3장, config/field_dictionary.json)과 칸 값 검사. 파일 읽기 말고는 IO 없음.

**정비안은 이 사전에 있는 칸만 만든다.** 가게 이름·주소·업종은 사전에 없다(DB CHECK로도 막음).
값 제한은 실제 관리 화면으로 확인해 고친다 `[PoC]`.
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from seelo.domain.attributes import ATTRIBUTES
from seelo.domain.hours import open_minutes
from seelo.domain.normalize import normalize_phone

DICTIONARY_FILE = Path(__file__).resolve().parents[2] / "config" / "field_dictionary.json"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
PLACEHOLDER = "[ ]"
_HHMM = re.compile(r"^\d{1,2}:\d{2}$")
_URL_IN_TEXT = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_IN_TEXT = re.compile(r"0\d{1,2}-?\d{3,4}-?\d{4}")


@dataclass(frozen=True)
class FieldSpec:
    provider: str
    key: str
    label: str
    type: str  # text|hours|url|phone|menu|attributes|links|services|tags
    order: int
    max_length: int | None = None
    max_items: int | None = None
    max_featured: int | None = None
    api: str | None = None
    choices: tuple[str, ...] = field(default_factory=tuple)


@lru_cache
def load_dictionary(path: str = str(DICTIONARY_FILE)) -> dict[str, dict[str, FieldSpec]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, FieldSpec]] = {}
    for provider in ("google", "kakao"):
        out[provider] = {
            key: FieldSpec(
                provider=provider,
                key=key,
                label=v["label"],
                type=v["type"],
                order=v["order"],
                max_length=v.get("maxLength"),
                max_items=v.get("maxItems"),
                max_featured=v.get("maxFeatured"),
                api=v.get("api"),
                choices=tuple(v.get("choices") or ()),
            )
            for key, v in (raw.get(provider) or {}).items()
        }
    return out


def specs(provider: str) -> list[FieldSpec]:
    """사전 순서(order)대로."""
    return sorted(load_dictionary()[provider].values(), key=lambda s: s.order)


def spec(provider: str, key: str) -> FieldSpec | None:
    return load_dictionary().get(provider, {}).get(key)


def field_label(provider: str, key: str) -> str:
    """칸 라벨(예: google regular_hours → "영업시간"). 사전에 없으면 칸 키 그대로."""
    s = spec(provider, key)
    return s.label if s else key


# --- 값 검사(09 3장 표) ----------------------------------------------------------------------


def _is_url(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    parts = urlsplit(v.strip())
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def _hours_ok(v: Any) -> bool:
    if not isinstance(v, dict) or not isinstance(v.get("days"), dict) or set(v["days"]) != set(DAYS):
        return False
    for day in v["days"].values():
        if day is None:
            continue
        if not isinstance(day, list):
            return False
        for iv in day:
            if not isinstance(iv, dict) or not all(
                _HHMM.match(str(iv.get(k, ""))) for k in ("open", "close")
            ):
                return False
    return True


def _text_reason(s: FieldSpec, v: Any) -> str | None:
    if not isinstance(v, str):
        return "bad_format"
    if PLACEHOLDER in v:
        return "placeholder_left"
    if s.max_length is not None and len(v) > s.max_length:
        return "too_long"
    if s.provider == "google" and s.key == "description":
        if _URL_IN_TEXT.search(v) or _EMAIL.search(v) or _PHONE_IN_TEXT.search(v):
            return "bad_format"
    return None


def _menu_reason(s: FieldSpec, v: Any) -> str | None:
    if not isinstance(v, list):
        return "bad_format"
    for item in v:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            return "bad_format"
        price = item.get("price")
        if price is not None and (isinstance(price, bool) or not isinstance(price, int) or price < 0):
            return "bad_format"
        if any(PLACEHOLDER in str(item.get(k) or "") for k in ("name", "nameEn", "description")):
            return "placeholder_left"
    if s.max_items is not None and len(v) > s.max_items:
        return "too_many"
    featured = sum(1 for item in v if item.get("featured"))
    if s.max_featured is not None and featured > s.max_featured:
        return "too_many"
    return None


def validate_value(s: FieldSpec, value: Any) -> str | None:
    """오류 reason(too_long·bad_format·too_many·placeholder_left) 또는 None."""
    t = s.type
    if t == "text":
        return _text_reason(s, value)
    if t == "hours":
        return None if _hours_ok(value) else "bad_format"
    if t == "url":
        return None if _is_url(value) else "bad_format"
    if t == "phone":
        if isinstance(value, str) and PLACEHOLDER in value:
            return "placeholder_left"
        digits = normalize_phone(value if isinstance(value, str) else "")
        return None if 9 <= len(digits) <= 11 else "bad_format"
    if t == "menu":
        return _menu_reason(s, value)
    if t == "attributes":
        if not isinstance(value, dict) or not value:
            return "bad_format"
        if any(k not in ATTRIBUTES or not isinstance(b, bool) for k, b in value.items()):
            return "bad_format"
        return None
    if t in ("links", "services", "tags"):
        if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
            return "bad_format"
        if s.max_items is not None and len(value) > s.max_items:
            return "too_many"
        if t == "links" and not all(_is_url(x) for x in value):
            return "bad_format"
        if t == "services" and s.choices and not all(x in s.choices for x in value):
            return "bad_format"  # 선택지 목록은 [PoC]. 비어 있으면 검사하지 않는다
        if t == "tags" and s.max_length is not None and any(len(x) > s.max_length for x in value):
            return "too_long"
        return None
    return "bad_format"


def is_incomplete(s: FieldSpec, value: Any) -> bool:
    """승인 전에 사장님이 채워야 하는 값: 비었거나 `[ ]`가 남았거나 attributes에 null이 남음."""
    if value is None or value == "" or value == [] or value == {}:
        return True
    if s.type == "attributes" and isinstance(value, dict):
        return any(v is None for v in value.values())
    return PLACEHOLDER in json.dumps(value, ensure_ascii=False)


def _norm(type_: str, v: Any) -> Any:
    if v is None:
        return None
    if type_ == "text":
        return " ".join(str(v).split())
    if type_ == "phone":
        return normalize_phone(str(v))
    if type_ == "url":
        p = urlsplit(str(v).strip())
        return (p.scheme, (p.hostname or "").lower(), p.path.rstrip("/"), p.query)
    if type_ == "links":
        return sorted(_norm("url", x) for x in v)
    if type_ in ("services", "tags"):
        return sorted(" ".join(str(x).split()) for x in v)
    if type_ == "hours":  # 실제로 여는 구간으로 비교(쉬는 시간을 따로 적었든 구간을 나눴든 같음)
        return {d: open_minutes(v, d) for d in DAYS}
    return v


def same_value(type_: str, a: Any, b: Any) -> bool:
    """정규화해서 같은가(정비안에서 바꿀 필요 없는 칸을 지울 때)."""
    return _norm(type_, a) == _norm(type_, b)
