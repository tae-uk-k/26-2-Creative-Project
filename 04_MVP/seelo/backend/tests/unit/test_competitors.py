"""W-05-4 주변 가게 5곳(08 5.4): 동률은 평균 순위로, 5곳 미만, 지점명 묶기, 화면 이름."""

from seelo.domain.metrics import RecView, ResponseView, competitors
from seelo.domain.normalize import normalize_name


def _r(rid: int, *names: str, provider: str = "openai", ok: bool = True, target: str = "") -> ResponseView:
    recs = [RecView(normalize_name(n), n, i, n == target, [], []) for i, n in enumerate(names, 1)]
    return ResponseView(rid, provider, 1, ok, recs, [])


def test_tie_on_count_broken_by_average_rank() -> None:
    views = [_r(1, "A", "B"), _r(2, "B", "C"), _r(3, "A", "B")]  # B 3회, A 2회(평균 1), C 1회
    views.append(_r(4, "C", "D"))  # C 2회(평균 1.5) → A(2회, 1.0) 다음
    assert [n for n, _ in competitors(views)] == ["b", "a", "c", "d"]


def test_fewer_than_five_and_target_and_failed_excluded() -> None:
    views = [
        _r(1, "우리가게", "A", target="우리가게"),
        _r(2, "B", "C", ok=False),  # 추출 실패 응답은 넣지 않음
        _r(3, "A", provider="gemini"),
    ]
    assert competitors(views) == [("a", "A")]


def test_branch_names_grouped_once_per_response() -> None:
    """지점명이 달라도 한 가게. 한 응답에 두 지점이 나와도 등장은 1번, 순위는 더 높은 쪽."""
    views = [
        _r(1, "명동칼국수 본점", "을지면옥"),
        _r(2, "을지면옥", "명동칼국수 명동점", "명동칼국수"),
        _r(3, "Myeongdong Kalguksu Main Branch"),  # 영문 이름은 다른 정규화 이름(한영은 묶지 않음)
    ]
    got = competitors(views)
    # 명동칼국수 2회·평균 (1+2)/2, 을지면옥 2회·평균 (2+1)/2 → 완전히 같아 정규화 이름순
    # 화면 이름: 세 표기가 1번씩 → 먼저 나온 "명동칼국수 본점"
    assert got[0] == ("명동칼국수", "명동칼국수 본점")
    assert got[1] == ("을지면옥", "을지면옥")
    assert got[2][0] == "myeongdongkalguksu"


def test_display_name_most_frequent_then_first_seen() -> None:
    views = [_r(1, "카페 Onion 성수점"), _r(2, "카페Onion"), _r(3, "카페Onion"), _r(4, "카페 Onion 성수점")]
    assert competitors(views) == [("카페onion", "카페 Onion 성수점")]  # 2:2 동률 → 먼저 나온 것
    views.append(_r(5, "카페Onion"))
    assert competitors(views) == [("카페onion", "카페Onion")]


def test_top_five_only() -> None:
    views = [_r(i, f"가게{i}") for i in range(1, 9)]  # 모두 1회·1위 → 이름순 5개
    assert [n for n, _ in competitors(views)] == ["가게1", "가게2", "가게3", "가게4", "가게5"]
