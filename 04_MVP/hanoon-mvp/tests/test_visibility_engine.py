"""한눈의 핵심 기술인 AI 추천 노출 측정·정보 진단 테스트."""

import pytest

from core.visibility import (
    compare_visibility,
    find_channel_conflicts,
    find_missing_tourist_fields,
    measure_visibility,
)


TARGET = "망원 골목국수"
CANONICAL_FACTS = {
    "hours": "Tue-Sun 11:30-20:30",
    "payment": "International cards accepted",
}
CONDITIONS = ("english_menu", "solo_dining")
SETUP = {
    "prompt_count": 2,
    "repeat_count": 2,
    "models": ["ChatGPT", "Gemini"],
    "language": "English",
}


def recommendation(rank, *, hours=None, payment=None, conditions=()):
    return {
        "name": TARGET,
        "rank": rank,
        "facts": {"hours": hours, "payment": payment},
        "conditions": list(conditions),
    }


def test_repeated_ai_answers_are_converted_to_visibility_metrics():
    responses = [
        {
            "recommendations": [
                recommendation(
                    1,
                    hours=CANONICAL_FACTS["hours"],
                    payment=CANONICAL_FACTS["payment"],
                    conditions=CONDITIONS,
                )
            ]
        },
        {
            "recommendations": [
                recommendation(
                    2,
                    hours="Open Monday",
                    payment=CANONICAL_FACTS["payment"],
                    conditions=("english_menu",),
                )
            ]
        },
        {"recommendations": [{"name": "다른 가게", "rank": 1}]},
        {
            "recommendations": [
                recommendation(3, hours=CANONICAL_FACTS["hours"])
            ]
        },
    ]

    result = measure_visibility(responses, TARGET, CANONICAL_FACTS, CONDITIONS)

    assert result == {
        "responseCount": 4,
        "appearanceCount": 3,
        "appearanceRate": 75.0,
        "averageRank": 2.0,
        "accuracy": 66.7,
        "conditionCoverage": 50.0,
    }


def test_no_recommendation_returns_zero_without_division_error():
    responses = [{"recommendations": []}, {"recommendations": [{"name": "다른 가게"}]}]

    result = measure_visibility(responses, TARGET, CANONICAL_FACTS, CONDITIONS)

    assert result["appearanceRate"] == 0.0
    assert result["averageRank"] == 0.0
    assert result["accuracy"] == 0.0
    assert result["conditionCoverage"] == 0.0


def test_missing_tourist_information_is_detected():
    store = {
        "name_en": "Mangwon Golmok Noodles",
        "description_en": "Small Korean noodle restaurant.",
        "menu_prices": [],
        "hours": "Tue-Sun 11:30-20:30",
        "address": "21 World Cup-ro 13-gil",
        "payment_methods": [],
        "dietary_options": None,
    }

    assert find_missing_tourist_fields(store) == [
        "menu_prices",
        "payment_methods",
        "dietary_options",
    ]


def test_conflicting_hours_are_found_across_channels():
    channels = {
        "Google Maps": {"hours": "Closed Monday", "address": "21 World Cup-ro"},
        "Naver Place": {"hours": "Closed Monday", "address": "21  World Cup-ro"},
        "Instagram": {"hours": "Monday 11:30-20:30", "address": "21 World Cup-ro"},
    }

    conflicts = find_channel_conflicts(channels, fields=("hours", "address"))

    assert conflicts == {
        "hours": {
            "Google Maps": "Closed Monday",
            "Naver Place": "Closed Monday",
            "Instagram": "Monday 11:30-20:30",
        }
    }


def test_before_after_comparison_requires_the_same_measurement_setup():
    changed_setup = {**SETUP, "language": "Korean"}

    with pytest.raises(ValueError, match="조건이 같아야"):
        compare_visibility(
            [{"recommendations": []}],
            [{"recommendations": []}],
            before_setup=SETUP,
            after_setup=changed_setup,
            target_name=TARGET,
            canonical_facts=CANONICAL_FACTS,
            required_conditions=CONDITIONS,
        )


def test_before_after_comparison_calculates_improvement_delta():
    before = [
        {"recommendations": [recommendation(3, hours="Wrong hours")]},
        {"recommendations": []},
    ]
    after = [
        {
            "recommendations": [
                recommendation(
                    1,
                    hours=CANONICAL_FACTS["hours"],
                    payment=CANONICAL_FACTS["payment"],
                    conditions=CONDITIONS,
                )
            ]
        },
        {
            "recommendations": [
                recommendation(
                    2,
                    hours=CANONICAL_FACTS["hours"],
                    payment=CANONICAL_FACTS["payment"],
                    conditions=CONDITIONS,
                )
            ]
        },
    ]

    comparison = compare_visibility(
        before,
        after,
        before_setup=SETUP,
        after_setup=SETUP,
        target_name=TARGET,
        canonical_facts=CANONICAL_FACTS,
        required_conditions=CONDITIONS,
    )

    assert comparison["delta"] == {
        "appearanceRate": 50.0,
        "averageRank": 1.5,
        "accuracy": 100.0,
        "conditionCoverage": 100.0,
    }
