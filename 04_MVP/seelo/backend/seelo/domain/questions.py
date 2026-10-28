"""질문 만들기 규칙(08 1장, 14 2.5, W-04-1). IO 없음."""

import re
import unicodedata
from typing import Any

from seelo.domain.attributes import ATTRIBUTES, google_value
from seelo.domain.normalize import normalize_name
from seelo.schemas.llm import GeneratedQuestionOut

MAX_LEN = 200
FEATURE_ORDER = (
    "vegetarian",
    "budget",
    "card_payment",
    "reservation",
    "takeout",
    "outdoor_seating",
    "kid_friendly",
    "group_friendly",
)
DEFAULT_FEATURE = "budget"

_CUISINE: dict[str, tuple[str, str]] = {
    "korean_restaurant": ("Korean restaurants", "한식당"),
    "japanese_restaurant": ("Japanese restaurants", "일식당"),
    "sushi_restaurant": ("Japanese restaurants", "일식당"),
    "ramen_restaurant": ("Japanese restaurants", "일식당"),
    "chinese_restaurant": ("Chinese restaurants", "중식당"),
    "italian_restaurant": ("Italian restaurants", "이탈리안 레스토랑"),
    "pizza_restaurant": ("Italian restaurants", "이탈리안 레스토랑"),
    "barbecue_restaurant": ("Korean BBQ restaurants", "고깃집"),
    "vegetarian_restaurant": ("vegetarian restaurants", "채식 식당"),
    "vegan_restaurant": ("vegetarian restaurants", "채식 식당"),
}
_DEFAULT_CUISINE = {"restaurant": ("restaurants", "식당"), "cafe": ("cafes", "카페"), "bar": ("bars", "술집")}

CATEGORY_WORDS: dict[str, tuple[list[str], list[str]]] = {
    "restaurant": (
        ["restaurant", "restaurants", "food", "eat", "dining", "bbq"],
        ["식당", "맛집", "음식점", "한식", "일식", "중식", "고깃집", "레스토랑"],
    ),
    "cafe": (["cafe", "cafes", "café", "coffee"], ["카페", "커피"]),
    "bar": (["bar", "bars", "pub", "drinks", "cocktail"], ["술집", "바", "펍", "주점"]),
}

# 질문 2에 들어가야 하는 조건 핵심 단어(소문자 부분 일치)
CONDITION_WORDS: dict[str, list[str]] = {
    "vegetarian": ["vegetarian", "vegan"],
    "budget": ["affordable", "cheap", "budget", "inexpensive"],
    "card_payment": ["credit card", "card"],
    "reservation": ["reservation", "reserve", "booking", "book a table"],
    "takeout": ["takeout", "take-out", "take out", "takeaway", "to go"],
    "outdoor_seating": ["outdoor", "terrace", "patio"],
    "kid_friendly": ["kid", "child", "family"],
    "group_friendly": ["group"],
    "delivery": ["delivery", "deliver"],
    "alcohol": ["drink", "alcohol", "beer", "wine"],
    "wheelchair": ["wheelchair", "accessible"],
    "pet_friendly": ["pet", "dog"],
}

_WORD = re.compile(r"[^0-9a-z가-힣]")


def _flat(s: str) -> str:
    """비교용: NFKC, 소문자, 한글·영문·숫자만."""
    return _WORD.sub("", unicodedata.normalize("NFKC", s).casefold())


def pick_feature(google_payload: dict[str, Any] | None) -> str:
    """Google 스냅샷에서 순서대로 처음 참인 조건 키. 없으면 budget."""
    g = google_payload or {}
    return next((k for k in FEATURE_ORDER if google_value(k, g) is True), DEFAULT_FEATURE)


def cuisine_for(primary_type: str | None, category: str) -> tuple[str, str]:
    if category == "restaurant" and primary_type in _CUISINE:
        return _CUISINE[primary_type]
    return _DEFAULT_CUISINE[category]


def feature_text(feature: str) -> tuple[str, str]:
    """(질문용 영어 표현, 한글 라벨)."""
    a = ATTRIBUTES[feature]
    return a.en, a.label


def _region_ko_forms(region_ko: str) -> list[str]:
    forms = [region_ko]
    if region_ko.endswith("동") and len(region_ko) >= 3:  # "성수동" → "성수"(두 글자 이상 남을 때만)
        forms.append(region_ko[:-1])
    return forms


def _has_any(text: str, words: list[str]) -> bool:
    low = text.casefold()
    return any(w.casefold() in low for w in words)


