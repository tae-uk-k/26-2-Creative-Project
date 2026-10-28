"""로컬 HTML 관리 화면(테스트용, 11 3장). 진짜 Google·카카오 화면이 아니다.

PoC로 실제 화면 HTML을 저장하기 전에 화면 조작 엔진(ScreenAdmin)·차단 감지를 시험하려고 만든 단순한 화면이다.
Playwright route로 모든 요청을 받아 메모리 상태로 그린다(네트워크·포트 없음). 저장(POST)하면 값이 바뀐다.
"""

import asyncio
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlsplit

from seelo.integrations.browser.screen import ScreenConfig, parse_screen_config

BASE = "https://admin.test"
LOGIN = {"google": "https://accounts.google.com/signin", "kakao": "https://accounts.kakao.com/login"}
TEXT_FIELDS = {"google": ("description", "website", "phone"), "kakao": ("intro",)}
_SHOW = "document.getElementById('{f}-form').hidden=false"  # [수정]을 누르면 입력 칸이 열린다
ATTENTION = {
    "google": ("verification_required", "인증 필요"),
    "kakao": ("no_owner_authority", "수정 권한 없음"),
}


def screen_config(provider: str) -> ScreenConfig:
    """이 테스트 화면에 맞춘 셀렉터(실제 selectors/{provider}.yaml과 같은 형식)."""
    reason, text = ATTENTION[provider]
    return parse_screen_config(
        provider,
        {
            "login": {"url": LOGIN[provider], "logged_in": "css=#account"},
            "pages": {
                "store_list": {"url": f"{BASE}/stores", "ready": "css=#store-list"},
                "info": {
                    "url_template": BASE + "/store/{external_ref}",
                    "ready": "css=#info-ready",
                    "not_found": "css=#not-found",
                },
            },
            "store_search": {
                "row": "css=.store-row",
                "name": "css=.store-name",
                "link": "css=a.open",
                "external_ref": r"/store/(\w+)",
            },
            "attention": {reason: f"text={text}"},
            "fields": {
                f: {
                    "read": f"css=#{f}-value",
                    "open_editor": f"css=#edit-{f}",
                    "input": f"css=#{f}-form textarea",
                    "save": f"css=#save-{f}",
                    "saved_ready": "css=#saved",
                    "review_badge": f"css=#{f}-review",
                }
                for f in TEXT_FIELDS[provider]
            },
        },
    )


@dataclass
class AdminSite:
    provider: str
    stores: dict[str, str] = field(default_factory=lambda: {"77": "데모식당", "88": "다른식당"})
    values: dict[str, Any] = field(default_factory=dict)
    review_after_save: set[str] = field(default_factory=set)  # 저장하면 "검토 중"이 붙는 칸
    reviewing: set[str] = field(default_factory=set)
    mode: str = "normal"  # normal|login|security|captcha|attention|broken
    saves: list[tuple[str, str]] = field(default_factory=list)

    async def attach(self, context: Any) -> None:
        await context.route("**/*", self._handle)

    async def _handle(self, route: Any, request: Any) -> None:
        u = urlsplit(request.url)
        if u.hostname in ("accounts.google.com", "accounts.kakao.com"):
            return await route.fulfill(
                content_type="text/html", body=_page("로그인", "<form>비밀번호</form>")
            )
        if u.hostname != "admin.test":
            return await route.fulfill(content_type="text/html", body="")  # 캡차 iframe 등
        if self.mode == "login":  # 로그인이 풀림: 불러온 뒤 로그인 화면으로 넘어간다
            refresh = f'<meta http-equiv="refresh" content="0;url={LOGIN[self.provider]}">'
            return await route.fulfill(content_type="text/html", body=_page("이동", refresh))
        if u.path == "/stores":
            return await route.fulfill(content_type="text/html", body=self._list())
        parts = u.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "store":
            sid = parts[1]
            saved = False
            if request.method == "POST" and len(parts) == 3 and parts[2] == "save":
                key = parse_qs(u.query)["field"][0]
                value = parse_qs(request.post_data or "")["value"][0]
                self.values[key] = value
                self.saves.append((key, value))
                if key in self.review_after_save:
                    self.reviewing.add(key)
                saved = True
            return await route.fulfill(content_type="text/html", body=self._info(sid, saved))
        await route.fulfill(status=404, content_type="text/html", body=_page("없음", ""))

    def _list(self) -> str:
        rows = "".join(
            f'<li class="store-row"><span class="store-name">{escape(n)}</span>'
            f'<span class="addr">서울 중구</span><a class="open" href="/store/{sid}">열기</a></li>'
            for sid, n in self.stores.items()
        )
        return _page("가게 목록", f'<ul id="store-list">{rows}</ul>')

    def _info(self, sid: str, saved: bool) -> str:
        if sid not in self.stores:
            return _page("정보", '<div id="not-found">가게를 찾을 수 없어요</div>')
        if self.mode == "security":
            return _page("확인", "<p>보안 확인이 필요해요. 본인 확인을 진행해 주세요.</p>")
        if self.mode == "captcha":
            return _page("확인", '<iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>')
        if self.mode == "broken":
            return _page("새 화면", "<p>화면 구성이 바뀌었어요</p>")
        body = '<div id="info-ready">정보</div>' + ('<div id="saved">저장됨</div>' if saved else "")
        if self.mode == "attention":
            body += f'<div class="warn">{ATTENTION[self.provider][1]}</div>'
        for f in TEXT_FIELDS[self.provider]:
            badge = f'<span id="{f}-review">검토 중</span>' if f in self.reviewing else ""
            body += (
                f'<section><p id="{f}-value">{escape(str(self.values.get(f) or ""))}</p>{badge}'
                f'<button id="edit-{f}" onclick="{_SHOW.format(f=f)}">수정</button>'
                f'<form id="{f}-form" hidden method="post" action="/store/{sid}/save?field={f}">'
                f'<textarea name="value"></textarea><button id="save-{f}" type="submit">저장</button></form>'
                "</section>"
            )
        return _page(escape(self.stores[sid]), body)


