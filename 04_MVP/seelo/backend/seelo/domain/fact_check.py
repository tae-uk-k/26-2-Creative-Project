"""정비안 글 사실 검사(09 6.6, W-09-2). IO 없음.

LLM이 만든 문장을 문장 단위로 검사한다. LLM이 붙인 근거 id는 믿지 않는다(이 검사가 최종).
1. 숫자: 사실에 없는 숫자가 든 표현(시간·가격·전화·숫자)은 `[ ]`로 바꾸고 needs_owner_input.
2. 민감 정보(알레르기·할랄 등): 같은 단어가 사실에 있을 때만 남기고 sensitive. 없으면 문장 삭제.
3. 조건 주장(채식·카드 결제·예약 등): 그 조건의 attribute 사실이 참이어야 한다. 아니면 문장 삭제.
4. 금지 내용(google description): URL·이메일·전화·가격·할인 문구가 든 문장 삭제(사실에 있어도).
"""

import re
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDER = "[ ]"

_PHONE = r"0\d{1,2}-?\d{3,4}-?\d{4}"
_PRICE = r"₩\s?\d[\d,]*|\d[\d,]*\s?(?:원|won|KRW)\b"
_TIME = (
    r"\d{1,2}(?::\d{2})?\s?(?:am|pm|시)?\s?[~–—-]\s?\d{1,2}(?::\d{2})?\s?(?:am|pm|시)?"
    r"|\d{1,2}:\d{2}\s?(?:am|pm)?|\d{1,2}\s?(?:am|pm|시)"
)
_NUMBER = r"\d+(?:[,.:]\d+)*"
EXPRESSION = re.compile(f"{_PHONE}|{_PRICE}|{_TIME}|{_NUMBER}", re.IGNORECASE)
_NUM_CHUNK = re.compile(r"\d[\d,.:]*")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")

SENSITIVE = [
    "알레르기", "알러지", "할랄", "글루텐", "견과", "땅콩", "유제품", "갑각류",
    "allerg", "halal", "gluten", "peanut", "tree nut", "dairy-free", "shellfish", "kosher",
]  # fmt: skip
# 조건 키 → 문장에서 그 조건을 주장하는 말(08 0.1 영어 표현·한글 라벨에서).
# 그 키의 attribute 사실이 참이어야 한다
CLAIM_WORDS: dict[str, list[str]] = {
    "vegetarian": ["vegetarian", "vegan", "채식", "비건"],
    "card_payment": ["credit card", "card payment", "카드 결제", "카드결제"],
    "reservation": ["reservation", "reserve", "booking", "예약"],
    "takeout": ["takeout", "take-out", "take out", "to go", "포장"],
    "delivery": ["delivery", "배달"],
    "kid_friendly": ["kid-friendly", "kids", "children", "아이 동반", "어린이"],
    "group_friendly": ["good for groups", "large groups", "단체"],
    "outdoor_seating": ["outdoor seating", "terrace", "patio", "야외", "테라스"],
    "alcohol": ["beer", "wine", "cocktail", "soju", "주류"],
    "wheelchair": ["wheelchair", "휠체어"],
    "pet_friendly": ["pet-friendly", "pets", "dog-friendly", "반려동물"],
    "budget": ["affordable", "inexpensive", "cheap", "저렴", "합리적인 가격"],
    "english_menu": ["english menu", "영어 메뉴", "영문 메뉴"],
}
_FORBIDDEN = re.compile(
    rf"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+|{_PHONE}|{_PRICE}"
    r"|할인|이벤트|쿠폰|프로모션|discount|sale\b|coupon|promo",
    re.IGNORECASE,
)


@dataclass
class Fact:
    id: str  # "f1", "f2", ...
    kind: str  # hours|phone|website|instagram|menu_item|intro_text|attribute|cuisine|region|landmark
    value: Any  # kind별 형식(08 0장). attribute면 조건 키
    source: str  # website|google_current|kakao_current|google|instagram|web
    text: str  # 사실 검사용 평문(숫자 포함)


@dataclass
class CheckResult:
    text: str
    needs_owner_input: bool = False
    sensitive: bool = False
    removed: list[str] = field(default_factory=list)  # 지운 문장(로그·디버그용, 저장하지 않음)


def _numbers(text: str) -> set[str]:
    return {c.rstrip(".,:").replace(",", "").replace(".", "") for c in _NUM_CHUNK.findall(text)}


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def _has(text: str, word: str) -> bool:
    return word.lower() in text.lower()


def check_sentence(sentence: str, facts: list[Fact], *, provider: str, field_: str) -> CheckResult:
    """문장 하나. 지우면 text가 빈 문자열."""
    fact_text = " ".join(f.text for f in facts)
    if provider == "google" and field_ == "description" and _FORBIDDEN.search(sentence):
        return CheckResult("", removed=[sentence])
    sensitive = False
    for word in SENSITIVE:
        if _has(sentence, word):
            if not _has(fact_text, word):
                return CheckResult("", removed=[sentence])
            sensitive = True
    true_keys = {f.value for f in facts if f.kind == "attribute"}
    for key, words in CLAIM_WORDS.items():
        if any(_has(sentence, w) for w in words) and key not in true_keys:
            return CheckResult("", removed=[sentence])
    known = _numbers(fact_text)
    replaced = False

    def sub(m: re.Match[str]) -> str:
        nonlocal replaced
        if _numbers(m.group(0)) - known:
            replaced = True
            return PLACEHOLDER
        return m.group(0)

    out = EXPRESSION.sub(sub, sentence)
    return CheckResult(out, needs_owner_input=replaced, sensitive=sensitive)


def check_text(text: str, facts: list[Fact], *, provider: str, field: str) -> CheckResult:
    """여러 문장 글. 남은 문장을 원래 순서대로 잇는다(한글·영어 문단이 바뀌는 곳은 빈 줄)."""
    kept: list[str] = []
    result = CheckResult("")
    for sentence in split_sentences(text):
        r = check_sentence(sentence, facts, provider=provider, field_=field)
        result.needs_owner_input |= r.needs_owner_input
        result.sensitive |= r.sensitive
        result.removed += r.removed
        if r.text:
            kept.append(r.text)
    result.text = join_sentences(kept)
    return result


_HANGUL = re.compile(r"[가-힣]")


def join_sentences(sentences: list[str]) -> str:
    """영어 문장들과 한국어 문장들을 각각 한 문단으로(문단 사이 빈 줄)."""
    paragraphs: list[list[str]] = []
    last: bool | None = None
    for s in sentences:
        ko = bool(_HANGUL.search(s))
        if ko != last:
            paragraphs.append([])
            last = ko
        paragraphs[-1].append(s)
    return "\n\n".join(" ".join(p) for p in paragraphs)
