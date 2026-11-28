"""W-12-2 손 계산 3개·질문 제외·금지어·주변 가게 재계산(10 3장)."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from seelo.domain.metrics import RecView, ResponseView, compute_run_metrics
from seelo.domain.report_builder import (
    BANNED_TERMS,
    ChangeView,
    QuestionView,
    RunMetricsView,
    assert_no_banned_terms,
    build_report,
)
from seelo.schemas.report import ReportContent


def views(count, competitor, *, missing_gemini=False):
    out = []
    for p in ("openai", "gemini"):
        if p == "gemini" and missing_gemini:
            continue
        for i in range(2):
            recs = [RecView(competitor.lower(), competitor, 1, False, [], [])]
            if i < count:
                recs.append(RecView("target", "우리", 2, True, [], []))
            out.append(ResponseView(len(out) + 1, p, 1, True, recs, []))
    return out


def report_case(n):
    data = json.loads(
        (Path(__file__).parents[1] / f"fixtures/report/case_{n}.json").read_text(encoding="utf-8")
    )
    inp = data["input"]
    b = views(inp["beforeCount"], "A", missing_gemini=inp["missingGemini"])
    a = views(inp["afterCount"], inp["afterCompetitor"])

    def view(responses, date):
        return RunMetricsView(
            compute_run_metrics(responses, question_ids=[1], failed=0, total=len(responses)).rows,
            responses,
            datetime.fromisoformat(date),
            1,
            2,
            {"openai": "fake-openai", "gemini": "fake-gemini"},
        )

    args = dict(
        before=view(b, "2026-10-01T00:00:00+00:00"),
        after=view(a, "2026-10-29T00:00:00+00:00"),
        questions=[QuestionView(1, 1, "en", "Where can I eat in Myeongdong?", "명동에서 식사할 곳은?")],
        changes=[
            ChangeView(
                provider="google",
                field="phone",
                field_label="전화번호",
                before_value=None,
                applied_value="02-123-4567",
                status="manual_done",
                method="manual",
                verified_at=None,
                remeasure_match="unknown",
            )
        ],
        fix_completed_at=datetime.fromisoformat("2026-10-15T00:00:00+00:00"),
        interval_days=14,
        early=False,
    )
    return data, args


@pytest.mark.parametrize("n", [1, 2, 3])
def test_full_report_matches_hand_calculated_fixture(n):
    data, args = report_case(n)
    report = build_report(**args)
    assert report.model_dump(mode="json", by_alias=True) == ReportContent.model_validate(
        data["expected"]
    ).model_dump(mode="json", by_alias=True)
    assert_no_banned_terms(report)


@pytest.mark.parametrize("term", BANNED_TERMS)
def test_banned_terms_recursive_and_case_insensitive(term):
    with pytest.raises(ValueError, match="report_banned_term"):
        assert_no_banned_terms({"nested": [{"text": term.upper()}]})
    assert_no_banned_terms({"notices": [term], "safe": "변화"})
    with pytest.raises(ValueError):
        assert_no_banned_terms({"nested": {"notices": [term]}})


def test_citations_use_google_path_and_differs_note():
    _, args = report_case(1)
    r = args["after"].responses[0]
    r.source_domains = ["google.com", "place.map.kakao.com"]
    r.source_urls = ["https://www.google.com/maps/place/x", "https://place.map.kakao.com/123"]
    args["after"] = replace(args["after"], responses=[r])
    args["changes"][0].remeasure_match = "differs"
    report = build_report(**args)
    assert report.sources["mapCitations"]["after"] == {"googleMaps": 1, "kakaoMap": 1}
    assert report.changes[0].note == "지금 지도 값이 달라요(사장님이 바꿨거나 아직 반영 전)"


def test_competitor_that_becomes_target_is_excluded_from_recount():
    _, args = report_case(1)
    args["after"].responses[0].recs.append(RecView("a", "A", 1, True, [], []))
    report = build_report(**args)
    assert report.competitors.before_top5[0].after.openai.appearance_count == 0


@pytest.mark.parametrize("change", ["questions", "repeats", "transport"])
def test_mismatched_measurement_conditions_reject_report(change):
    _, args = report_case(1)
    if change == "questions":
        args["after"] = replace(args["after"], question_set_id=2)
    elif change == "repeats":
        args["after"] = replace(args["after"], repeat_count=1)
    else:
        args["after"] = replace(
            args["after"],
            models={
                "openai": "codex-cli/gpt-6.1-sol",
                "gemini": "gemini-cli/auto",
            },
        )
    with pytest.raises(ValueError, match="report_conditions_mismatch"):
        build_report(**args)


def test_local_cli_report_is_labeled_and_ordinary_model_update_allowed():
    _, args = report_case(1)
    args["after"] = replace(args["after"], models={"openai": "new-api-model", "gemini": "new-gemini-model"})
    assert build_report(**args).notices == []
    models = {"openai": "codex-cli/gpt-6.1-sol", "gemini": "gemini-cli/auto"}
    args["before"] = replace(args["before"], models=models)
    args["after"] = replace(args["after"], models=models)
    assert any("로컬 CLI 시험" in notice for notice in build_report(**args).notices)
