"""W-03-3 공식 웹사이트(07 6.3, 11 4장). 진짜 HttpWebsiteFetcher 규칙을 가짜 서버에 대고 시험한다."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations import website as website_mod
from seelo.models.store import SourceSnapshot, StoreSource
from seelo.services import collect_service
from tests.map_world import G_EN, g_detail, k, north, seed_store

pytestmark = pytest.mark.usefixtures("queue_app")

SITE = "https://kyoja.example"
HOME = f"""<html lang="ko"><body><h1>명동교자</h1><p>매일 10:30~21:00</p>
<a href="{SITE}/menu">메뉴</a><a href="/en/">English</a>
<a href="https://www.instagram.com/kyoja_official/">인스타그램</a></body></html>"""


def _world(maps: Any, website: str | None = f"{SITE}/") -> None:
    extra = {"websiteUri": website} if website else {}
    maps.places.world = [g_detail("G1", "명동교자", **extra)]
    maps.places.english = {"G1": G_EN}
    maps.kakao.world = [k("K1", "명동교자", north(30))]


def _site_calls(web: Any) -> list[dict[str, Any]]:
    """웹사이트 정리 LLM 호출만(같은 가짜 LLM에 AI 웹 검색 호출도 섞인다)."""
    return [c for c in web.llm.calls if c.get("schema") == "WebsiteExtractOut"]


async def _collect(db: AsyncSession) -> tuple[SourceSnapshot, dict[str, StoreSource]]:
    store_id, run_id = await seed_store(db, naver=False)
    await collect_service.collect_store(store_id, run_id)
    db.expire_all()
    snap = await db.scalar(select(SourceSnapshot).where(SourceSnapshot.provider == "website"))
    sources = {s.provider: s for s in await db.scalars(select(StoreSource))}
    return snap, sources


async def test_website_ok_with_menu_english_extract_and_instagram(
    db: AsyncSession, maps: Any, web: Any
) -> None:
    _world(maps)
    web.server.robots(SITE, "User-agent: *\nAllow: /")
    web.server.html(f"{SITE}/", HOME)
    web.server.html(f"{SITE}/menu", "<html><body><li>칼국수 11,000원</li></body></html>")
    snap, sources = await _collect(db)

    assert snap.status == "ok"
    p = snap.payload
    assert (p["url"], p["menuUrl"], p["hasEnglishPage"]) == (f"{SITE}/", f"{SITE}/menu", True)
    ext = p["extract"]
    assert ext["phone"] == "02-776-0000" and ext["menu"][0] == {
        "name": "칼국수",
        "price": 11000,
        "description": None,
    }
    assert ext["hours"]["days"]["mon"] == [{"open": "11:00", "close": "21:00"}]  # WeeklyHours로 바꿔 저장
    assert ext["hours"]["breaks"]["mon"] == [{"start": "15:00", "end": "17:00"}]
    assert "html" not in str(p).lower()  # 원문 HTML은 저장하지 않는다
    # LLM에는 두 페이지 텍스트만(주소·HTML 없음)
    prompt = _site_calls(web)[0]["prompt"]
    assert "[페이지 1]" in prompt and "[페이지 2]" in prompt and "칼국수 11,000원" in prompt
    assert "<a" not in prompt and SITE not in prompt
    assert (sources["website"].match_status, sources["website"].url) == ("found", f"{SITE}/")
    assert (sources["instagram"].match_status, sources["instagram"].external_id) == (
        "found",
        "kyoja_official",
    )


async def test_robots_disallow_means_zero_body_requests(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps)
    web.server.robots(SITE, "User-agent: SeeloBot\nDisallow: /\n\nUser-agent: *\nAllow: /")
    web.server.html(f"{SITE}/", HOME)
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code, snap.payload) == ("robots_disallowed", "disallowed", None)
    assert web.server.body_requests() == []
    assert _site_calls(web) == []  # 웹사이트 정리 LLM은 부르지 않음(AI 웹 검색은 따로)


@pytest.mark.parametrize(("status", "allowed"), [(404, True), (403, True), (500, False), (503, False)])
async def test_robots_4xx_allows_5xx_disallows(
    db: AsyncSession, maps: Any, web: Any, status: int, allowed: bool
) -> None:
    _world(maps)
    web.server.robots(SITE, "", status=status)
    web.server.html(f"{SITE}/", HOME)
    snap, _ = await _collect(db)
    if allowed:
        assert snap.status == "ok" and web.server.body_requests()
    else:
        assert (snap.status, snap.error_code) == ("robots_disallowed", "robots_5xx")
        assert web.server.body_requests() == []


async def test_robots_timeout_disallows(
    db: AsyncSession, maps: Any, web: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(website_mod, "ROBOTS_TIMEOUT_S", 0.2)
    _world(maps)
    web.server.robots(SITE, "")
    web.server.delays[f"{SITE}/robots.txt"] = 1
    web.server.html(f"{SITE}/", HOME)
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("robots_disallowed", "robots_error")
    assert web.server.body_requests() == []


async def test_page_over_1mb_fails(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps)
    web.server.robots(SITE, "")
    web.server.html(f"{SITE}/", "<p>" + "가" * 400_000 + "</p>")  # UTF-8 3바이트 × 40만 = 1.2MB
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("failed", "too_large")
    assert _site_calls(web) == []  # 웹사이트 정리 LLM은 부르지 않음(AI 웹 검색은 따로)


async def test_page_over_10s_fails(
    db: AsyncSession, maps: Any, web: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(website_mod, "PAGE_TIMEOUT_S", 0.3)  # 운영 10초를 줄여 시험
    _world(maps)
    web.server.robots(SITE, "")
    web.server.html(f"{SITE}/", HOME)
    web.server.delays[f"{SITE}/"] = 2
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("failed", "timeout")


async def test_not_html_fails(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps)
    web.server.robots(SITE, "")
    web.server.pages[f"{SITE}/"] = (200, {"content-type": "application/pdf"}, b"%PDF")
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("failed", "not_html")


async def test_redirect_target_is_robots_checked(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps)
    web.server.robots(SITE, "")
    web.server.redirect(f"{SITE}/", "https://other-host.example/home")
    web.server.robots("https://other-host.example", "User-agent: *\nDisallow: /home")
    web.server.html("https://other-host.example/home", HOME)
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("robots_disallowed", "robots_disallowed")
    assert "https://other-host.example/home" not in web.server.body_requests()


async def test_instagram_website_goes_to_instagram_source(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps, website="https://www.instagram.com/kyoja_official/")
    snap, sources = await _collect(db)
    assert (snap.status, snap.error_code) == ("skipped", "instagram")
    assert sources["website"].match_status == "not_found"
    assert (sources["instagram"].match_status, sources["instagram"].external_id) == (
        "found",
        "kyoja_official",
    )
    assert web.server.seen == []


async def test_no_website_is_skipped(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps, website=None)
    snap, sources = await _collect(db)
    assert (snap.status, snap.error_code) == ("skipped", "no_url")
    assert sources["website"].match_status == "not_found" and sources["instagram"].match_status == "not_found"


async def test_internal_address_is_never_requested(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps, website="http://localhost:8000/admin")
    snap, _ = await _collect(db)
    assert (snap.status, snap.error_code) == ("failed", "blocked_host")
    assert web.server.seen == []


async def test_llm_failure_keeps_page_info(db: AsyncSession, maps: Any, web: Any) -> None:
    _world(maps)
    web.server.robots(SITE, "")
    web.server.html(f"{SITE}/", HOME)
    web.llm.fail_next(1, "refused", only="WebsiteExtractOut")
    snap, _ = await _collect(db)
    assert snap.status == "ok"
    assert snap.payload["extract"] is None and snap.payload["extractError"] == "refused"
    assert snap.payload["hasEnglishPage"] is True
