"""가짜 지도 연동(17 1장, 11 3장). 가짜 모드(FAKE_EXTERNALS=true)와 테스트가 같은 클래스를 쓴다.

- world: 그 지도의 "실제 응답 원문" 목록. 검색어와 이름이 비슷한 것만 돌려준다.
- fail_next(n, kind): 다음 n번 호출을 실패시킨다.
  kind = "5xx" | "timeout"(바로 ExternalApiError) | "hang"(응답 없음).
- calls: 호출 기록(네이버 값이 AI 요청에 들어갔는지 등을 테스트가 본다).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from seelo.domain.geo import haversine_m, parse_naver_coord
from seelo.domain.links import LinkInfo, classify
from seelo.domain.normalize import name_similarity
from seelo.errors import AppError
from seelo.integrations import Place, google_places, kakao_local, naver_local
from seelo.integrations.http import ExternalApiError

MATCH_SIMILARITY = 60
NONE_WORD = "없음"  # 가짜 모드: 검색어에 이 말이 있으면 0건(17 1장)
CANDIDATE_WORD = "후보"  # 가짜 모드: 검색어에 이 말이 있으면 같은 이름 결과를 하나 더(후보 흐름)


def _matches(query: str, name: str) -> bool:
    return NONE_WORD not in query and name_similarity(query, name) >= MATCH_SIMILARITY


@dataclass
class _FakeBase:
    provider: str = ""
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    extras: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # 검색어 단어 → 더 붙일 결과

    def fail_next(self, n: int = 1, kind: str = "5xx") -> None:
        self.failures.extend([kind] * n)

    async def _maybe_fail(self) -> None:
        if not self.failures:
            return
        kind = self.failures.pop(0)
        if kind == "hang":
            await asyncio.sleep(3600)  # 부르는 쪽 제한 시간이 끊는다
        raise ExternalApiError(self.provider, kind, 503 if kind == "5xx" else None)

    def _with_extras(self, query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for word, more in self.extras.items():
            if word in query:
                hits = hits + more
        return hits


@dataclass
class FakePlaces(_FakeBase):
    world: list[dict[str, Any]] = field(default_factory=list)
    english: dict[str, dict[str, Any]] = field(default_factory=dict)  # place id → 영문 응답
    provider: str = "google"

    async def search_text(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        radius_m: float = 200.0,
        page_size: int = 5,
    ) -> list[Place]:
        self.calls.append(("search_text", {"query": query, "lat": lat, "lng": lng, "radius_m": radius_m}))
        await self._maybe_fail()
        hits = [r for r in self.world if _matches(query, r["displayName"]["text"])]
        places = [google_places.to_place(r) for r in self._with_extras(query, hits)]
        if lat is not None and lng is not None:  # locationBias처럼 가까운 것을 앞으로
            places.sort(key=lambda p: haversine_m(lat, lng, p.lat, p.lng) if p.lat is not None else 1e9)
        return places[:page_size]

    async def details(self, place_id: str, *, fields: str, language: str = "ko") -> dict[str, Any] | None:
        """world의 원문 중 fields에 든 키만 돌려준다(필드 마스크처럼). 영문은 english[place_id]."""
        self.calls.append(("details", {"place_id": place_id, "fields": fields, "language": language}))
        await self._maybe_fail()
        pool = self.world + [r for more in self.extras.values() for r in more]
        raw = next((r for r in pool if r.get("id") == place_id), None)
        if raw is None:
            return None
        if language == "en":
            raw = self.english.get(place_id, raw)
        wanted = set(fields.split(","))
        return {k: v for k, v in raw.items() if k in wanted}


@dataclass
class FakeKakao(_FakeBase):
    world: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "kakao"

    async def keyword(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
        sort: str = "accuracy",
        page: int = 1,
        size: int = 15,
    ) -> tuple[list[Place], bool]:
        self.calls.append(
            ("keyword", {"query": query, "x": x, "y": y, "radius": radius, "sort": sort, "page": page})
        )
        await self._maybe_fail()
        docs = self._with_extras(query, [d for d in self.world if _matches(query, d["place_name"])])
        places = [kakao_local.to_place(d) for d in docs]
        if x is not None and y is not None:
            dist = {id(p): haversine_m(y, x, p.lat, p.lng) for p in places if p.lat is not None}
            if radius is not None:
                places = [p for p in places if dist.get(id(p), 1e9) <= radius]
            if sort == "distance":
                places.sort(key=lambda p: dist.get(id(p), 1e9))
        start = (page - 1) * size
        return places[start : start + size], start + size >= len(places)


@dataclass
class FakeNaver(_FakeBase):
    world: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "naver"

    async def search(self, query: str, *, display: int = 5) -> list[Place]:
        self.calls.append(("search", {"query": query, "display": display}))
        await self._maybe_fail()
        items = [i for i in self.world if _matches(query, naver_local.clean_title(i["title"]))]
        return [naver_local.to_place(i) for i in self._with_extras(query, items)][:display]


@dataclass
class FakeShortLinks:
    """짧은 링크 → 긴 링크를 표로 돌려준다(실제 요청 없음). 표에 없으면 호스트별 기본값."""

    mapping: dict[str, str] = field(default_factory=dict)
    by_host: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    async def resolve(self, link: LinkInfo) -> LinkInfo:
        self.calls.append(link.url)
        target = self.mapping.get(link.url)
        if target is None:
            host = link.url.split("://", 1)[-1].split("/", 1)[0].lower()
            target = self.by_host.get(host)
        info = classify(target) if target else None
        if info is None or info.kind != "long":
            raise AppError("LINK_UNRESOLVED")
        return info


# --- 가짜 모드 데모 세계(17 1장): "데모식당", 서울 중구 명동 ------------------------------

DEMO_LAT, DEMO_LNG = 37.5636, 126.9850
LAT_PER_M = 1 / 111_195
LNG_PER_M = 1 / 88_240  # 위도 37.56도 근처

DEMO_GOOGLE: dict[str, Any] = {
    "id": "ChIJdemo0000000000000001",
    "displayName": {"text": "데모식당", "languageCode": "ko"},
    "formattedAddress": "대한민국 서울특별시 중구 명동10길 29",
    "location": {"latitude": DEMO_LAT, "longitude": DEMO_LNG},
    "types": ["korean_restaurant", "restaurant", "food", "point_of_interest", "establishment"],
    "primaryType": "korean_restaurant",
    "googleMapsUri": "https://maps.google.com/?cid=1000000000000000001",
    "nationalPhoneNumber": "02-776-0000",
    # 아래는 수집(5단계)용 상세 필드. 가게 찾기는 위 필드만 쓴다
    "primaryTypeDisplayName": {"text": "한식당", "languageCode": "ko"},
    "addressComponents": [
        {
            "longText": "명동2가",
            "shortText": "명동2가",
            "types": ["sublocality_level_2", "sublocality", "political"],
        },
        {
            "longText": "중구",
            "shortText": "중구",
            "types": ["sublocality_level_1", "sublocality", "political"],
        },
        {
            "longText": "서울특별시",
            "shortText": "서울특별시",
            "types": ["administrative_area_level_1", "political"],
        },
    ],
    "websiteUri": "https://demo-restaurant.example/",
    "regularOpeningHours": {
        "periods": [
            {"open": {"day": d, "hour": 11, "minute": 0}, "close": {"day": d, "hour": 21, "minute": 0}}
            for d in range(7)
        ],
        "weekdayDescriptions": [
            f"{d}요일: 오전 11:00~오후 9:00" for d in ("월", "화", "수", "목", "금", "토", "일")
        ],
    },
    "priceLevel": "PRICE_LEVEL_MODERATE",
    "rating": 4.4,
    "userRatingCount": 1200,
    "takeout": True,
    "dineIn": True,
    "reservable": False,
    "paymentOptions": {"acceptsCreditCards": True},
    "editorialSummary": {"text": "칼국수와 만두로 알려진 오래된 식당", "languageCode": "ko"},
    "photos": [{"name": "places/x/photos/1"}, {"name": "places/x/photos/2"}],
}
DEMO_GOOGLE_EN: dict[str, Any] = {
    "displayName": {"text": "Demo Restaurant", "languageCode": "en"},
    "addressComponents": [
        {
            "longText": "Myeong-dong 2(i)-ga",
            "shortText": "Myeong-dong 2(i)-ga",
            "types": ["sublocality_level_2"],
        },
        {"longText": "Jung District", "shortText": "Jung District", "types": ["sublocality_level_1"]},
    ],
}
DEMO_GOOGLE_TWIN: dict[str, Any] = {
    **DEMO_GOOGLE,
    "id": "ChIJdemo0000000000000002",
    "formattedAddress": "대한민국 서울특별시 중구 명동8길 12",
    "location": {"latitude": DEMO_LAT + 60 * LAT_PER_M, "longitude": DEMO_LNG},
    "googleMapsUri": "https://maps.google.com/?cid=1000000000000000002",
}
DEMO_KAKAO: dict[str, Any] = {
    "id": "1",
    "place_name": "데모식당",
    "category_name": "음식점 > 한식",
    "category_group_code": "FD6",
    "category_group_name": "음식점",
    "phone": "02-776-0000",
    "address_name": "서울 중구 명동2가 1-1",
    "road_address_name": "서울 중구 명동10길 29",
    "x": str(DEMO_LNG),
    "y": str(round(DEMO_LAT + 40 * LAT_PER_M, 7)),
    "place_url": "http://place.map.kakao.com/1",
}
DEMO_KAKAO_TWIN: dict[str, Any] = {
    **DEMO_KAKAO,
    "id": "2",
    "road_address_name": "서울 중구 명동8길 12",
    "y": str(round(DEMO_LAT + 60 * LAT_PER_M, 7)),
    "place_url": "http://place.map.kakao.com/2",
}
DEMO_NAVER: dict[str, Any] = {
    "title": "<b>데모식당</b>",
    "link": "https://demo-restaurant.example/",
    "category": "음식점>한식",
    "description": "",
    "telephone": "",
    "address": "서울특별시 중구 명동2가 1-1",
    "roadAddress": "서울특별시 중구 명동10길 29",
    "mapx": str(round((DEMO_LNG + 40 * LNG_PER_M) * 1e7)),
    "mapy": str(round(DEMO_LAT * 1e7)),
}
DEMO_NAVER_TWIN: dict[str, Any] = {
    **DEMO_NAVER,
    "roadAddress": "서울특별시 중구 명동8길 12",
    "mapy": str(round((DEMO_LAT + 60 * LAT_PER_M) * 1e7)),
}
# 주변 가게 사실 조회(08 6.6)용 데모 이웃. 가짜 AI 답변의 주변 가게 이름과 같다(나머지 3곳은 지도에서 못 찾음)
DEMO_NEIGHBORS: list[dict[str, Any]] = [
    {
        "id": "ChIJdemoNeighbor0000000001",
        "displayName": {"text": "명동칼국수", "languageCode": "ko"},
        "formattedAddress": "대한민국 서울특별시 중구 명동길 1",
        "location": {"latitude": DEMO_LAT + 120 * LAT_PER_M, "longitude": DEMO_LNG},
        "types": ["korean_restaurant", "restaurant", "food"],
        "primaryType": "korean_restaurant",
        "nationalPhoneNumber": "02-776-1111",
        "websiteUri": "https://neighbor-1.example/",
        "regularOpeningHours": {"periods": [], "weekdayDescriptions": ["매일 10:00~21:00"]},
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
        "servesVegetarianFood": True,
        "paymentOptions": {"acceptsCreditCards": True},
    },
    {
        "id": "ChIJdemoNeighbor0000000002",
        "displayName": {"text": "을지면옥", "languageCode": "ko"},
        "formattedAddress": "대한민국 서울특별시 중구 충무로 2",
        "location": {"latitude": DEMO_LAT - 300 * LAT_PER_M, "longitude": DEMO_LNG},
        "types": ["korean_restaurant", "restaurant", "food"],
        "primaryType": "korean_restaurant",
        "nationalPhoneNumber": "02-776-2222",
        "regularOpeningHours": {"periods": [], "weekdayDescriptions": ["매일 11:00~20:00"]},
        "paymentOptions": {"acceptsCreditCards": True},
    },
]
DEMO_GOOGLE_LONG = (
    "https://www.google.com/maps/place/%EB%8D%B0%EB%AA%A8%EC%8B%9D%EB%8B%B9/"
    f"@{DEMO_LAT},{DEMO_LNG},17z/data=!4m6!3m5!1s0x0:0x1!8m2!3d{DEMO_LAT}!4d{DEMO_LNG}"
)


def demo_maps() -> dict[str, Any]:
    """가짜 모드 기본 지도 묶음(Clients 필드 이름 → 가짜)."""
    return {
        "places": FakePlaces(
            world=[DEMO_GOOGLE, *DEMO_NEIGHBORS],
            english={DEMO_GOOGLE["id"]: DEMO_GOOGLE_EN},
            extras={CANDIDATE_WORD: [DEMO_GOOGLE_TWIN]},
        ),
        "kakao": FakeKakao(world=[DEMO_KAKAO], extras={CANDIDATE_WORD: [DEMO_KAKAO_TWIN]}),
        "naver": FakeNaver(world=[DEMO_NAVER], extras={CANDIDATE_WORD: [DEMO_NAVER_TWIN]}),
        "short_links": FakeShortLinks(
            by_host={
                "kko.to": "https://place.map.kakao.com/1",
                "naver.me": "https://map.naver.com/p/entry/place/1",
                "maps.app.goo.gl": DEMO_GOOGLE_LONG,
            }
        ),
    }


def naver_coords(item: dict[str, Any]) -> tuple[float, float]:
    """테스트 도우미: 네이버 항목의 (위도, 경도)."""
    return parse_naver_coord(item["mapy"]), parse_naver_coord(item["mapx"])
