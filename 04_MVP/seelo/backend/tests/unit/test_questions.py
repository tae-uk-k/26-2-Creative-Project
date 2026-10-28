"""W-04-1 질문 규칙(08 1장, 14 2.5)과 출처 번호(08 3.1·2.3)."""

import pytest

from seelo.domain.annotate import annotate_gemini, annotate_openai, gemini_domain
from seelo.domain.questions import (
    cuisine_for,
    generation_prompt,
    pick_feature,
    template_questions,
    validate_questions,
    with_feature,
)
from seelo.schemas.llm import GeneratedQuestionOut as Q

KW = {
    "region_ko": "명동",
    "region_en": "Myeong-dong",
    "category": "restaurant",
    "cuisine": ("Korean restaurants", "한식당"),
    "feature": "takeout",
}
NAMES = ["명동교자 본점", "Myeongdong Kyoja", "명동교자(본점)"]


def good() -> list[Q]:
    return [
        Q(
            lang="en",
            intent_type="basic",
            text="Any good Korean restaurants near Myeong-dong?",
            text_ko="번역",
        ),
        Q(
            lang="en",
            intent_type="conditional",
            text="Korean restaurants with takeout near Myeongdong?",
            text_ko="번역",
        ),
        Q(lang="ko", intent_type="basic", text="명동 근처 한식당 추천해줘", text_ko=None),
    ]


def with_text(i: int, text: str) -> list[Q]:
    qs = good()
    qs[i] = qs[i].model_copy(update={"text": text})
    return qs


def test_good_questions_pass() -> None:
    assert validate_questions(good(), target_names=NAMES, **KW) == []


@pytest.mark.parametrize(
    ("i", "text"),
    [
        (0, "Is Myeongdong Kyoja good near Myeong-dong? Korean restaurants?"),  # 영문 이름
        (2, "명동 근처 명동교자 같은 한식당 추천해줘"),  # 한글 이름(지점 표기 지운 이름)
        (2, "명동 근처 명동 교자 같은 한식당 추천해줘"),  # 띄어 써도
        (1, "MYEONGDONG-KYOJA with takeout Korean restaurants near Myeong-dong?"),  # 대소문자·기호
    ],
)
def test_store_name_rejected(i: int, text: str) -> None:
    assert "contains_store_name" in validate_questions(with_text(i, text), target_names=NAMES, **KW)


@pytest.mark.parametrize(
    ("i", "text", "code"),
    [
        (2, "근처 맛집 추천해줘", "missing_region"),  # 14 2.5 예시
        (0, "Any good Korean restaurants around here?", "missing_region"),
        (0, "What should I see near Myeong-dong?", "missing_category"),
        (2, "명동 근처 가 볼 곳 추천해줘", "missing_category"),
        (1, "Good Korean restaurants near Myeong-dong for dinner?", "missing_condition"),
        (1, "Any good Korean restaurants near Myeong-dong?", "duplicate"),
        (0, "Korean restaurants near Myeong-dong " + "really " * 30 + "?", "too_long"),
    ],
)
def test_rules(i: int, text: str, code: str) -> None:
    assert code in validate_questions(with_text(i, text), target_names=NAMES, **KW)


def test_region_forms_and_structure() -> None:
    kw = {**KW, "region_ko": "성수동", "region_en": "Seongsu-dong"}
    qs = [
        Q(lang="en", intent_type="basic", text="Good Korean restaurants near Seongsu-dong?", text_ko=None),
        Q(
            lang="en",
            intent_type="conditional",
            text="Takeout Korean restaurants near Seongsu dong?",
            text_ko=None,
        ),
        Q(
            lang="ko", intent_type="basic", text="성수 근처 한식당 추천해줘", text_ko=None
        ),  # 끝 "동"을 뺀 형태도 됨
    ]
    assert validate_questions(qs, target_names=NAMES, **kw) == []
    assert validate_questions(list(reversed(qs)), target_names=NAMES, **kw) == ["bad_structure"]
    assert validate_questions(qs[:2], target_names=NAMES, **kw) == ["bad_structure"]


