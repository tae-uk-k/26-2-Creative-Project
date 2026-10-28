"""5단계 순수 함수: 영업시간·지역·편의 정보·페이지 해석·비용(08 0장, 07 6.3·6.6, 06 6장)."""

import json

import pytest

from seelo.domain.attributes import google_value, true_labels
from seelo.domain.hours import format_hours_ko, from_google_periods, hours_diff, to_weekly_hours
from seelo.domain.region import from_google, from_kakao_address, trim_en, trim_ko
from seelo.domain.webpage import find_menu_link, has_english_page, instagram_username, page_text
from seelo.schemas.llm import DayHoursOut, IntervalOut, WeeklyHoursOut


def test_from_google_periods_and_diff() -> None:
    w = from_google_periods(
        [{"open": {"day": 1, "hour": 11, "minute": 0}, "close": {"day": 1, "hour": 21, "minute": 0}}]
    )
    assert w["days"]["mon"] == [{"open": "11:00", "close": "21:00"}]
    assert all(w["days"][d] is None for d in ("tue", "wed", "thu", "fri", "sat", "sun"))
    other = from_google_periods(
        [{"open": {"day": 1, "hour": 11, "minute": 0}, "close": {"day": 1, "hour": 22, "minute": 0}}]
    )
    assert hours_diff(w, other) == ["mon"]
    assert hours_diff(w, w) == []
    always = from_google_periods([{"open": {"day": 0, "hour": 0, "minute": 0}}])  # 24시간 영업
    assert always["days"]["sun"] == [{"open": "00:00", "close": "24:00"}]


def test_to_weekly_hours_rules() -> None:
    out = WeeklyHoursOut(
        days=[
            DayHoursOut(
                day="mon",
                closed=False,
                intervals=[IntervalOut(open="11:00", close="21:00")],
                breaks=[IntervalOut(open="15:00", close="17:00")],
            ),
            DayHoursOut(day="tue", closed=True, intervals=[], breaks=[]),
            DayHoursOut(
                day="wed", closed=False, intervals=[IntervalOut(open="오전 11시", close="9pm")], breaks=[]
            ),
        ],
        notes="공휴일 휴무",
    )
    w = to_weekly_hours(out)
    assert w["days"]["mon"] == [{"open": "11:00", "close": "21:00"}]
    assert w["breaks"]["mon"] == [{"start": "15:00", "end": "17:00"}]
    assert w["days"]["tue"] == []  # 쉬는 날
    assert w["days"]["wed"] is None  # 시각 형식이 틀리면 추측하지 않고 정보 없음
    assert w["days"]["thu"] is None  # 나오지 않은 요일
    assert w["notes"] == "공휴일 휴무"
    assert format_hours_ko(w) == "월 11:00~21:00 / 화 휴무"
    assert to_weekly_hours(None) is None


@pytest.mark.parametrize(
    ("raw", "ko"),
    [
        ("명동2가", "명동"),
        ("성수1동", "성수동"),
        ("성수동", "성수동"),
        ("종로1가", "종로"),
        ("익선동", "익선동"),
    ],
)
def test_trim_ko(raw: str, ko: str) -> None:
    assert trim_ko(raw) == ko


def test_trim_en_and_from_google_order() -> None:
    assert trim_en("Myeong-dong 2(i)-ga") == "Myeong-dong"
    assert trim_en("Seongsu-dong 1(il)-ga") == "Seongsu-dong"
    ko = {
        "addressComponents": [
            {"longText": "중구", "types": ["sublocality_level_1"]},
            {"longText": "명동2가", "types": ["sublocality_level_2", "sublocality"]},
            {"longText": "서울특별시", "types": ["locality"]},
        ]
    }
    en = {"addressComponents": [{"longText": "Myeong-dong 2(i)-ga", "types": ["sublocality_level_2"]}]}
    assert from_google(ko, en) == ("명동", "Myeong-dong")  # level_2가 먼저
    only_locality = {"addressComponents": [{"longText": "서울특별시", "types": ["locality"]}]}
    assert from_google(only_locality, None) == ("서울특별시", None)
    assert from_google(None, None) == (None, None)
    assert from_kakao_address("서울 중구 명동2가 25-2") == "명동"
    assert from_kakao_address("서울") is None


