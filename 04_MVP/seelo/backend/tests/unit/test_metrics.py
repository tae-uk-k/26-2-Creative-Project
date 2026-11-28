"""W-05-3 지표(08 5장): fixtures/metrics/case_{1,2,3}.json 손 계산과 같은지. 저장 행 전부를 비교한다."""

import json
from pathlib import Path
from typing import Any

import pytest

from seelo.domain.metrics import (
    MetricRow,
    RecView,
    ResponseView,
    competitor_position,
    compute_run_metrics,
    target_sources,
    top_sources,
)
from seelo.domain.normalize import normalize_name

CASES = Path(__file__).parents[1] / "fixtures" / "metrics"
FOUR = ("success_count", "appearance_count", "appearance_rate", "avg_rank")


def _views(case: dict[str, Any]) -> list[ResponseView]:
    return [
        ResponseView(
            response_id=r["id"],
            provider=r["provider"],
            question_id=r["question_id"],
            extraction_ok=r["ok"],
            source_domains=r["sources"],
            recs=[
                RecView(
                    normalized_name=normalize_name(x["name"]),
                    name=x["name"],
                    rank=x["rank"],
                    is_target=x.get("target", False),
                    source_domains=x.get("sources", []),
                    mentioned_attributes=[],
                )
                for x in r["recs"]
            ],
        )
        for r in case["responses"]
    ]


def _expected_rows(case: dict[str, Any]) -> list[tuple]:
    exp = case["expected"]
    rows: list[tuple] = []
    for provider, by_q in exp["target"].items():
        for q, four in by_q.items():
            qid = None if q == "all" else int(q)
            rows += [
                (provider, qid, "target", "target", m, v, d, None, None)
                for m, (v, d) in zip(FOUR, four, strict=True)
            ]
    for order, c in enumerate(exp["competitors"], 1):
        for provider in case["providers"]:
            rows += [
                (provider, None, "competitor", c["name"], m, v, d, order, c["display"])
                for m, (v, d) in zip(FOUR, c[provider], strict=True)
            ]
    for provider, domains in exp["sources"].items():
        for domain, ((cv, cd), (tv, td)) in domains.items():
            rows.append((provider, None, "source", domain, "citation_count", cv, cd, None, None))
            rows.append((provider, None, "source", domain, "target_citation_count", tv, td, None, None))
    return rows


def _key(row: tuple) -> tuple:
    return tuple("" if x is None else str(x) for x in row[:5])


def _as_tuple(m: MetricRow) -> tuple:
    return (
        m.provider,
        m.question_id,
        m.subject_type,
        m.subject_name,
        m.metric_name,
        m.value,
        m.denominator,
        m.rank_order,
        m.display_name,
    )


@pytest.mark.parametrize("name", ["case_1", "case_2", "case_3"])
def test_hand_calculated_cases(name: str) -> None:
    case = json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))
    result = compute_run_metrics(
        _views(case),
        question_ids=case["question_ids"],
        failed=case["failed"],
        total=case["total"],
        providers=case["providers"],
    )
    got = sorted((_as_tuple(m) for m in result.rows), key=_key)
    want = sorted(_expected_rows(case), key=_key)
    assert [_key(r) for r in got] == [_key(r) for r in want]  # 같은 행(대상·지표)이 빠짐없이
    for g, w in zip(got, want, strict=True):
        assert g[5] == (None if w[5] is None else pytest.approx(w[5])), g
        assert g[6:] == w[6:], g
    exp = case["expected"]
    assert result.failure_rate == pytest.approx(exp["failure_rate"])
    assert result.competitors == [c["name"] for c in exp["competitors"]]
    assert competitor_position(result.rows) == tuple(exp["position"])
    assert top_sources(result.rows) == [tuple(x) for x in exp["top_sources"]]
    assert target_sources(result.rows) == [tuple(x) for x in exp["target_sources"]]


def _resp(
    rid: int, provider: str = "openai", *, ok: bool = True, recs: list[RecView] | None = None
) -> ResponseView:
    return ResponseView(rid, provider, 1, ok, recs or [], [])


def _rec(name: str, rank: int, target: bool = False) -> RecView:
    return RecView(normalize_name(name), name, rank, target, [], [])


def _value(rows: list[MetricRow], metric: str, provider: str = "openai") -> Any:
    return next(
        r.value
        for r in rows
        if r.subject_type == "target"
        and r.question_id is None
        and r.provider == provider
        and r.metric_name == metric
    )


def test_zero_appearance_is_rate_zero_and_avg_none() -> None:
    rows = compute_run_metrics([_resp(1, recs=[_rec("A", 1)])], question_ids=[1], failed=0, total=1).rows
    assert (_value(rows, "appearance_rate"), _value(rows, "avg_rank")) == (0.0, None)


def test_zero_success_is_none_not_zero() -> None:
    """추출이 모두 실패하면 측정하지 못함(None). 0%로 보이면 안 된다."""
    rows = compute_run_metrics([_resp(1, ok=False)], question_ids=[1], failed=0, total=1).rows
    assert _value(rows, "success_count") == 0
    assert (_value(rows, "appearance_rate"), _value(rows, "avg_rank")) == (None, None)
    assert _value(rows, "appearance_rate", "gemini") is None  # 응답이 아예 없는 공급자도 행은 있다


def test_source_rows_top_twenty_plus_target_domains() -> None:
    """출처는 공급자별 상위 20개 + 우리 가게 추천에 붙은 도메인. unknown은 넣지 않는다."""
    views = [ResponseView(i, "openai", 1, True, [], [f"site{i:02d}.com", "common.com"]) for i in range(1, 25)]
    target = RecView("우리", "우리", 1, True, ["zzz-rare.com", "unknown"], [])
    views.append(ResponseView(99, "openai", 1, True, [target], ["zzz-rare.com", "unknown"]))
    rows = compute_run_metrics(views, question_ids=[1], failed=0, total=25, providers=["openai"]).rows
    domains = {r.subject_name for r in rows if r.subject_type == "source"}
    assert "common.com" in domains and "zzz-rare.com" in domains and "unknown" not in domains
    assert len(domains) == 21  # common + site01~site19(이름순) + rare
    assert "site20.com" not in domains
