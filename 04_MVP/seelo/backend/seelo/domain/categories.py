"""업종 판정(07 5장, D-11, W-02-4). IO 없음(규칙은 부르는 쪽이 config/categories.json에서 읽어 넘긴다)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from seelo.integrations import Place

Category = Literal["restaurant", "cafe", "bar"]
RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "categories.json"


@lru_cache
def load_rules(path: str = str(RULES_FILE)) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _google(place: Place, rules: dict[str, Any]) -> Category | None:
    g = rules["google"]
    primary = place.raw.get("primaryType")
    values = ([primary] if primary else []) + list(place.category_raw)
    for v in values:
        if v in g["bar"]["exact"]:
            return "bar"
        if v in g["cafe"]["exact"]:
            return "cafe"
        r = g["restaurant"]
        if v in r["exact"] or any(v.endswith(s) for s in r.get("suffix", [])):
            return "restaurant"
    return None


def _kakao_tokens(category_name: str) -> list[str]:
    levels = [s.strip() for s in category_name.split(">") if s.strip()]
    return [t.strip() for level in levels[-2:] for t in level.split(",") if t.strip()]


def _kakao(place: Place, rules: dict[str, Any]) -> Category | None:
    k = rules["kakao"]
    code = place.category_raw[0] if place.category_raw else ""
    name = place.category_raw[1] if len(place.category_raw) > 1 else ""
    tokens = _kakao_tokens(name)
    # 한 글자 키워드("바")는 단계 이름과 정확히 같을 때만(예: "바베큐"는 바가 아니다)
    for kw in k["barKeywords"]:
        if any(t == kw or (len(kw) >= 2 and kw in t) for t in tokens):
            return "bar"
    return k["groupCode"].get(code)


def _naver(place: Place, rules: dict[str, Any]) -> Category | None:
    n = rules["naver"]
    text = " ".join(place.category_raw)
    for cat in ("bar", "cafe", "restaurant"):
        if any(kw in text for kw in n[cat]):
            return cat  # type: ignore[return-value]
    return None


_BY_PROVIDER = {"google": _google, "kakao": _kakao, "naver": _naver}


def classify_one(place: Place, rules: dict[str, Any] | None = None) -> Category | None:
    return _BY_PROVIDER[place.provider](place, rules or load_rules())


def classify_category(places: list[Place], rules: dict[str, Any] | None = None) -> Category | None:
    """Google → 카카오 → 네이버 순으로 보고 처음 판정되는 업종. 모두 판정하지 못하면 대상 아님(None)."""
    rules = rules or load_rules()
    for provider in ("google", "kakao", "naver"):
        for p in places:
            if p.provider == provider:
                cat = _BY_PROVIDER[provider](p, rules)
                if cat is not None:
                    return cat
    return None
