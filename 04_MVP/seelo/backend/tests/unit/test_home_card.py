"""W-06-3 홈 카드(03 4장): 15가지 카드가 모두 나오고 정상 상태에서는 unknown이 나오지 않는다."""

from types import SimpleNamespace as NS

import pytest

from seelo.domain.home_card import CARDS, pick_card


def _s(status: str) -> NS:
    return NS(status=status)


CASES = [
    # (가게, 신청, 정비안 상태들, 카드)
    (None, None, [], "no_store"),
    ("diagnosed", "requested", [], "fix_requested"),
    ("collected", "rejected", [], "fix_rejected"),
    ("collecting", None, [], "measuring"),
    ("measuring", None, [], "measuring"),
    ("measuring", "approved", [], "measuring"),  # 승인 뒤 진단(E9 base_run 없음)
    ("measure_failed", None, [], "measure_failed"),
    ("measure_failed", "approved", [], "measure_failed"),
    ("diagnosed", None, [], "diagnosed"),
    ("collected", None, [], "free_used_store_changed"),
    ("diagnosed", "connecting", ["awaiting_approval"], "plan_needs_approval"),
    ("diagnosed", "fixing", ["approved", "awaiting_approval"], "plan_needs_approval"),
    ("diagnosed", "connecting", ["generating"], "plan_preparing"),
    ("diagnosed", "connecting", ["generation_failed"], "plan_preparing"),
    ("diagnosed", "connecting", [], "connect_needed"),
    ("diagnosed", "fixing", ["approved"], "fixing"),
    ("diagnosed", "remeasure_scheduled", ["approved"], "remeasure_waiting"),
    ("diagnosed", "remeasuring", ["approved"], "remeasuring"),
    ("diagnosed", "remeasure_failed", ["approved"], "remeasure_failed"),
    ("diagnosed", "report_ready", ["approved"], "report_ready"),
]


@pytest.mark.parametrize(("store", "req", "plans", "card"), CASES)
def test_cards(store: str | None, req: str | None, plans: list[str], card: str) -> None:
    got = pick_card(_s(store) if store else None, _s(req) if req else None, [_s(p) for p in plans])
    assert got == card


def test_all_fifteen_cards_covered_and_no_unknown() -> None:
    assert {c for *_, c in CASES} == set(CARDS)
    assert len(CARDS) == 15


def test_revoked_or_manual_do_not_change_card() -> None:
    """연결 끊김·수동 처리는 공통 표시(revokedProviders·manualInProgress)로만 보인다."""
    store, req = _s("diagnosed"), _s("fixing")
    revoked = [NS(provider="google", status="revoked")]
    assert pick_card(store, req, [_s("approved")], revoked, True) == "fixing"


def test_unexpected_combination_is_unknown() -> None:
    assert pick_card(_s("archived"), None, []) == "unknown"
    assert pick_card(_s("diagnosed"), _s("approved"), []) == "unknown"  # E9가 바로 connecting으로 바꾼다
