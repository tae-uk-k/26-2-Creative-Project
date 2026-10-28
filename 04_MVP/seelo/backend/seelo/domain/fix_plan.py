"""정비안 만들기의 순수 부분(09 4·6장): 사실 목록, finding → 칸, 칸별 바꿀 값, 글 프롬프트, 글자 수. IO 없음.

- 사실(Fact) 출처 우선순위: 공식 웹사이트 → 연결 뒤 읽은 지금 값(두 지도) → Google 스냅샷 → 인스타그램 →
  AI 웹 검색 사이트(2곳 이상이 같은 값일 때만). **네이버 값과 카카오 로컬 API 값은 넣지 않는다.**
- 칸 값은 사실만으로 정한다. 사실이 없으면 지어내지 않고 사장님 입력(needs_owner_input)으로 남긴다.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from seelo.domain.attributes import ATTRIBUTES, KAKAO_KEYWORD
from seelo.domain.fact_check import PLACEHOLDER, Fact, check_sentence, check_text, join_sentences
from seelo.domain.field_dictionary import FieldSpec
from seelo.domain.findings_rules import title_for
from seelo.domain.hours import format_hours_ko, from_google_periods
from seelo.domain.labels import GUIDE_ADDRESS, GUIDE_KAKAO_PHONE, GUIDE_NAME, MAP_LABEL
from seelo.domain.normalize import domain_of, normalize_phone
from seelo.schemas.llm import PlanTextsOut

TEXT_FIELDS = {"google": {"description"}, "kakao": {"intro", "tags"}}
MENU_FIELDS = {"google": "menu", "kakao": "price_items"}
FEATURED = 2  # 카카오 가격 정보 추천 표시 수

# finding field → 칸(09 6.3 표). None = 칸 없음(ownerOnly·mapNotFound)
_FIELD_MAP = {
    "google": {
        "regular_hours": "regular_hours", "hours": "regular_hours", "website": "website", "phone": "phone",
        "menu": "menu", "price_items": "menu", "attributes": "attributes", "services": "attributes",
        "description": "description", "intro": "description",
    },
    "kakao": {
        "regular_hours": "hours", "hours": "hours", "website": "links", "menu": "price_items",
        "price_items": "price_items", "attributes": "services", "services": "services",
        "description": "intro", "intro": "intro", "links": "links", "tags": "tags",
    },
}  # fmt: skip


@dataclass
class FindingRef:
    id: int
    provider: str
    field: str
    category: str
    title_key: str
    priority: int
    evidence: dict[str, Any]


@dataclass
class PlanInputs:
    provider: str
    category: str
    region_ko: str | None
    current: dict[str, Any]  # 칸 → 지금 값(읽지 않았으면 None)
    findings: list[FindingRef]  # 이 지도의 진단 단계 + 정비안 단계 finding
    website: dict[str, Any] | None  # 웹사이트 스냅샷 extract
    website_url: str | None  # 웹사이트 수집에 성공한 주소
    google: dict[str, Any] | None  # Google 스냅샷 ko payload
    other_current: dict[str, Any] = field(default_factory=dict)  # 다른 지도의 지금 값
    instagram_url: str | None = None
    instagram_bio: str | None = None
    web_sites: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ItemDraft:
    field: str
    proposed: Any
    finding_ids: list[int]
    reason: str
    order_key: tuple[int, int]
    needs_owner_input: bool = False
    sensitive: bool = False
    fact_ids: list[str] = field(default_factory=list)
    response_ids: list[int] = field(default_factory=list)
    delete: bool = False  # 사실이 없어 만들지 않는 칸(website·links)


# --- 사실 ---------------------------------------------------------------------------------


def build_facts(inp: PlanInputs) -> list[Fact]:
    facts: list[Fact] = []

    def add(kind: str, value: Any, source: str, text: str) -> None:
        facts.append(Fact(f"f{len(facts) + 1}", kind, value, source, text))

    site = inp.website or {}
    if isinstance(site.get("hours"), dict):
        add("hours", site["hours"], "website", site.get("hours_text") or format_hours_ko(site["hours"]))
    if site.get("phone"):
        add("phone", site["phone"], "website", site["phone"])
    if inp.website_url:
        add("website", inp.website_url, "website", inp.website_url)
    for m in site.get("menu") or []:
        if m.get("name"):
            price = f" {m['price']}원" if m.get("price") is not None else ""
            add("menu_item", {"name": m["name"], "price": m.get("price")}, "website", f"{m['name']}{price}")
    if site.get("intro"):
        add("intro_text", site["intro"], "website", site["intro"])
    site_words = " ".join(str(site.get(k) or "") for k in ("intro", "hours_text")).lower()
    for key, a in ATTRIBUTES.items():
        if a.label.lower() in site_words or a.en.lower() in site_words:
            add("attribute", key, "website", a.label)
    # 연결 뒤 읽은 지금 값(이 지도와 다른 지도)
    for source, values in (
        (f"{inp.provider}_current", inp.current),
        (_other(inp.provider), inp.other_current),
    ):
        hours = values.get("regular_hours") or values.get("hours")
        if isinstance(hours, dict):
            add("hours", hours, source, format_hours_ko(hours))
        attrs = values.get("attributes")
        if isinstance(attrs, dict):
            for key, v in attrs.items():
                if v is True and key in ATTRIBUTES:
                    add("attribute", key, source, ATTRIBUTES[key].label)
        for kw in values.get("services") or []:
            key = next((k for k, w in KAKAO_KEYWORD.items() if w == kw), None)
            if key:
                add("attribute", key, source, kw)
        for k in ("description", "intro"):
            if values.get(k):
                add("intro_text", values[k], source, str(values[k]))
    g = inp.google or {}
    periods = (g.get("regularOpeningHours") or {}).get("periods")
    if periods:
        desc = "\n".join((g.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [])
        add("hours", from_google_periods(periods), "google", desc)
    if g.get("nationalPhoneNumber"):
        add("phone", g["nationalPhoneNumber"], "google", g["nationalPhoneNumber"])
    if g.get("websiteUri"):
        add("website", g["websiteUri"], "google", g["websiteUri"])
    for key, a in ATTRIBUTES.items():
        if g and a.google(g) is True:
            add("attribute", key, "google", a.label)
    cuisine = (g.get("primaryTypeDisplayName") or {}).get("text")
    if cuisine:
        add("cuisine", cuisine, "google", cuisine)
    if inp.region_ko:
        add("region", inp.region_ko, "google", inp.region_ko)
    if inp.instagram_url:
        add("instagram", inp.instagram_url, "instagram", inp.instagram_url)
    if inp.instagram_bio:
        add("intro_text", inp.instagram_bio, "instagram", inp.instagram_bio)
    # 웹 근거: 서로 다른 사이트 2곳 이상이 같은 값일 때만
    for kind, key, norm in (
        ("phone", "phone", normalize_phone),
        ("hours", "hours_text", lambda v: " ".join(v.split())),
    ):
        groups: dict[str, set[str]] = defaultdict(set)
        original: dict[str, str] = {}
        for s in inp.web_sites:
            if s.get(key):
                n = norm(str(s[key]))
                groups[n].add(domain_of(s.get("url") or ""))
                original.setdefault(n, str(s[key]))
        for n, domains in groups.items():
            if len(domains) >= 2:
                add(kind if kind == "phone" else "hours_text", original[n], "web", original[n])
    return facts


def _other(provider: str) -> str:
    return "kakao_current" if provider == "google" else "google_current"


def _first(facts: list[Fact], kind: str, sources: tuple[str, ...]) -> Fact | None:
    for src in sources:
        for f in facts:
            if f.kind == kind and f.source == src:
                return f
    return None


# --- finding → 칸 ---------------------------------------------------------------------------


def item_field(provider: str, f: FindingRef) -> str | None:
    if f.provider != provider or f.field in ("name", "address", "listing", "category"):
        return None
    if f.category == "condition_missing":
        if provider == "kakao":
            return "services"
        return "menu" if f.field == "menu" else "attributes"
    if f.category == "english_missing":
        return {"description": _FIELD_MAP[provider]["description"], "menu": MENU_FIELDS[provider]}.get(
            f.field
        )
    return _FIELD_MAP[provider].get(f.field)


def owner_only_fields(provider: str, findings: list[FindingRef]) -> list[tuple[str, str]]:
    """이름·주소(·카카오 전화)가 다르거나 없을 때 사장님이 직접 고치는 방법(09 4장)."""
    guides = {"name": GUIDE_NAME, "address": GUIDE_ADDRESS}
    out: dict[str, str] = {}
    for f in findings:
        if f.provider != provider:
            continue
        if f.field in guides:
            out[f.field] = guides[f.field].format(map=MAP_LABEL[provider])
        elif provider == "kakao" and f.field == "phone":
            out["phone"] = GUIDE_KAKAO_PHONE
    return sorted(out.items())


def map_not_found(provider: str, findings: list[FindingRef]) -> bool:
    return any(f.provider == provider and f.title_key == "map_missing.listing" for f in findings)


# --- 칸별 바꿀 값(09 6.4) --------------------------------------------------------------------


def _related_keys(findings: list[FindingRef]) -> list[str]:
    keys: list[str] = []
    for f in findings:
        for k in [*f.evidence.get("missingKeys", []), f.evidence.get("conditionKey")]:
            if k and k in ATTRIBUTES and k not in keys:
                keys.append(k)
    return keys


def draft_items(inp: PlanInputs, facts: list[Fact], specs: list[FieldSpec]) -> list[ItemDraft]:
    """finding이 연결된 칸만. 글 칸(description·intro·tags)과 메뉴 영문은 LLM 결과로 나중에 채운다."""
    by_field: dict[str, list[FindingRef]] = defaultdict(list)
    for f in inp.findings:
        fld = item_field(inp.provider, f)
        if fld:
            by_field[fld].append(f)
    order = {s.key: s.order for s in specs}
    other = _other(inp.provider)
    drafts: list[ItemDraft] = []
    for spec in specs:
        linked = by_field.get(spec.key)
        if not linked:
            continue  # 근거 없는 칸은 만들지 않는다
        d = ItemDraft(
            field=spec.key,
            proposed=None,
            finding_ids=sorted(f.id for f in linked),
            reason="·".join(dict.fromkeys(title_for(f.title_key, f.provider, f.evidence) for f in linked)),
            order_key=(min(f.priority for f in linked), order[spec.key]),
            response_ids=sorted({r for f in linked for r in f.evidence.get("responseIds", [])}),
        )
        key = spec.key
        if spec.type == "hours":
            fact = _first(facts, "hours", ("website", other, "google"))
            d.proposed = fact.value if fact else None
            d.needs_owner_input = fact is None
            d.fact_ids = [fact.id] if fact else []
        elif key == "website":
            fact = _first(facts, "website", ("website",))
            d.proposed, d.fact_ids, d.delete = (fact.value, [fact.id], False) if fact else (None, [], True)
        elif key == "phone":
            fact = _first(facts, "phone", ("website", "kakao_current"))
            d.proposed = fact.value if fact else PLACEHOLDER
            d.needs_owner_input = fact is None
            d.fact_ids = [fact.id] if fact else []
        elif key == "links":
            used = [
                f
                for f in (_first(facts, "website", ("website",)), _first(facts, "instagram", ("instagram",)))
                if f
            ]
            d.proposed, d.fact_ids, d.delete = [f.value for f in used], [f.id for f in used], not used
        elif spec.type == "menu":
            items = [f for f in facts if f.kind == "menu_item" and f.source == "website"]
            d.proposed = [
                {
                    "name": f.value["name"], "nameEn": None, "price": f.value["price"], "description": None,
                    **({"featured": i < FEATURED} if inp.provider == "kakao" else {}),
                }
                for i, f in enumerate(items)
            ]  # fmt: skip
            d.fact_ids = [f.id for f in items]
            d.needs_owner_input = not items
        elif key == "attributes":
            true_keys = {f.value for f in facts if f.kind == "attribute"}
            keys = _related_keys(linked)
            d.proposed = {k: (True if k in true_keys else None) for k in keys}
            d.fact_ids = [f.id for f in facts if f.kind == "attribute" and f.value in keys]
            d.needs_owner_input = any(v is None for v in d.proposed.values()) or not keys
        elif key == "services":
            attrs = [f for f in facts if f.kind == "attribute" and f.value in KAKAO_KEYWORD]
            d.proposed = list(dict.fromkeys(KAKAO_KEYWORD[f.value] for f in attrs))
            d.fact_ids = [f.id for f in attrs]
            d.needs_owner_input = not d.proposed
        # description·intro·tags는 LLM(apply_texts)
        drafts.append(d)
    return drafts


def needs_texts(provider: str, drafts: list[ItemDraft]) -> dict[str, bool]:
    fields = {d.field for d in drafts}
    menu = MENU_FIELDS[provider]
    return {
        "description": provider == "google" and "description" in fields,
        "intro": provider == "kakao" and "intro" in fields,
        "tags": provider == "kakao" and "tags" in fields,
        "menu": menu in fields and any(d.field == menu and d.proposed for d in drafts),
    }


# --- 글(09 6.5~6.7) ---------------------------------------------------------------------------


def plan_prompt(
    inp: PlanInputs,
    facts: list[Fact],
    drafts: list[ItemDraft],
    specs: dict[str, FieldSpec],
    *,
    shorter: dict[str, int] | None = None,
) -> str:
    want = needs_texts(inp.provider, drafts)
    titles = sorted({d.reason for d in drafts})
    fact_lines = "\n".join(f"{f.id} [{f.kind}] {f.text}" for f in facts if f.kind != "website")
    lines = []
    if want["description"]:
        n = (shorter or {}).get("description") or specs["description"].max_length or 750
        lines.append(
            "- google_description: one English paragraph, then one Korean paragraph. "
            f"Max {n} characters total."
        )
    if want["intro"]:
        n = (shorter or {}).get("intro") or specs["intro"].max_length or 50
        lines.append(f"- kakao_intro: Korean, max {n} characters.")
    if want["menu"]:
        lines.append(
            "- menu_texts: for each menu item id, an English name and a short English description "
            "(no prices)."
        )
    if want["tags"]:
        lines.append("- kakao_tags: up to 5 short Korean tags.")
    rewrite = ""
    if shorter:
        rewrite = "Rewrite shorter than the limits above, same facts only.\n"
    return (
        f"You write listing text for a small {inp.category} in {inp.region_ko or 'Seoul'}, Korea, "
        "to help foreign tourists.\n"
        "Use ONLY the facts below. Never add numbers, prices, opening hours, phone numbers, dates,\n"
        "years, awards, rankings, or claims that are not in the facts.\n"
        "Do not mention allergies, allergens, gluten, or halal unless a fact states it.\n"
        "Do not include URLs, emails, or phone numbers in the description.\n"
        f"Problems to fix: {'; '.join(titles) or '(none)'}\n"
        f"Facts:\n{fact_lines or '(none)'}\n"
        f"Write:\n" + "\n".join(lines) + "\n"
        "Leave fields that are not listed above as null or empty.\n"
        "For every sentence, list the fact ids it is based on.\n" + rewrite
    )


def fit_length(text: str, limit: int) -> tuple[str, bool]:
    """제한을 넘으면 문장 단위로 뒤에서부터 지운다. 첫 문장만으로도 넘으면 자르고 (글, 사장님 확인 필요)."""
    from seelo.domain.fact_check import split_sentences

    if len(text) <= limit:
        return text, False
    sentences = split_sentences(text)
    while len(sentences) > 1 and len(join_sentences(sentences)) > limit:
        sentences.pop()
    out = join_sentences(sentences)
    if len(out) > limit:
        return out[:limit], True
    return out, False


def over_limit(drafts: list[ItemDraft], specs: dict[str, FieldSpec]) -> dict[str, int]:
    out = {}
    for d in drafts:
        s = specs[d.field]
        if (
            s.type == "text"
            and s.max_length
            and isinstance(d.proposed, str)
            and len(d.proposed) > s.max_length
        ):
            out[d.field] = s.max_length
    return out


def apply_texts(
    inp: PlanInputs,
    facts: list[Fact],
    drafts: list[ItemDraft],
    texts: PlanTextsOut,
    *,
    only: set[str] | None = None,
) -> None:
    """LLM 결과를 사실 검사(09 6.6)를 거쳐 칸에 넣는다. only가 있으면 그 칸만(짧게 다시 쓴 결과)."""
    ids = {f.id for f in facts}
    by = {d.field: d for d in drafts}
    p = inp.provider

    def take(field_: str) -> bool:
        return field_ in by and (only is None or field_ in only)

    if take("description") and texts.google_description is not None:
        kept, used = [], set()
        for ref in texts.google_description:
            r = check_sentence(ref.text.strip(), facts, provider=p, field_="description")
            by["description"].needs_owner_input |= r.needs_owner_input
            by["description"].sensitive |= r.sensitive
            if r.text:
                kept.append(r.text)
                used |= {i for i in ref.fact_ids if i in ids}
        by["description"].proposed = join_sentences(kept) or None
        by["description"].fact_ids = sorted(used)
        by["description"].needs_owner_input |= not kept
    if take("intro") and texts.kakao_intro is not None:
        r = check_text(texts.kakao_intro, facts, provider=p, field="intro")
        d = by["intro"]
        d.proposed, d.needs_owner_input, d.sensitive = (
            r.text or None,
            r.needs_owner_input or not r.text,
            r.sensitive,
        )
    if take("tags"):
        tags = []
        for t in texts.kakao_tags:
            r = check_sentence(t.strip().lstrip("#"), facts, provider=p, field_="tags")
            if r.text and PLACEHOLDER not in r.text and r.text not in tags:
                tags.append(r.text)
        by["tags"].proposed = tags[:5]
        by["tags"].needs_owner_input = not tags
    menu = MENU_FIELDS[p]
    if take(menu) and texts.menu_texts and isinstance(by[menu].proposed, list):
        names = {f.id: f.value["name"] for f in facts if f.kind == "menu_item"}
        text_by_name = {names[m.fact_id]: m for m in texts.menu_texts if m.fact_id in names}
        for item in by[menu].proposed:
            m = text_by_name.get(item["name"])
            if m is None:
                continue
            for key, value in (("nameEn", m.name_en), ("description", m.description_en)):
                if not value:
                    continue
                r = check_text(value, facts, provider=p, field="menu")
                item[key] = r.text or None
                by[menu].needs_owner_input |= r.needs_owner_input
                by[menu].sensitive |= r.sensitive


def fit_all(drafts: list[ItemDraft], specs: dict[str, FieldSpec]) -> None:
    """09 6.7 2번: 그래도 넘는 글 칸을 문장 단위로 줄인다."""
    for d in drafts:
        s = specs[d.field]
        if s.type == "text" and s.max_length and isinstance(d.proposed, str):
            d.proposed, cut = fit_length(d.proposed, s.max_length)
            d.needs_owner_input |= cut
        if d.field == "tags" and isinstance(d.proposed, list):
            limit = s.max_length or 20
            d.proposed = [t for t in d.proposed if len(t) <= limit][: s.max_items or 5]
