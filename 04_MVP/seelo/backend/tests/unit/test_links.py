"""W-02-2 링크 판별·짧은 링크 따라가기(07 2장, 11 4장).

links.csv는 지금 문서 예시 링크다. 테스트 가게 20곳 × 3사 × 긴·짧은 링크는 PoC 때 채운다(07 2.2).
"""

import asyncio
import csv
from pathlib import Path

import httpx
import pytest

from seelo.domain.links import LinkInfo, classify, extract_urls, pick_supported
from seelo.errors import AppError
from seelo.integrations import http as http_mod
from seelo.integrations.http import HttpShortLinkResolver

ROWS = list(
    csv.DictReader((Path(__file__).parents[1] / "fixtures" / "links" / "links.csv").open(encoding="utf-8"))
)


@pytest.mark.parametrize("row", ROWS, ids=[f"{r['provider']}-{r['kind']}-{i}" for i, r in enumerate(ROWS)])
def test_links_csv(row: dict[str, str]) -> None:
    info = classify(row["url"])
    assert info is not None
    assert (info.provider, info.kind) == (row["provider"], row["kind"])
    assert info.external_id == (row["expected_external_id"] or None)
    if row["expected_name"]:
        assert info.name == row["expected_name"]
    # 공유 문구 통째로 넣어도 같다
    assert pick_supported(f"[{row['provider']}] 가게 이름\n{row['url']} 에서 보기") == info


def test_doc_examples() -> None:
    assert pick_supported("[네이버 지도]\n명동교자 본점\nhttps://naver.me/5abcDEF") == LinkInfo(
        "naver", "short", "https://naver.me/5abcDEF"
    )
    g = classify(ROWS[12]["url"])
    assert (g.lat, g.lng) == (37.5627, 126.9858)  # !3d!4d(가게 위치)가 @(지도 중심)보다 먼저
    center = classify("https://www.google.com/maps/place/X/@37.5,126.9,17z")
    assert (center.lat, center.lng) == (37.5, 126.9)
    assert pick_supported(
        "https://www.google.com/maps/search/?api=1&query=x&query_place_id=ChIJ123"
    ).place_id == ("ChIJ123")
    assert pick_supported("maps.app.goo.gl/AbCd123 여기") == LinkInfo(
        "google", "short", "https://maps.app.goo.gl/AbCd123"
    )


def test_extract_urls_trailing_punctuation_and_order() -> None:
    text = "먼저 (https://www.instagram.com/x), 그다음 「https://place.map.kakao.com/1」. naver.me/abc!"
    assert extract_urls(text) == [
        "https://www.instagram.com/x",
        "https://place.map.kakao.com/1",
        "https://naver.me/abc",
    ]
    # 지원 안 하는 링크가 앞에 있어도 처음 지원하는 것을 쓴다
    assert pick_supported(text).external_id == "1"


REJECTS = [
    "https://www.instagram.com/myeongdongkyoja",
    "https://www.google.com/search?q=명동교자",
    "https://www.google.com/maps",  # 가게를 가리키지 않음
    "https://map.kakao.com/",  # 장소 번호 없음
    "https://map.naver.com/p/search/명동교자",  # 장소 번호 없음
    "https://m.place.naver.com/restaurant/home",
    "https://www.tripadvisor.co.kr/Restaurant_Review-g294197",
    "https://goo.gl/abcdef",  # /maps가 아닌 goo.gl
    "https://www.naver.com/",
    "https://place.map.kakao.com.evil.example/1",
]


@pytest.mark.parametrize("url", REJECTS)
def test_rejects(url: str) -> None:
    assert classify(url) is None
    with pytest.raises(AppError) as e:
        pick_supported(url)
    assert e.value.code == "UNSUPPORTED_LINK"


@pytest.mark.parametrize("text", ["가게 이름만", "ftp://place.map.kakao.com/1", "place.map.kakao.com/1"])
def test_no_link(text: str) -> None:
    with pytest.raises(AppError) as e:
        pick_supported(text)
    assert e.value.code == "NO_LINK"