def _page(title: str, body: str) -> str:
    head = f'<meta charset="utf-8"><title>{title}</title>'
    return f'<!doctype html><html lang="ko"><head>{head}</head><body>{body}</body></html>'


class BrowserThread:
    """Playwright를 따로 스레드의 이벤트 루프에서 돌린다.

    Windows의 테스트 루프(psycopg 때문에 SelectorEventLoop)는 브라우저 프로세스를 띄우지 못한다.
    """

    def __init__(self) -> None:
        self.loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()

    async def call(self, coro: Any) -> Any:
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, self.loop))

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=10)
        self.loop.close()


class LoopAdmin:
    """다른 루프의 MapAdmin을 이 루프에서 부르게 하는 대리자(applyFix 같은 서비스가 그대로 쓴다)."""

    def __init__(self, bt: BrowserThread, inner: Any) -> None:
        self.bt, self.inner, self.provider = bt, inner, inner.provider

    async def open_store(self, store: Any, external_ref: str | None) -> str:
        return await self.bt.call(self.inner.open_store(store, external_ref))  # type: ignore[no-any-return]

    async def read_fields(self, fields: list[str]) -> Any:
        return await self.bt.call(self.inner.read_fields(fields))

    async def write_field(self, field_: str, value: object) -> None:
        await self.bt.call(self.inner.write_field(field_, value))

    async def same_page(self, config: ScreenConfig) -> "LoopAdmin":
        """같은 페이지에 다른 셀렉터를 쓰는 화면 엔진(실제 selectors 파일 시험용)."""

        async def make() -> Any:
            return type(self.inner)(self.inner.page, config)

        return LoopAdmin(self.bt, await self.bt.call(make()))


@asynccontextmanager
async def open_admin(site: AdminSite) -> AsyncIterator[LoopAdmin]:
    """이 화면에 붙은 브라우저(새 컨텍스트) 위의 GoogleAdminBrowser·KakaoPartnerBrowser.

    Playwright·Chromium이 없으면 테스트를 건너뛴다(정비 워커 이미지나 `uv sync --group browser` 뒤에 돈다).
    """
    import pytest

    pw_api = pytest.importorskip("playwright.async_api")
    from seelo.integrations.browser.google_admin import GoogleAdminBrowser
    from seelo.integrations.browser.kakao_partner import KakaoPartnerBrowser

    holder: dict[str, Any] = {}

    async def start() -> Any:
        holder["pw"] = await pw_api.async_playwright().start()
        try:
            holder["browser"] = await holder["pw"].chromium.launch()
        except pw_api.Error as e:
            await holder["pw"].stop()
            return e
        ctx = await holder["browser"].new_context(locale="ko-KR")
        await site.attach(ctx)
        page = await ctx.new_page()
        cls = GoogleAdminBrowser if site.provider == "google" else KakaoPartnerBrowser
        return cls(page, screen_config(site.provider))

    async def close() -> None:
        await holder["browser"].close()
        await holder["pw"].stop()

    bt = BrowserThread()
    try:
        admin = await bt.call(start())
        if isinstance(admin, Exception):
            pytest.skip(f"Chromium 없음: {admin}")
        try:
            yield LoopAdmin(bt, admin)
        finally:
            await bt.call(close())
    finally:
        bt.stop()
