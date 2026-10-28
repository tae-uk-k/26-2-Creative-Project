"""W-07-2 영향 순서(08 6.6): 주변 가게 수 → 질문 수 → 분류 순서 → 칸 이름. 근거 부족은 맨 뒤."""

from dataclasses import replace
from typing import Any

from seelo.domain.findings_rules import FindingDraft, FindingInputs, prioritize
from seelo.domain.metrics import RecView, ResponseView
from seelo.domain.normalize import normalize_name

FACTS = {
    "a": {
        "nationalPhoneNumber": "02-1",
        "regularOpeningHours": {"periods": []},
        "servesVegetarianFood": True,
    },
    "b": {"nationalPhoneNumber": "02-2", "priceLevel": "PRICE_LEVEL_MODERATE"},
    "c": {},
}


def _inp(**kw: Any) -> FindingInputs:
    base = FindingInputs(
        category="restaurant",
        google_found=True,
        kakao_found=True,
        google={},
        kakao_basic=None,
        naver_basic=None,
        website=None,
        web_sites=[],
        question_ids=[1, 2, 3],
        question_features={1: [], 2: ["budget"], 3: []},
        responses=[],
        claims=[],
        competitors=["a", "b", "c"],
        competitor_facts=FACTS,
    )
    return replace(base, **kw)


def _d(category: str, field: str, key: str | None = None, **evidence: Any) -> FindingDraft:
    return FindingDraft(
        "diagnosis", category, f"{category}.{key or field}", "google", field, evidence=evidence
    )


def _resp(rid: int, qid: int, name: str, attrs: list[str]) -> ResponseView:
    return ResponseView(
        rid, "openai", qid, True, [RecView(normalize_name(name), name, 1, False, [], attrs)], []
    )


def test_counts_per_rule() -> None:
    inp = _inp(responses=[_resp(1, 1, "C", ["vegetarian"]), _resp(2, 3, "c", ["vegetarian"])])
    got = {
        d.title_key: (d.competitor_count, d.question_count)
        for d in prioritize(
            [
                _d("map_missing", "listing"),
                _d("map_missing", "phone"),
                _d("map_missing", "regular_hours"),
                _d("map_missing", "menu"),
                _d("map_missing", "attributes", missingKeys=["vegetarian"]),
                _d("condition_missing", "attributes", "vegetarian", conditionKey="vegetarian"),
                _d("source_mismatch", "phone"),
                _d("ai_wrong", "phone", questionIds=[1, 3]),
            ],
            inp,
        )
    }
    assert got == {
        "map_missing.listing": (3, 3),  # 주변 가게는 모두 지도에 있음, 모든 질문
        "map_missing.phone": (2, 3),  # a·b가 전화번호를 갖춤
        "map_missing.regular_hours": (1, 3),
        "map_missing.menu": (1, 2),  # budget 질문 1 + 1
        "map_missing.attributes": (1, 2),  # a만 채식 참. 질문: 채식 이유로 추천된 질문 1·3
        "condition_missing.vegetarian": (1, 2),  # max(사실 1, 채식으로 추천된 가게 c 1)
        "source_mismatch.phone": (0, 3),
        "ai_wrong.phone": (0, 2),
    }


def test_condition_count_is_max_of_facts_and_recommended() -> None:
    responses = [_resp(1, 1, "a", ["budget"]), _resp(2, 2, "b", ["budget"]), _resp(3, 3, "c", ["budget"])]
    (d,) = prioritize(
        [_d("condition_missing", "menu", "budget", conditionKey="budget")], _inp(responses=responses)
    )
    assert (d.competitor_count, d.question_count) == (3, 3)  # 사실은 b 1곳, 추천은 3곳


def test_order_and_ties() -> None:
    drafts = prioritize(
        [
            _d("source_mismatch", "phone"),  # 0곳, 질문 3
            _d("map_missing", "regular_hours"),  # 1곳, 질문 3
            _d("map_missing", "phone"),  # 2곳, 질문 3
            _d("ai_wrong", "address", questionIds=[1, 2, 3]),  # 0곳, 질문 3 → 분류 순서로 source_mismatch 앞
            _d("ai_wrong", "phone", questionIds=[1, 2, 3]),  # 같은 분류 → 칸 이름순
        ],
        _inp(),
    )
    assert [(d.priority, d.title_key) for d in drafts] == [
        (1, "map_missing.phone"),
        (2, "map_missing.regular_hours"),
        (3, "ai_wrong.address"),
        (4, "ai_wrong.phone"),
        (5, "source_mismatch.phone"),
    ]


def test_insufficient_goes_last() -> None:
    """주변 가게 사실 조회 실패(None) → 그 정보에 기대는 항목은 근거 부족, 맨 뒤."""
    drafts = prioritize(
        [_d("map_missing", "phone"), _d("source_mismatch", "address"), _d("map_missing", "listing")],
        _inp(competitor_facts=None),
    )
    assert [(d.title_key, d.evidence.get("insufficient", False)) for d in drafts] == [
        ("map_missing.listing", False),
        ("source_mismatch.address", False),
        ("map_missing.phone", True),
    ]
