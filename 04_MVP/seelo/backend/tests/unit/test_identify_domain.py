"""4단계 순수 함수(14 2.1~2.3의 예시 = 테스트, 07 1장 정규화 각 3개 이상)."""

import pytest

from seelo.domain.categories import classify_category
from seelo.domain.geo import haversine_m, parse_naver_coord
from seelo.domain.matching import naver_fingerprint, pick_same_place
from seelo.domain.normalize import (
    domain_of,
    map_kind,
    name_similarity,
    normalize_address,
    normalize_name,
    normalize_phone,
    same_name,
)
from seelo.integrations import Place


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 14 2.1 예시
        ("명동교자 본점", "명동교자"),
        ("Myeongdong Kyoja (Main)", "myeongdongkyoja"),
        ("교촌치킨 명동점", "교촌치킨"),
        ("Cafe Onion Seongsu Branch", "cafeonion"),
        ("스타벅스 R 명동점", "스타벅스r"),
        ("점", "점"),
        # 대소문자
        ("MYEONGDONG KYOJA", "myeongdongkyoja"),
        ("Cafe ONION", "cafeonion"),
        ("ｃａｆｅ　Ｏｎｉｏｎ", "cafeonion"),  # 전각(NFKC)
        # 공백·기호
        ("명동 교자", "명동교자"),
        ("명동-교자!", "명동교자"),
        ("Cafe&Onion", "cafeonion"),
        # 지점명(한글·영문)
        ("명동교자 명동본점", "명동교자"),
        ("런던베이글뮤지엄 안국점", "런던베이글뮤지엄"),
        ("Starbucks Myeongdong Store", "starbucks"),
        ("Onion Main Branch", "onion"),
        ("명동교자직영점", "명동교자"),
        # 괄호
        ("명동교자(본점)", "명동교자"),
        ("[명동] 교자", "교자"),
        ("Kyoja (Myeongdong)", "kyoja"),
        # 한영 혼합
        ("카페 Onion 성수점", "카페onion"),
        ("BHC치킨 명동점", "bhc치킨"),
        ("명동 Kyoja 2호점", "명동kyoja"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_normalize_phone_address_domain() -> None:
    assert normalize_phone("+82 2-776-5348") == "027765348"
    assert normalize_phone("02) 776-5348") == "027765348"
    assert normalize_phone(None) == ""
    assert normalize_address("서울 중구 명동10길 29") == ("명동10길", "29")
    assert normalize_address("서울특별시 성동구 아차산로9길 8 1층") == ("아차산로9길", "8")
    assert normalize_address("명동2가 25-2") is None
    assert domain_of("https://www.TripAdvisor.com/x") == "tripadvisor.com"


@pytest.mark.parametrize(
    ("domain", "url", "kind"),
    [
        ("place.map.kakao.com", "", "kakao_map"),
        ("google.com", "https://google.com/maps/place/x", "google_maps"),
        ("google.com", "https://google.com/search?q=x", None),
        ("maps.app.goo.gl", "", "google_maps"),
        ("naver.me", "", "naver_map"),
        ("instagram.com", "", None),
    ],
)
def test_map_kind(domain: str, url: str, kind: str | None) -> None:
    assert map_kind(domain, url) == kind


def test_same_name() -> None:
    assert same_name("명동교자", "명동 교자", 85)
    assert not same_name("명동교자", "명동칼국수", 85)
    assert name_similarity("명동교자 본점", "명동교자") == 100
    assert name_similarity("", "명동교자") == 0


def test_geo() -> None:
    assert haversine_m(37.5627, 126.9858, 37.5636, 126.9858) == pytest.approx(100.1, abs=0.2)
    assert parse_naver_coord("1269858123") == pytest.approx(126.9858123)
    assert parse_naver_coord("126.9858123") == pytest.approx(126.9858123)
    assert parse_naver_coord(375636000) == pytest.approx(37.5636)


def _p(name: str, lat: float, lng: float, provider: str = "kakao", **kw: object) -> Place:
    return Place(
        provider,
        kw.get("eid"),
        name,
        kw.get("address"),
        lat,
        lng,
        None,
        list(kw.get("cats", [])),
        None,
        dict(kw.get("raw", {})),
    )  # type: ignore[arg-type]


REF = _p("명동교자", 37.5627, 126.9858, "google")
LAT_PER_M = 1 / 111_195  # 위도 1m


def test_pick_same_place() -> None:
    a = _p("명동교자 본점", 37.5627 + 40 * LAT_PER_M, 126.9858)
    b = _p("명동교자", 37.5627 + 180 * LAT_PER_M, 126.9858)
    c = _p("명동칼국수", 37.5627 + 10 * LAT_PER_M, 126.9858)
    d = _p("명동 교자", 37.5627 + 60 * LAT_PER_M, 126.9858)
    assert pick_same_place(REF, [a, b], names=["명동교자"], threshold=85) is a
    assert pick_same_place(REF, [c], names=["명동교자"], threshold=85) is None
    assert pick_same_place(REF, [d, a], names=["명동교자"], threshold=85) is a  # 유사도 같으면 가까운 것
    # 100m 경계: 99m 같음, 101m 다름
    near = _p("명동교자", 37.5627 + 99 * LAT_PER_M, 126.9858)
    far = _p("명동교자", 37.5627 + 101 * LAT_PER_M, 126.9858)
    assert pick_same_place(REF, [near], names=["명동교자"], threshold=85) is near
    assert pick_same_place(REF, [far], names=["명동교자"], threshold=85) is None


def test_naver_fingerprint_uses_road_address() -> None:
    p1 = _p("명동교자 본점", 0, 0, "naver", raw={"roadAddress": "서울 중구 명동10길 29"})
    p2 = _p("명동교자", 0, 0, "naver", raw={"roadAddress": "서울 중구 명동10길 29"})
    p3 = _p("명동교자", 0, 0, "naver", raw={"roadAddress": "서울 중구 명동길 1"})
    assert naver_fingerprint(p1) == naver_fingerprint(p2) != naver_fingerprint(p3)
    assert len(naver_fingerprint(p1)) == 64


@pytest.mark.parametrize(
    ("places", "expected"),
    [
        ([_p("x", 0, 0, "google", raw={"primaryType": "korean_restaurant"})], "restaurant"),
        ([_p("x", 0, 0, "google", cats=["coffee_shop", "food"])], "cafe"),
        ([_p("x", 0, 0, "google", raw={"primaryType": "wine_bar"}, cats=["restaurant"])], "bar"),
        ([_p("x", 0, 0, "kakao", cats=["FD6", "음식점 > 술집 > 호프,요리주점"])], "bar"),
        ([_p("x", 0, 0, "kakao", cats=["CE7", "음식점 > 카페 > 커피전문점"])], "cafe"),
        ([_p("x", 0, 0, "kakao", cats=["FD6", "음식점 > 한식 > 육류,고기 > 바베큐"])], "restaurant"),
        ([_p("x", 0, 0, "naver", cats=["술집>요리주점"])], "bar"),
        ([_p("x", 0, 0, "naver", cats=["카페,디저트>베이커리"])], "cafe"),
        ([_p("x", 0, 0, "naver", cats=["한식>칼국수,만두"])], "restaurant"),
    ],
)
def test_classify_category_targets(places: list[Place], expected: str) -> None:
    assert classify_category(places) == expected


@pytest.mark.parametrize(
    "places",
    [
        # 비대상 5곳(W-02-4): 미용실·편의점·약국·옷가게·호텔
        [_p("x", 0, 0, "google", cats=["hair_care"]), _p("x", 0, 0, "kakao", cats=["", "미용 > 미용실"])],
        [
            _p("x", 0, 0, "google", cats=["convenience_store", "store"]),
            _p("x", 0, 0, "kakao", cats=["CS2", "가정,생활 > 편의점"]),
        ],
        [_p("x", 0, 0, "google", cats=["pharmacy", "health"]), _p("x", 0, 0, "naver", cats=["약국"])],
        [_p("x", 0, 0, "google", cats=["clothing_store"]), _p("x", 0, 0, "naver", cats=["패션>의류"])],
        [
            _p("x", 0, 0, "google", cats=["lodging", "hotel"]),
            _p("x", 0, 0, "kakao", cats=["AD5", "여행 > 숙박 > 호텔"]),
        ],
    ],
)
def test_classify_category_rejects_non_targets(places: list[Place]) -> None:
    assert classify_category(places) is None


def test_google_unknown_falls_back_to_kakao() -> None:
    places = [
        _p("x", 0, 0, "google", cats=["point_of_interest"]),
        _p("x", 0, 0, "kakao", cats=["CE7", "음식점 > 카페"]),
    ]
    assert classify_category(places) == "cafe"