@pytest.mark.parametrize("category", ["restaurant", "cafe", "bar"])
@pytest.mark.parametrize(
    "feature", ["vegetarian", "budget", "card_payment", "reservation", "takeout", "kid_friendly"]
)
def test_templates_pass_their_own_rules(category: str, feature: str) -> None:
    cuisine = cuisine_for("korean_restaurant", category)
    kw = {**KW, "category": category, "cuisine": cuisine, "feature": feature}
    qs = template_questions(**kw)
    assert validate_questions(qs, target_names=NAMES, **kw) == [], [q.text for q in qs]
    assert qs[0].text_ko and qs[1].text_ko and qs[2].text_ko is None


def test_template_fails_when_store_name_is_region() -> None:
    qs = template_questions(**KW)
    assert "contains_store_name" in validate_questions(qs, target_names=["명동"], **KW)


def test_pick_feature_cuisine_and_word_order() -> None:
    assert pick_feature({"servesVegetarianFood": True}) == "vegetarian"
    assert pick_feature({"priceLevel": "PRICE_LEVEL_EXPENSIVE"}) == "budget"  # 기본값
    assert pick_feature({"priceLevel": "PRICE_LEVEL_EXPENSIVE", "takeout": True}) == "takeout"
    assert pick_feature(None) == "budget"
    assert cuisine_for("sushi_restaurant", "restaurant") == ("Japanese restaurants", "일식당")
    assert cuisine_for("brunch_restaurant", "restaurant") == ("restaurants", "식당")
    assert cuisine_for("korean_restaurant", "cafe") == ("cafes", "카페")
    assert with_feature("with takeout", "cafes") == "cafes with takeout"
    assert with_feature("affordable", "a cafe") == "an affordable cafe"
    assert (
        with_feature("vegetarian-friendly", "Korean restaurants") == "vegetarian-friendly Korean restaurants"
    )


def test_prompt_has_no_store_name_and_asks_region_en_when_missing() -> None:
    p = generation_prompt(
        region_ko="명동", region_en=None, cuisine=("Korean restaurants", "한식당"), feature="takeout"
    )
    assert "region_en" in p and "명동" in p and "Do not mention any specific business name" in p
    assert "명동교자" not in p


def test_annotate_openai_example_and_dedupe() -> None:
    assert annotate_openai("Try A. Also B.", [("https://x.com/a", "x", 0, 6)]) == (
        "Try A.[1] Also B.",
        [{"n": 1, "url": "https://x.com/a", "title": "x", "domain": "x.com"}],
    )
    text, sources = annotate_openai(
        "A. B. C.",
        [("https://a.com", "a", 0, 2), ("https://b.com", "b", 3, 5), ("https://a.com", "a", 6, 8)],
    )
    assert text == "A.[1] B.[2] C.[1]"
    assert [s["n"] for s in sources] == [1, 2]
    assert annotate_openai("no cites", []) == ("no cites", [])


def test_annotate_gemini_uses_segment_text_and_title_domain() -> None:
    chunks = [
        {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/1", "title": "uefa.com"},
        {
            "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/2",
            "title": "Some Site Name",
        },
    ]
    supports = [
        {"text": "Spain won.", "end_index": 999, "chunk_indices": [0]},  # 텍스트로 위치를 찾음
        {"text": "not in answer", "end_index": 3, "chunk_indices": [1]},  # 못 찾으면 end_index(길이 이하)
        {"text": "missing", "end_index": 999, "chunk_indices": [1]},  # 둘 다 안 되면 위치 없음
    ]
    text, sources = annotate_gemini("Hi! Spain won. Bye.", chunks, supports)
    assert text == "Hi![2] Spain won.[1] Bye."
    assert [(s["n"], s["domain"]) for s in sources] == [(1, "uefa.com"), (2, "unknown")]
    assert sources[0]["url"].startswith("https://vertexaisearch")  # 리디렉션 주소 그대로
    assert gemini_domain({"domain": "www.tripadvisor.com", "title": "x"}) == "tripadvisor.com"
    assert annotate_gemini("answer", [], []) == ("answer", [])  # 그라운딩이 비어도 실패 아님