def validate_questions(
    qs: list[GeneratedQuestionOut],
    *,
    target_names: list[str],
    region_ko: str,
    region_en: str,
    category: str,
    cuisine: tuple[str, str],
    feature: str,
) -> list[str]:
    """오류 코드 목록(비면 통과). 구조가 틀리면 bad_structure 하나만."""
    shape = [(q.lang, q.intent_type) for q in qs]
    if shape != [("en", "basic"), ("en", "conditional"), ("ko", "basic")]:
        return ["bad_structure"]
    errors: list[str] = []
    names = {n for n in (normalize_name(x) for x in target_names if x) if len(n) >= 2}
    flats = [_flat(q.text) for q in qs]
    if any(n in f for f in flats for n in names):
        errors.append("contains_store_name")
    region_en_flat = _flat(region_en)
    en_ok = bool(region_en_flat) and all(region_en_flat in flats[i] for i in (0, 1))
    ko_ok = any(_flat(form) in flats[2] for form in _region_ko_forms(region_ko))
    if not (en_ok and ko_ok):
        errors.append("missing_region")
    en_words, ko_words = CATEGORY_WORDS[category]
    en_words = en_words + cuisine[0].casefold().split()
    ko_words = ko_words + [cuisine[1]]
    if not (all(_has_any(qs[i].text, en_words) for i in (0, 1)) and _has_any(qs[2].text, ko_words)):
        errors.append("missing_category")
    if not _has_any(qs[1].text, CONDITION_WORDS.get(feature, [ATTRIBUTES[feature].en])):
        errors.append("missing_condition")
    if len(set(flats)) != 3:
        errors.append("duplicate")
    if any(len(q.text) > MAX_LEN for q in qs):
        errors.append("too_long")
    return errors


def _eun_neun(word: str) -> str:
    """받침이 있으면 "은", 없으면 "는"."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "은" if (ord(last) - 0xAC00) % 28 else "는"
    return "는"


def with_feature(feature_en: str, noun: str) -> str:
    """조건 표현을 영어 어순에 맞게 붙인다: "vegetarian-friendly cafes", "cafes with takeout"."""
    if feature_en.startswith(("with ", "that ")):
        return f"{noun} {feature_en}"
    if noun.startswith("a "):
        article = "an" if feature_en[:1].lower() in "aeiou" else "a"
        return f"{article} {feature_en} {noun[2:]}"
    return f"{feature_en} {noun}"


def template_questions(
    *, region_ko: str, region_en: str, category: str, cuisine: tuple[str, str], feature: str
) -> list[GeneratedQuestionOut]:
    """08 1.5 템플릿. Q1·Q2의 한국어 번역은 고정 문구."""
    c_en, c_ko = cuisine
    f_en, f_ko = feature_text(feature)
    if category == "cafe":
        q1, q2, q3 = (
            f"What are nice cafes near {region_en}?",
            f"Where can I find {with_feature(f_en, 'a cafe')} near {region_en}?",
            f"{region_ko} 근처 괜찮은 카페 추천해줘",
        )
    elif category == "bar":
        q1, q2, q3 = (
            f"What are good bars near {region_en}?",
            f"Where can I find {with_feature(f_en, 'a bar')} near {region_en}?",
            f"{region_ko} 근처 분위기 좋은 술집 추천해줘",
        )
    else:
        q1, q2, q3 = (
            f"What are good {c_en} near {region_en}?",
            f"Where can I find {with_feature(f_en, c_en)} near {region_en}?",
            f"{region_ko} 근처 맛있는 {c_ko} 추천해줘",
        )
    return [
        GeneratedQuestionOut(
            lang="en",
            intent_type="basic",
            text=q1,
            text_ko=f"{region_ko} 근처 괜찮은 {c_ko}{_eun_neun(c_ko)}?",
        ),
        GeneratedQuestionOut(
            lang="en",
            intent_type="conditional",
            text=q2,
            text_ko=f"{region_ko} 근처 {f_ko} {c_ko}{_eun_neun(c_ko)} 어디야?",
        ),
        GeneratedQuestionOut(lang="ko", intent_type="basic", text=q3, text_ko=None),
    ]


def generation_prompt(
    *, region_ko: str, region_en: str | None, cuisine: tuple[str, str], feature: str
) -> str:
    """08 1.2. region_en을 모르면 LLM이 지역 영어 이름(region_en)도 정한다. 가게 이름은 넣지 않는다."""
    f_en, _ = feature_text(feature)
    area = region_en or f"<English name of {region_ko}>"
    lines = [
        "Write exactly 3 questions that a foreign tourist visiting Korea might ask an AI assistant "
        "to find places.",
        f"Q1: English. Ask for good {cuisine[0]} near {area}.",
        f'Q2: English. Ask for {f_en} {cuisine[0]} near {area}. The condition "{f_en}" must appear.',
        f"Q3: Korean. Ask for good {cuisine[1]} near {region_ko}, casual tone "
        '(반말 요청형, e.g. "...추천해줘").',
        "Rules: Do not mention any specific business name. Each question under 20 words. "
        "Natural, like a real traveler.",
        "Also give a Korean translation for Q1 and Q2.",
    ]
    if region_en is None:
        lines.append(
            f'The area "{region_ko}" is in Korea. Use its common English name in Q1 and Q2 '
            "and return it as region_en."
        )
    return "\n".join(lines)
