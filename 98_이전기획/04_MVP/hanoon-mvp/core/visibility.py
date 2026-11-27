"""AI 추천 노출 진단의 핵심 계산 로직.

외부 AI API 호출부와 분리된 순수 함수라서 동일한 입력에는 항상 동일한
결과를 반환한다. MVP에서는 이 모듈로 반복 응답의 노출 지표, 관광객용
정보 누락, 채널 간 불일치를 검증한다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


REQUIRED_TOURIST_FIELDS = (
    "name_en",
    "description_en",
    "menu_prices",
    "hours",
    "address",
    "payment_methods",
    "dietary_options",
)

MEASUREMENT_SETUP_FIELDS = (
    "prompt_count",
    "repeat_count",
    "models",
    "language",
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _round_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def find_missing_tourist_fields(
    store: Mapping[str, Any],
    required_fields: Iterable[str] = REQUIRED_TOURIST_FIELDS,
) -> list[str]:
    """외국인 관광객의 선택에 필요한 정보 중 비어 있는 항목을 반환한다."""

    missing = []
    for field in required_fields:
        value = store.get(field)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(field)
    return missing


def find_channel_conflicts(
    channels: Mapping[str, Mapping[str, Any]],
    fields: Iterable[str] = ("name", "address", "hours", "phone"),
) -> dict[str, dict[str, str]]:
    """Google·Naver·SNS 등에서 서로 다르게 적힌 정보를 찾는다.

    공백과 영문 대소문자 차이는 같은 값으로 간주하고, 실제 값이 두 종류
    이상인 필드만 채널별 원문과 함께 반환한다.
    """

    conflicts: dict[str, dict[str, str]] = {}
    for field in fields:
        grouped_values: defaultdict[str, dict[str, str]] = defaultdict(dict)
        for channel_name, channel_data in channels.items():
            raw_value = channel_data.get(field)
            normalized = _normalize_text(raw_value)
            if normalized:
                grouped_values[normalized][channel_name] = str(raw_value).strip()

        if len(grouped_values) > 1:
            conflicts[field] = {
                channel: value
                for group in grouped_values.values()
                for channel, value in group.items()
            }
    return conflicts


def measure_visibility(
    responses: Sequence[Mapping[str, Any]],
    target_name: str,
    canonical_facts: Mapping[str, Any],
    required_conditions: Iterable[str],
) -> dict[str, float | int]:
    """반복된 AI 추천 응답에서 노출·순서·정확도·조건 반영률을 계산한다.

    각 응답은 ``recommendations`` 배열을 가지며 추천 항목은 ``name``,
    ``rank``, ``facts``, ``conditions``를 포함할 수 있다. 정확도와 조건
    반영률은 누락을 오답으로 포함해 과대평가를 막는다.
    """

    if not responses:
        raise ValueError("최소 1개의 AI 응답이 필요합니다.")

    normalized_target = _normalize_text(target_name)
    expected_facts = dict(canonical_facts)
    expected_conditions = tuple(required_conditions)
    appearances: list[Mapping[str, Any]] = []

    for response in responses:
        recommendations = response.get("recommendations") or []
        match = next(
            (
                recommendation
                for recommendation in recommendations
                if _normalize_text(recommendation.get("name")) == normalized_target
            ),
            None,
        )
        if match is not None:
            appearances.append(match)

    ranks = [float(item["rank"]) for item in appearances if item.get("rank") is not None]

    correct_facts = 0
    for item in appearances:
        observed_facts = item.get("facts") or {}
        correct_facts += sum(
            _normalize_text(observed_facts.get(field)) == _normalize_text(expected)
            for field, expected in expected_facts.items()
        )

    matched_conditions = 0
    for item in appearances:
        observed_conditions = {
            _normalize_text(condition) for condition in (item.get("conditions") or [])
        }
        matched_conditions += sum(
            _normalize_text(condition) in observed_conditions
            for condition in expected_conditions
        )

    fact_opportunities = len(appearances) * len(expected_facts)
    condition_opportunities = len(appearances) * len(expected_conditions)

    return {
        "responseCount": len(responses),
        "appearanceCount": len(appearances),
        "appearanceRate": _round_rate(len(appearances), len(responses)),
        "averageRank": round(sum(ranks) / len(ranks), 1) if ranks else 0.0,
        "accuracy": _round_rate(correct_facts, fact_opportunities),
        "conditionCoverage": _round_rate(matched_conditions, condition_opportunities),
    }


def _measurement_signature(setup: Mapping[str, Any]) -> tuple[Any, ...]:
    signature = []
    for field in MEASUREMENT_SETUP_FIELDS:
        value = setup.get(field)
        if isinstance(value, (list, tuple)):
            value = tuple(_normalize_text(item) for item in value)
        elif isinstance(value, str):
            value = _normalize_text(value)
        signature.append(value)
    return tuple(signature)


def compare_visibility(
    before_responses: Sequence[Mapping[str, Any]],
    after_responses: Sequence[Mapping[str, Any]],
    *,
    before_setup: Mapping[str, Any],
    after_setup: Mapping[str, Any],
    target_name: str,
    canonical_facts: Mapping[str, Any],
    required_conditions: Iterable[str],
) -> dict[str, Any]:
    """같은 측정 조건인지 확인한 뒤 정비 전후 지표와 변화량을 반환한다."""

    if _measurement_signature(before_setup) != _measurement_signature(after_setup):
        raise ValueError("정비 전후의 질문·반복·모델·언어 조건이 같아야 합니다.")

    before = measure_visibility(
        before_responses,
        target_name,
        canonical_facts,
        required_conditions,
    )
    after = measure_visibility(
        after_responses,
        target_name,
        canonical_facts,
        required_conditions,
    )

    return {
        "before": before,
        "after": after,
        "delta": {
            "appearanceRate": round(after["appearanceRate"] - before["appearanceRate"], 1),
            "averageRank": round(before["averageRank"] - after["averageRank"], 1),
            "accuracy": round(after["accuracy"] - before["accuracy"], 1),
            "conditionCoverage": round(
                after["conditionCoverage"] - before["conditionCoverage"],
                1,
            ),
        },
    }
