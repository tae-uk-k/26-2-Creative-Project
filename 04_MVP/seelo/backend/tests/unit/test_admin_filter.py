"""A01 상태 판정(03 5장)과 S12 진행 단계(04 7.1 steps)."""

import pytest

from seelo.domain.admin_filter import RequestFacts, display_status, matching
from seelo.domain.fix_steps import fix_steps


@pytest.mark.parametrize(
    ("facts", "hits", "display"),
    [
        (RequestFacts("requested"), {"requested"}, "requested"),
        (RequestFacts("approved"), {"approved"}, "approved"),
        (RequestFacts("rejected"), {"rejected"}, "rejected"),
        (RequestFacts("connecting"), {"connect_waiting"}, "connect_waiting"),
        (RequestFacts("connecting", {"awaiting_approval"}), {"plan_waiting"}, "plan_waiting"),
        (
            RequestFacts("fixing", {"approved", "awaiting_approval"}),
            {"fixing", "plan_waiting"},
            "plan_waiting",
        ),
        (
            RequestFacts("fixing", {"approved"}, has_manual=True),
            {"fixing", "manual_required"},
            "manual_required",
        ),
        (RequestFacts("remeasure_scheduled", {"approved"}), {"remeasure_waiting"}, "remeasure_waiting"),
        (RequestFacts("remeasuring", {"approved"}), {"remeasure_waiting"}, "remeasure_waiting"),
        (RequestFacts("report_ready", {"approved"}), {"report_ready"}, "report_ready"),
        (RequestFacts("remeasure_failed", {"approved"}), {"failed"}, "failed"),
        (RequestFacts("connecting", {"generation_failed"}), {"failed"}, "failed"),
        (
            RequestFacts("remeasuring", {"approved"}, has_manual=True, latest_report_failed=True),
            {"remeasure_waiting", "manual_required", "failed"},
            "failed",  # 대표 상태 순서: failed가 먼저
        ),
        (
            RequestFacts("connecting", {"generating"}),
            set(),
            "connect_waiting",
        ),  # 어느 필터도 아님 → 신청 상태로
    ],
)
def test_filters_and_display(facts: RequestFacts, hits: set[str], display: str) -> None:
    assert matching(facts) == hits
    assert display_status(facts) == display


def _states(
    status: str, connected: bool = False, plans: dict[int, str] | None = None
) -> list[tuple[str, str]]:
    return [(s.key, s.state) for s in fix_steps(status, connected=connected, plan_statuses=plans or {})]


def test_steps_requested_and_rejected() -> None:
    assert _states("requested") == [
        ("received", "done"), ("approved", "current"), ("connect", "todo"), ("review", "todo"),
        ("fixing", "todo"), ("remeasure_waiting", "todo"), ("report", "todo"),
    ]  # fmt: skip
    assert _states("rejected") == [("received", "done")] + [
        (k, "todo") for k in ("approved", "connect", "review", "fixing", "remeasure_waiting", "report")
    ]


def test_steps_connecting_and_review() -> None:
    assert dict(_states("connecting")) == {
        "received": "done", "approved": "done", "connect": "current", "review": "todo",
        "fixing": "todo", "remeasure_waiting": "todo", "report": "todo",
    }  # fmt: skip
    steps = fix_steps("connecting", connected=True, plan_statuses={7: "awaiting_approval", 3: "approved"})
    by = {s.key: s for s in steps}
    assert (by["connect"].state, by["review"].state) == ("done", "done")
    assert by["review"].action_path == "/fix/plans/7" and by["connect"].action_path == "/fix/connect"
    only_awaiting = {
        s.key: s.state
        for s in fix_steps("connecting", connected=True, plan_statuses={7: "awaiting_approval"})
    }
    assert only_awaiting["review"] == "current"


@pytest.mark.parametrize(
    ("status", "fixing", "waiting", "report"),
    [
        ("fixing", "current", "todo", "todo"),
        ("remeasure_scheduled", "done", "current", "todo"),
        ("remeasuring", "done", "done", "current"),
        ("remeasure_failed", "done", "done", "current"),
        ("report_ready", "done", "done", "done"),
    ],
)
def test_steps_after_fixing(status: str, fixing: str, waiting: str, report: str) -> None:
    got = dict(_states(status, connected=True, plans={1: "approved"}))
    assert (got["approved"], got["connect"], got["review"]) == ("done", "done", "done")
    assert (got["fixing"], got["remeasure_waiting"], got["report"]) == (fixing, waiting, report)
