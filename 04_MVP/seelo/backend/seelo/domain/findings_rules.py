"""고쳐야 할 점 판정(08 6장, W-07). IO 없음.

- 코드 규칙으로 판정한다. LLM은 D5(AI가 틀리게 말함)의 문장 비교에만 쓰고, 그 호출은 서비스가 한다
  (여기서는 비교할 묶음 `claim_checks`와 결과 반영 `ai_wrong_drafts`만).
- 판정에 필요한 출처 값이 없으면 그 규칙은 판정하지 않는다.
- Google 지도·카카오맵에서 고칠 수 있는 것만 만든다(인스타그램·외부 사이트 쪽 문제는 만들지 않음).
- **카카오·네이버 값은 evidence에 넣지 않는다**(`{"source": "naver", "valueStored": false}`처럼 출처만).
- 진단 단계 카카오는 기본정보(이름·주소·전화)만 쓴다. 정비안 단계 규칙(6.5)은 11단계에서 더한다.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from seelo.domain.attributes import ATTRIBUTES, KAKAO_KEYWORD
from seelo.domain.hours import from_google_periods, hours_diff
from seelo.domain.labels import AI_LABEL, MAP_LABEL, PRICE_LEVEL_LABEL, SOURCE_LABEL
from seelo.domain.metrics import ResponseView
from seelo.domain.normalize import (
    domain_of,
    name_similarity,
    normalize_address,
    normalize_name,
    normalize_phone,
)
from seelo.integrations import Place

CATEGORY_ORDER = ["map_missing", "condition_missing", "ai_wrong", "source_mismatch", "english_missing"]
BASE_KEYS = {  # D2 업종별 기본 편의 키
    "restaurant": ["vegetarian", "card_payment", "reservation", "takeout"],
    "cafe": ["card_payment", "takeout", "outdoor_seating"],
    "bar": ["card_payment", "reservation", "alcohol"],
}
NO_GOOGLE_FIELD = frozenset({"halal", "english_menu"})  # Google에 칸이 없어 고칠 수 없음
CLAIM_FIELD = {"hours": "regular_hours", "phone": "phone", "price": "menu", "location": "address"}
ALL_QUESTION_FIELDS = frozenset({"listing", "regular_hours", "phone", "website"})


@dataclass
class TargetClaim:
    """우리 가게에 대한 AI 답변의 사실 주장(ai_responses.target_claims 한 줄)."""

    response_id: int
    provider: str
    question_id: int
    field: str  # hours|location|price|phone
    value: str


@dataclass
class FindingInputs:
    category: str
    google_found: bool
    kakao_found: bool
    google: dict[str, Any] | None  # 스냅샷 ko payload(상태 ok일 때)
    kakao_basic: Place | None  # 다시 부르기(진단: 기본정보). 판정에만 쓰고 저장하지 않음
    naver_basic: Place | None  # 다시 부르기. 판정에만 쓰고 저장하지 않음
    website: dict[str, Any] | None  # 웹사이트 스냅샷의 extract(WebsiteExtract)
    web_sites: list[dict[str, Any]]  # web_evidence.fields(EvidenceSite)
    question_ids: list[int]
    question_features: dict[int, list[str]]  # question_id → 조건 키
    responses: list[ResponseView]
    claims: list[TargetClaim]
    competitors: list[str]  # 주변 가게 정규화 이름(최대 5)
    competitor_facts: dict[str, dict[str, Any]] | None  # 6.6. 조회 실패면 None
    name_threshold: int = 85
    plan_values: dict[str, Any] | None = None  # 정비안 단계(11단계)


@dataclass
class FindingDraft:
    stage: str
    category: str
    title_key: str
    provider: str
    field: str
    competitor_count: int = 0
    question_count: int = 0
    priority: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)


def _draft(
    category: str, provider: str, field_: str, key: str | None = None, **evidence: Any
) -> FindingDraft:
    return FindingDraft(
        stage="diagnosis",
        category=category,
        title_key=f"{category}.{key or field_}",
        provider=provider,
        field=field_,
        evidence=evidence,
    )


# --- D1·D2 지도에 정보 없음 ---------------------------------------------------------------


def _map_missing(inp: FindingInputs) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    if not inp.google_found:
        out.append(_draft("map_missing", "google", "listing"))
    if not inp.kakao_found:
        out.append(_draft("map_missing", "kakao", "listing"))
    g = inp.google
    if g is None:  # 스냅샷이 없거나 실패면 D2를 판정하지 않는다
        return out
    if not g.get("regularOpeningHours"):
        out.append(_draft("map_missing", "google", "regular_hours"))
    if not g.get("websiteUri"):
        out.append(_draft("map_missing", "google", "website"))
    if not g.get("nationalPhoneNumber"):
        out.append(_draft("map_missing", "google", "phone"))
    if g.get("priceLevel") is None and not g.get("priceRange"):
        out.append(_draft("map_missing", "google", "menu"))
    missing = [k for k in BASE_KEYS.get(inp.category, []) if ATTRIBUTES[k].google(g) is None]
    if missing:
        out.append(_draft("map_missing", "google", "attributes", missingKeys=missing))
    return out


# --- D3 출처끼리 정보 다름(6.3.1) -----------------------------------------------------------


@dataclass
class _Other:
    source: str  # website | web:<domain> | naver
    value: str
    stored: bool  # evidence에 값을 넣어도 되는가(네이버는 거짓)


def _differs(field_: str, mine: str, theirs: str, threshold: int) -> tuple[bool, Any]:
    """(다른가, 서로 같은 값끼리 묶을 키)."""
    if field_ == "name":
        return name_similarity(mine, theirs) < threshold, normalize_name(theirs)
    if field_ == "address":
        a, b = normalize_address(mine), normalize_address(theirs)
        return a is not None and b is not None and a != b, b
    pa, pb = normalize_phone(mine), normalize_phone(theirs)
    return bool(pa and pb and pa != pb), pb


def _others(inp: FindingInputs, field_: str) -> list[_Other]:
    out: list[_Other] = []
    site_key = {"name": None, "address": "address", "phone": "phone"}[field_]
    if inp.website and site_key and inp.website.get(site_key):
        out.append(_Other("website", inp.website[site_key], True))
    seen: set[str] = set()
    for s in inp.web_sites:
        d = domain_of(s.get("url") or "")
        if d in seen or not s.get(field_):
            continue
        seen.add(d)
        out.append(_Other(f"web:{d}", s[field_], True))
    naver_val = {"name": inp.naver_basic.name, "address": inp.naver_basic.address} if inp.naver_basic else {}
    if naver_val.get(field_):  # 네이버 API는 전화번호를 주지 않는다
        out.append(_Other("naver", naver_val[field_], False))
    return out


def _source_mismatch_field(
    inp: FindingInputs, provider: str, field_: str, map_value: str | None
) -> FindingDraft | None:
    if not map_value:
        return None  # 지도 값이 없으면 D2
    differing = []
    groups: dict[Any, int] = defaultdict(int)
    for o in _others(inp, field_):
        diff, key = _differs(field_, map_value, o.value, inp.name_threshold)
        if diff:
            differing.append(o)
            groups[key] += 1
    website_differs = any(o.source == "website" for o in differing)
    if not (website_differs or any(n >= 2 for n in groups.values())):
        return None  # 웹 검색 사이트 1곳이나 네이버 혼자 다르면 만들지 않는다
    evidence: dict[str, Any] = {
        "sources": [
            {"source": o.source, "valueStored": o.stored, **({"value": o.value} if o.stored else {})}
            for o in differing
        ]
    }
    if provider == "google":  # 카카오 지도 값은 저장하지 않는다
        evidence = {"mapValue": map_value, **evidence}
    return _draft("source_mismatch", provider, field_, **evidence)


def _hours_mismatch(inp: FindingInputs) -> FindingDraft | None:
    g, site = inp.google or {}, inp.website or {}
    periods = (g.get("regularOpeningHours") or {}).get("periods")
    if not periods or not site.get("hours"):
        return None
    days = hours_diff(site["hours"], from_google_periods(periods))
    if not days:
        return None
    return _draft(
        "source_mismatch",
        "google",
        "regular_hours",
        mapValue="\n".join((g.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []) or None,
        sources=[{"source": "website", "value": site.get("hours_text"), "valueStored": True}],
        days=days,
    )


def _source_mismatch(inp: FindingInputs) -> list[FindingDraft]:
    out: list[FindingDraft | None] = []
    if inp.google is not None:
        g = inp.google
        out.append(_source_mismatch_field(inp, "google", "name", (g.get("displayName") or {}).get("text")))
        out.append(_source_mismatch_field(inp, "google", "address", g.get("formattedAddress")))
        out.append(_source_mismatch_field(inp, "google", "phone", g.get("nationalPhoneNumber")))
        out.append(_hours_mismatch(inp))
    if inp.kakao_basic is not None:
        k = inp.kakao_basic
        out.append(_source_mismatch_field(inp, "kakao", "name", k.name))
        out.append(_source_mismatch_field(inp, "kakao", "address", k.address))
        out.append(_source_mismatch_field(inp, "kakao", "phone", k.phone))
    return [d for d in out if d is not None]


# --- D4 질문 조건 정보 부족 -----------------------------------------------------------------


def recommended_with(inp: FindingInputs, key: str, question_id: int | None = None) -> dict[str, str]:
    """그 조건 키를 추천 이유로 받은 주변 가게 {정규화 이름: 이름}(question_id가 있으면 그 질문 답변만)."""
    comps = set(inp.competitors)
    out: dict[str, str] = {}
    for r in inp.responses:
        if not r.extraction_ok or (question_id is not None and r.question_id != question_id):
            continue
        for x in r.recs:
            if not x.is_target and x.normalized_name in comps and key in x.mentioned_attributes:
                out.setdefault(x.normalized_name, x.name)
    return out


def _condition_missing(inp: FindingInputs) -> list[FindingDraft]:
    if inp.google is None:
        return []
    out: list[FindingDraft] = []
    keys: dict[str, list[int]] = defaultdict(list)
    for q in inp.question_ids:
        for k in inp.question_features.get(q, []):
            keys[k].append(q)
    for k, qids in keys.items():
        if k in NO_GOOGLE_FIELD or k not in ATTRIBUTES or ATTRIBUTES[k].google(inp.google) is not None:
            continue  # 거짓은 사실, 참은 이미 있음
        recommended: dict[str, str] = {}
        for q in qids:
            recommended.update(recommended_with(inp, k, q))
        if not recommended:
            continue
        field_ = "menu" if k == "budget" else "attributes"
        out.append(
            _draft(
                "condition_missing",
                "google",
                field_,
                key=k,
                conditionKey=k,
                questionIds=qids,
                competitors=list(recommended.values()),
            )
        )
    return out


# --- D5 AI가 틀리게 말함(6.4) ---------------------------------------------------------------


@dataclass
class ClaimCheck:
    """LLM으로 비교할 한 묶음: 같은 (칸, 주장 문장)의 응답들."""

    claim_field: str  # hours|phone|price|location
    claim: str
    truth: str
    map_value: str | None
    claims: list[TargetClaim]


def _won(n: int) -> str:
    return f"{n:,}원"


def _truth(website: dict[str, Any], claim_field: str) -> str | None:
    if claim_field == "hours":
        return website.get("hours_text")
    if claim_field == "phone":
        return website.get("phone")
    if claim_field == "location":
        return website.get("address")
    priced = [m for m in website.get("menu") or [] if m.get("price") is not None and m.get("name")]
    return ", ".join(f"{m['name']} {_won(m['price'])}" for m in priced) or None


def google_price_text(g: dict[str, Any]) -> str | None:
    level = PRICE_LEVEL_LABEL.get(g.get("priceLevel") or "")
    pr = g.get("priceRange") or {}
    lo, hi = (pr.get("startPrice") or {}).get("units"), (pr.get("endPrice") or {}).get("units")
    rng = f"{_won(int(lo)) if lo else ''}~{_won(int(hi)) if hi else ''}" if (lo or hi) else None
    return " ".join(x for x in (level, rng) if x) or None


def _map_value(g: dict[str, Any] | None, claim_field: str) -> str | None:
    if not g:
        return None
    if claim_field == "hours":
        return "\n".join((g.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []) or None
    if claim_field == "phone":
        return g.get("nationalPhoneNumber")
    if claim_field == "location":
        return g.get("formattedAddress")
    return google_price_text(g)


def claim_checks(inp: FindingInputs) -> list[ClaimCheck]:
    """우리 가게가 등장한 응답의 주장 중 웹사이트 정답이 있는 것만. 같은 문장은 한 번만 비교한다."""
    if not inp.website:
        return []  # 정답이 지도 값이면 원인이 지도라고 할 수 없다
    appeared = {r.response_id for r in inp.responses if r.extraction_ok and any(x.is_target for x in r.recs)}
    groups: dict[tuple[str, str], ClaimCheck] = {}
    for c in inp.claims:
        if c.response_id not in appeared or c.field not in CLAIM_FIELD or not c.value.strip():
            continue
        truth = _truth(inp.website, c.field)
        if not truth:
            continue
        key = (c.field, " ".join(c.value.split()).casefold())
        if key not in groups:
            groups[key] = ClaimCheck(c.field, c.value.strip(), truth, _map_value(inp.google, c.field), [])
        groups[key].claims.append(c)
    return list(groups.values())


def ai_wrong_drafts(checks: list[ClaimCheck], results: list[tuple[bool, bool | None]]) -> list[FindingDraft]:
    """claimMatchesTruth = false이고 (claimMatchesMap = true 또는 지도 값 없음)이면 finding. 칸별로 묶는다."""
    by_field: dict[str, list[ClaimCheck]] = defaultdict(list)
    for check, (matches_truth, matches_map) in zip(checks, results, strict=True):
        if not matches_truth and (check.map_value is None or matches_map is True):
            by_field[CLAIM_FIELD[check.claim_field]].append(check)
    out = []
    for field_, wrong in by_field.items():
        claims = [c for ch in wrong for c in ch.claims]
        out.append(
            _draft(
                "ai_wrong",
                "google",
                field_,
                responseIds=sorted({c.response_id for c in claims}),
                providers=sorted({c.provider for c in claims}),
                questionIds=sorted({c.question_id for c in claims}),
                claims=list(dict.fromkeys(ch.claim for ch in wrong))[:3],
                truth=wrong[0].truth,
            )
        )
    return out


# --- 진단 단계 전체 -------------------------------------------------------------------------


def judge_diagnosis(inp: FindingInputs) -> list[FindingDraft]:
    """D1~D4(코드 규칙). D5는 서비스가 claim_checks → LLM → ai_wrong_drafts로 더한다."""
    return _map_missing(inp) + _source_mismatch(inp) + _condition_missing(inp)


# --- 6.5 정비안 단계(stage plan, 연결 뒤 읽은 지금 값으로 그 지도만) ------------------------------

KAKAO_PLAN_FIELDS = ("intro", "hours", "price_items", "links", "services", "tags")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _plan_draft(
    category: str, provider: str, field_: str, key: str | None = None, **evidence: Any
) -> FindingDraft:
    d = _draft(category, provider, field_, key, **evidence)
    d.stage = "plan"
    return d


def judge_plan(inp: FindingInputs, provider: str, existing: list[FindingDraft]) -> list[FindingDraft]:
    """P1~P8. 지금 값을 읽지 않았으면(plan_values가 None이거나 모두 None) 건너뛴다.

    카카오 지금 값은 판정에만 쓰고 evidence에 넣지 않는다(그 값은 fix_plan_items.current_value로만).
    진단 단계에 같은 (provider, field, category)가 있으면 다시 만들지 않는다.
    """
    pv = inp.plan_values
    if not pv or all(v is None for v in pv.values()):
        return []
    out: list[FindingDraft] = []
    if provider == "google":
        desc, menu = pv.get("description"), pv.get("menu")
        if _empty(desc):
            out.append(_plan_draft("map_missing", "google", "description"))  # P1
        elif len(_LATIN_WORD.findall(str(desc))) < 5:
            out.append(_plan_draft("english_missing", "google", "description"))  # P3
        if _empty(menu):
            out.append(_plan_draft("map_missing", "google", "menu"))  # P2(음식점·카페·바는 메뉴를 지원)
        elif sum(1 for m in menu if isinstance(m, dict) and m.get("nameEn")) * 2 < len(menu):
            out.append(_plan_draft("english_missing", "google", "menu"))  # P4
        attrs = pv.get("attributes") if isinstance(pv.get("attributes"), dict) else None
        if attrs is not None:  # P8: D4를 지금 값(편의 정보)으로 다시
            for d in _condition_missing(replace(inp, google=_attrs_as_google(attrs))):
                d.stage = "plan"
                out.append(d)
    else:
        for f in KAKAO_PLAN_FIELDS:  # P5
            if _empty(pv.get(f)):
                out.append(_plan_draft("map_missing", "kakao", f, valueStored=False))
        site_hours = (inp.website or {}).get("hours")
        if site_hours and isinstance(pv.get("hours"), dict) and hours_diff(pv["hours"], site_hours):  # P6
            out.append(
                _plan_draft(
                    "source_mismatch", "kakao", "hours", "regular_hours",
                    sources=[{"source": "website", "value": (inp.website or {}).get("hours_text"),
                              "valueStored": True}],
                    mapValueStored=False,
                )
            )  # fmt: skip
        words = " ".join(str(x) for f in ("services", "tags") for x in (pv.get(f) or []))
        for q in inp.question_ids:  # P7
            for k in inp.question_features.get(q, []):
                kw = KAKAO_KEYWORD.get(k)
                if kw and kw not in words and recommended_with(inp, k, q):
                    out.append(_plan_draft("condition_missing", "kakao", "services", k, conditionKey=k,
                                           questionIds=[q], valueStored=False))  # fmt: skip
    seen = {(d.provider, d.field, d.category) for d in existing}
    result: list[FindingDraft] = []
    for d in out:
        key = (d.provider, d.field, d.category)
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _attrs_as_google(attrs: dict[str, Any]) -> dict[str, Any]:
    """정비안 attributes 지금 값({조건 키: bool|None}) → D4가 읽는 Google 필드 모양."""
    g: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None or k not in ATTRIBUTES:
            continue
        if k == "budget":
            g["priceLevel"] = "PRICE_LEVEL_INEXPENSIVE" if v else "PRICE_LEVEL_EXPENSIVE"
        elif k == "card_payment":
            g["paymentOptions"] = {"acceptsCreditCards": v}
        elif k == "alcohol":
            g["servesBeer"] = v
        elif k == "wheelchair":
            g["accessibilityOptions"] = {"wheelchairAccessibleEntrance": v}
        else:
            g[_GOOGLE_FIELD[k]] = v
    return g


_GOOGLE_FIELD = {
    "vegetarian": "servesVegetarianFood",
    "reservation": "reservable",
    "takeout": "takeout",
    "delivery": "delivery",
    "kid_friendly": "goodForChildren",
    "group_friendly": "goodForGroups",
    "outdoor_seating": "outdoorSeating",
    "pet_friendly": "allowsDogs",
}


# --- 6.6 영향 순서 ------------------------------------------------------------------------

_FACT = {
    "regular_hours": lambda f: bool(f.get("regularOpeningHours")),
    "website": lambda f: bool(f.get("websiteUri")),
    "phone": lambda f: bool(f.get("nationalPhoneNumber")),
    "menu": lambda f: f.get("priceLevel") is not None,
}


def _keys_of(d: FindingDraft) -> list[str]:
    if d.category == "condition_missing":
        return [d.evidence["conditionKey"]]
    if d.field == "attributes":
        return list(d.evidence.get("missingKeys", []))
    return []


def _competitor_count(d: FindingDraft, inp: FindingInputs) -> tuple[int, bool]:
    """(그 정보를 갖춘 주변 가게 수, 근거 부족)."""
    if d.category not in ("map_missing", "condition_missing"):
        return 0, False
    if d.field == "listing":
        return len(inp.competitors), False  # 주변 가게는 모두 지도에 있음
    facts = inp.competitor_facts
    keys = _keys_of(d)
    have = 0
    if facts is not None:
        for f in facts.values():
            if keys:
                have += any(ATTRIBUTES[k].google(f) is True for k in keys if k in ATTRIBUTES)
            elif d.field in _FACT:
                have += _FACT[d.field](f)
    if d.category == "condition_missing":
        have = max(have, len(recommended_with(inp, keys[0])))
    return have, facts is None


def _question_count(d: FindingDraft, inp: FindingInputs) -> int:
    if d.category == "ai_wrong":
        return len(d.evidence.get("questionIds", []))
    keys = _keys_of(d)
    if keys:
        qs = {q for q in inp.question_ids if set(inp.question_features.get(q, [])) & set(keys)}
        for k in keys:
            qs |= {r.question_id for r in inp.responses if _recommended_in(r, inp, k)}
        return len(qs)
    if d.field == "menu":
        return sum("budget" in inp.question_features.get(q, []) for q in inp.question_ids) + 1
    return len(inp.question_ids)  # listing·regular_hours·phone·website·source_mismatch: 모든 질문


def _recommended_in(r: ResponseView, inp: FindingInputs, key: str) -> bool:
    comps = set(inp.competitors)
    return r.extraction_ok and any(
        not x.is_target and x.normalized_name in comps and key in x.mentioned_attributes for x in r.recs
    )


def prioritize(drafts: list[FindingDraft], inp: FindingInputs) -> list[FindingDraft]:
    """competitor_count·question_count·insufficient를 정하고 6.6 순서로 priority 1부터."""
    for d in drafts:
        d.competitor_count, insufficient = _competitor_count(d, inp)
        d.question_count = _question_count(d, inp)
        if insufficient:
            d.evidence["insufficient"] = True
    ordered = sorted(
        drafts,
        key=lambda d: (
            bool(d.evidence.get("insufficient")),
            -d.competitor_count,
            -d.question_count,
            CATEGORY_ORDER.index(d.category),
            d.field,
        ),
    )
    for i, d in enumerate(ordered, 1):
        d.priority = i
    return ordered


# --- 6.7 제목 ---------------------------------------------------------------------------

_MISSING_TITLE = {
    "listing": "{map}에 가게가 없어요",
    "regular_hours": "{map}에 영업시간이 없어요",
    "hours": "{map}에 영업시간이 없어요",
    "website": "{map}에 웹사이트가 없어요",
    "phone": "{map}에 전화번호가 없어요",
    "menu": "{map}에 메뉴·가격 정보가 없어요",
    "price_items": "{map}에 메뉴·가격 정보가 없어요",
    "description": "{map}에 가게 소개가 없어요",
    "intro": "{map}에 가게 소개가 없어요",
    "attributes": "{map}에 편의 정보가 비어 있어요",
    "services": "{map}에 편의 정보가 비어 있어요",
    "links": "{map}에 사이트·SNS 링크가 없어요",
    "tags": "{map}에 태그가 없어요",
}
_MISMATCH_WORD = {
    "name": "가게 이름이",
    "address": "주소가",
    "phone": "전화번호가",
    "regular_hours": "영업시간이",
}
_AI_WORD = {"regular_hours": "영업시간을", "phone": "전화번호를", "menu": "가격을", "address": "위치를"}
_ENGLISH_TITLE = {"description": "{map}에 영어 소개가 없어요", "menu": "{map} 메뉴에 영어가 없어요"}


def title_for(title_key: str, provider: str, evidence: dict[str, Any]) -> str:
    category, _, key = title_key.partition(".")
    map_ = MAP_LABEL.get(provider, provider)
    if category == "map_missing":
        return _MISSING_TITLE[key].format(map=map_)
    if category == "english_missing":
        return _ENGLISH_TITLE[key].format(map=map_)
    if category == "condition_missing":
        return f"{ATTRIBUTES[key].label} 여부가 표시돼 있지 않아요"
    if category == "source_mismatch":
        first = ((evidence.get("sources") or [{}])[0].get("source") or "web").split(":")[0]
        return f"{SOURCE_LABEL.get(first, '외부 사이트')}와 {map_}의 {_MISMATCH_WORD[key]} 달라요"
    providers = evidence.get("providers") or []
    ai = AI_LABEL[providers[0]] if len(providers) == 1 else "AI"
    return f"{ai}가 {_AI_WORD[key]} 틀리게 말해요"
