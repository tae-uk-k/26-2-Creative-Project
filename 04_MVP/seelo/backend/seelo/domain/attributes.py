"""조건 키(08 0.1). Google 필드 값은 참·거짓·없음 세 가지다. "정보 없음"은 필드가 없을 때만. IO 없음."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Tri = bool | None  # 참·거짓·없음


def _field(*path: str) -> Callable[[dict[str, Any]], Tri]:
    def get(g: dict[str, Any]) -> Tri:
        cur: Any = g
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return None
            cur = cur[p]
        return bool(cur)

    return get


def _budget(g: dict[str, Any]) -> Tri:
    if "priceLevel" not in g:
        return None
    return g["priceLevel"] in ("PRICE_LEVEL_INEXPENSIVE", "PRICE_LEVEL_MODERATE")


def _alcohol(g: dict[str, Any]) -> Tri:
    vals = [g[k] for k in ("servesBeer", "servesWine", "servesCocktails") if k in g]
    return any(vals) if vals else None


def _none(_: dict[str, Any]) -> Tri:
    return None


@dataclass(frozen=True)
class Attribute:
    key: str
    google: Callable[[dict[str, Any]], Tri]
    en: str
    label: str


ATTRIBUTES: dict[str, Attribute] = {
    a.key: a
    for a in [
        Attribute("vegetarian", _field("servesVegetarianFood"), "vegetarian-friendly", "채식 가능"),
        Attribute("budget", _budget, "affordable", "합리적인 가격"),
        Attribute(
            "card_payment",
            _field("paymentOptions", "acceptsCreditCards"),
            "that accepts credit cards",
            "카드 결제",
        ),
        Attribute("reservation", _field("reservable"), "that takes reservations", "예약 가능"),
        Attribute("takeout", _field("takeout"), "with takeout", "포장 가능"),
        Attribute("delivery", _field("delivery"), "with delivery", "배달 가능"),
        Attribute("kid_friendly", _field("goodForChildren"), "kid-friendly", "아이 동반"),
        Attribute("group_friendly", _field("goodForGroups"), "good for groups", "단체 가능"),
        Attribute("outdoor_seating", _field("outdoorSeating"), "with outdoor seating", "야외 좌석"),
        Attribute("alcohol", _alcohol, "that serves drinks", "주류"),
        Attribute(
            "wheelchair",
            _field("accessibilityOptions", "wheelchairAccessibleEntrance"),
            "wheelchair-accessible",
            "휠체어 출입",
        ),
        Attribute("pet_friendly", _field("allowsDogs"), "pet-friendly", "반려동물 동반"),
        Attribute("halal", _none, "halal", "할랄"),
        Attribute("english_menu", _none, "with an English menu", "영어 메뉴"),
    ]
}


def google_value(key: str, g: dict[str, Any]) -> Tri:
    return ATTRIBUTES[key].google(g)


def true_labels(g: dict[str, Any], *, exclude: frozenset[str] = frozenset({"budget"})) -> list[str]:
    """Google 스냅샷에서 참인 편의 정보 라벨(모은 정보 표 amenities).

    budget(가격)은 가격대 행에 따로 보이므로 기본으로 뺀다.
    """
    return [a.label for a in ATTRIBUTES.values() if a.key not in exclude and a.google(g) is True]


# 카카오 제공 서비스·태그 키워드(08 0.1 표 마지막 열) [PoC: 파트너센터 선택지로 확정].
# 없는 키는 카카오에 칸이 없음
KAKAO_KEYWORD: dict[str, str] = {
    "vegetarian": "채식",
    "card_payment": "카드결제",
    "reservation": "예약",
    "takeout": "포장",
    "delivery": "배달",
    "kid_friendly": "유아",
    "group_friendly": "단체",
    "outdoor_seating": "테라스",
    "alcohol": "주류",
    "wheelchair": "휠체어",
    "pet_friendly": "반려동물",
    "halal": "할랄",  # 민감 정보
}