def test_attributes_three_values() -> None:
    g = {
        "servesVegetarianFood": False,
        "paymentOptions": {"acceptsCreditCards": True},
        "priceLevel": "PRICE_LEVEL_EXPENSIVE",
    }
    assert google_value("vegetarian", g) is False  # 거짓은 사실
    assert google_value("card_payment", g) is True
    assert google_value("budget", g) is False
    assert google_value("reservation", g) is None  # 필드가 없을 때만 정보 없음
    assert google_value("alcohol", {"servesWine": True}) is True
    assert google_value("halal", g) is None
    assert true_labels({"takeout": True, "reservable": False, "servesBeer": True}) == ["포장 가능", "주류"]


HOME = """<html lang="ko"><head><style>.x{}</style></head><body>
<script>var secret = 1;</script><noscript>켜 주세요</noscript>
<h1>데모   식당</h1><p>영업시간
매일 11시</p>
<a href="/menu">메뉴</a><a href="https://other.example/menu">남의 메뉴</a>
<a href="/about">소개</a><a href="https://www.instagram.com/demo_shop/">인스타</a>
</body></html>"""


def test_page_text_menu_and_english() -> None:
    text = page_text(HOME)
    assert text.startswith("데모 식당 영업시간 매일 11시")
    assert "secret" not in text and "켜 주세요" not in text and ".x{}" not in text
    assert len(page_text("<p>" + "가" * 30000 + "</p>")) == 20000
    assert find_menu_link(HOME, "https://demo.example/") == "https://demo.example/menu"
    assert find_menu_link('<a href="/food-list">x</a>', "https://d.example/") == "https://d.example/food-list"
    assert find_menu_link('<a href="https://other.example/menu">메뉴</a>', "https://d.example/") is None
    assert not has_english_page(HOME, "https://demo.example/")
    assert has_english_page('<html lang="en-US"></html>', "https://d.example/")
    assert has_english_page('<link rel="alternate" hreflang="en" href="/en">', "https://d.example/")
    assert has_english_page('<a href="/en">EN</a>', "https://d.example/")
    assert has_english_page('<a href="/global">English</a>', "https://d.example/")


@pytest.mark.parametrize(
    ("url", "username"),
    [
        ("https://www.instagram.com/demo_shop/", "demo_shop"),
        ("https://instagram.com/demo.shop?igsh=abc", "demo.shop"),
        ("https://www.instagram.com/p/Cx123/", None),
        ("https://www.instagram.com/reel/abc", None),
        ("https://www.instagram.com/explore/", None),
        ("https://www.instagram.com/accounts/login/", None),
        ("https://www.instagram.com/stories/demo/", None),
        ("https://www.instagram.com/demo/tagged/", None),
        ("https://facebook.com/demo", None),
        (None, None),
    ],
)
def test_instagram_username(url: str | None, username: str | None) -> None:
    assert instagram_username(url) == username


def test_cost_usd(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    from seelo.config import get_settings
    from seelo.integrations import llm

    f = tmp_path / "pricing.json"
    f.write_text(
        json.dumps({"openai": {"m1": {"inputPer1M": 2.0, "outputPer1M": 8.0, "webSearchPerCall": 0.01}}})
    )
    monkeypatch.setenv("PRICING_FILE", str(f))
    get_settings.cache_clear()
    llm._pricing.cache_clear()
    try:
        assert llm.cost_usd(
            "openai", "m1", input_tokens=1_000_000, output_tokens=500_000, search_calls=2
        ) == pytest.approx(2.0 + 4.0 + 0.02)
        assert llm.cost_usd("openai", "unknown", input_tokens=10, output_tokens=10) == 0.0
    finally:
        get_settings.cache_clear()
        llm._pricing.cache_clear()