# --- 짧은 링크: 가짜 서버가 리디렉션 체인을 기록 ---------------------------------------------


class ChainServer:
    """url → (상태, Location). 받은 요청(메서드, url)을 모두 기록한다."""

    def __init__(
        self, routes: dict[str, tuple[int, str | None]], *, head_status: int | None = None, delay: float = 0
    ):
        self.routes, self.head_status, self.delay = routes, head_status, delay
        self.seen: list[tuple[str, str]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.method, str(request.url)))
        if self.delay:
            await asyncio.sleep(self.delay)
        if request.method == "HEAD" and self.head_status:
            return httpx.Response(self.head_status)
        status, loc = self.routes.get(str(request.url), (404, None))
        return httpx.Response(status, headers={"Location": loc} if loc else {})


async def _resolve(server: ChainServer, url: str) -> LinkInfo:
    resolver = HttpShortLinkResolver(transport=httpx.MockTransport(server))
    return await resolver.resolve(LinkInfo("naver", "short", url))


async def test_short_link_followed_hop_by_hop() -> None:
    server = ChainServer(
        {
            "https://naver.me/abc": (302, "https://naver.me/abc2"),
            "https://naver.me/abc2": (301, "/p/entry"),  # 상대 주소
            "https://naver.me/p/entry": (302, "https://map.naver.com/p/entry/place/11679241"),
        }
    )
    info = await _resolve(server, "https://naver.me/abc")
    assert info == LinkInfo(
        "naver", "long", "https://map.naver.com/p/entry/place/11679241", external_id="11679241"
    )
    # 자동으로 따라가지 않았다: 긴 링크 주소로는 요청하지 않았다
    assert [u for _, u in server.seen] == [
        "https://naver.me/abc",
        "https://naver.me/abc2",
        "https://naver.me/p/entry",
    ]
    assert all(m == "HEAD" for m, _ in server.seen)


async def test_fourth_hop_is_unresolved() -> None:
    routes = {f"https://kko.to/{i}": (302, f"https://kko.to/{i + 1}") for i in range(3)}
    routes["https://kko.to/3"] = (302, "https://place.map.kakao.com/1")  # 4번째 이동이어야 닿음
    with pytest.raises(AppError) as e:
        await _resolve(ChainServer(routes), "https://kko.to/0")
    assert e.value.code == "LINK_UNRESOLVED"


async def test_slow_server_is_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_mod, "SHORT_LINK_TIMEOUT_S", 0.2)  # 운영 5초를 줄여 시험
    server = ChainServer({"https://naver.me/slow": (302, "https://map.naver.com/p/entry/place/1")}, delay=1.0)
    with pytest.raises(AppError) as e:
        await _resolve(server, "https://naver.me/slow")
    assert e.value.code == "LINK_UNRESOLVED"


async def test_head_not_allowed_falls_back_to_get_stream() -> None:
    server = ChainServer(
        {"https://naver.me/g": (302, "https://map.naver.com/p/entry/place/9")}, head_status=405
    )
    info = await _resolve(server, "https://naver.me/g")
    assert info.external_id == "9"
    assert [m for m, _ in server.seen] == ["HEAD", "GET"]


@pytest.mark.parametrize(
    "location",
    ["http://169.254.169.254/latest/meta-data", "http://localhost:8000/api/health", "https://evil.example/x"],
)
async def test_does_not_follow_to_unrelated_hosts(location: str) -> None:
    server = ChainServer({"https://naver.me/x": (302, location)})
    with pytest.raises(AppError):
        await _resolve(server, "https://naver.me/x")
    assert [u for _, u in server.seen] == ["https://naver.me/x"]  # 그 주소로 요청하지 않았다


async def test_non_redirect_is_unresolved() -> None:
    with pytest.raises(AppError) as e:
        await _resolve(ChainServer({"https://naver.me/ok": (200, None)}), "https://naver.me/ok")
    assert e.value.code == "LINK_UNRESOLVED"
