"""쇼핑몰 AI 노출 판정 규칙. 실험(2026-11-24)의 발견·추천·인용·무효 기준을 고정 문자열로 검사한다."""

import pytest

from seelo.domain import commerce_measure as rules
from seelo.errors import AppError

TARGETS = {
    "names": ["seelo 사차인치 탈지 단백질 분말 300g"],
    "urls": ["https://xodnrdl06066.cafe24.com/product/detail.html?product_no=15"],
}


def test_exact_name_in_top_three_is_identified_and_recommended():
    text = (
        "1. 다른 단백질 분말 - A몰\n"
        "2. **seelo 사차인치 탈지 단백질 분말 300g** - 카페24\n   근거: 상세 페이지\n"
        "3. 또 다른 제품\n"
    )
    result = rules.evaluate(text, [], TARGETS)
    assert result["identified"] and result["recommended"] and result["rank"] == 2
    assert result["target_url_cited"] is False


def test_brand_or_ingredient_only_is_not_a_hit():
    text = "1. 사차인치 단백질은 식물성입니다.\n2. seelo 브랜드 제품도 있습니다."
    result = rules.evaluate(text, [], TARGETS)
    assert not result["identified"] and not result["recommended"] and result["rank"] is None


def test_url_in_sources_counts_as_citation_and_rank_beyond_three_is_not_recommended():
    text = (
        "\n".join(f"{n}. 제품 {n}" for n in range(1, 4))
        + "\n4. 다른 판매처 https://m.xodnrdl06066.cafe24.com/product/detail.html?product_no=15&utm=x"
    )
    result = rules.evaluate(
        text, [{"url": "https://xodnrdl06066.cafe24.com/product/detail.html?product_no=15"}], TARGETS
    )
    assert result["identified"] and result["target_url_cited"] and result["rank"] == 4
    assert result["recommended"] is False


def test_identified_without_list_needs_review():
    result = rules.evaluate("seelo 사차인치 탈지 단백질 분말 300g이 조건에 맞습니다.", [], TARGETS)
    assert result["identified"] and result["rank"] is None
    assert result["evaluation"]["needsReview"] is True


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("seelo 사차인치 탈지 단백질 분말 300g을 찾아줘", "query_contains_target"),
        ("https://xodnrdl06066.cafe24.com/product/detail.html?product_no=15 정보", "query_contains_target"),
    ],
)
def test_natural_questions_must_not_include_target(question, reason):
    with pytest.raises(AppError) as error:
        rules.check_set([{"id": "G01", "question": question}], TARGETS)
    assert error.value.details["reason"] == reason


def test_duplicate_query_id_is_rejected():
    with pytest.raises(AppError):
        rules.check_set(
            [{"id": "G01", "question": "식물성 단백질 분말"}, {"id": "G01", "question": "씨앗 단백질 분말"}],
            TARGETS,
        )


def test_failed_calls_are_invalid_not_zero_exposure():
    queries = [{"id": "G01"}, {"id": "G02"}]
    answers = [
        {"query_id": "G01", "repeat": 1, "attempt": 1, "status": "failed"},
        {
            "query_id": "G01",
            "repeat": 1,
            "attempt": 2,
            "status": "ok",
            "identified": True,
            "recommended": True,
            "target_url_cited": False,
        },
        {"query_id": "G02", "repeat": 1, "attempt": 1, "status": "failed"},
        {"query_id": "G02", "repeat": 1, "attempt": 2, "status": "failed"},
    ]
    summary = rules.summarize(queries, 1, answers)
    g01, g02 = summary["queries"]
    assert (g01["valid"], g01["identified"], g01["failedAttempts"]) == (1, 1, 1)
    assert (g02["valid"], g02["missing"], g02["identified"]) == (0, 1, 0)
    # 분모는 정상 응답 1건뿐이다. 실패를 0점으로 넣지 않는다.
    assert summary["totals"]["rates"]["identified"] == 1.0


def test_comparison_requires_same_set_and_condition():
    base = {
        "setId": 1,
        "condition": {
            "provider": "openai",
            "model": "m",
            "toolOptions": "t",
            "repeats": 3,
            "suffixHash": "h",
        },
    }
    rules.comparable(base, base)
    with pytest.raises(AppError) as error:
        rules.comparable(base, {**base, "condition": {**base["condition"], "model": "other"}})
    assert error.value.details["fields"] == ["model"]
    with pytest.raises(AppError):
        rules.comparable(base, {**base, "setId": 2})
