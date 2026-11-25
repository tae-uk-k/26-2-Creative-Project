"""실제 플랫폼이 아닌 HTML 화면에서 브라우저 상품 수정과 차단 조건을 검증한다."""

import copy
from contextlib import asynccontextmanager
from html import escape
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from seelo.config import get_settings
from seelo.domain.commerce import fingerprint
from seelo.errors import AppError
from seelo.integrations.browser import commerce
from seelo.integrations.commerce import CommerceApiError
from seelo.services import commerce_service as service
from seelo.services.commerce_service import product_client
from tests.browser_site import BrowserThread


def config(platform="cafe24"):
    return {
        "edit_url": (
            "https://{external_id}.cafe24.com/admin/product/{product_no}"
            if platform == "cafe24"
            else "https://sell.smartstore.naver.com/product/{product_no}"
        ),
        "ready": "#editor",
        "product_id": {"selector": "#product-no"},
        "shop_identity": {"selector": "#shop"},
        "name": {"selector": "#name"},
        "save": "#save",
        "saved_ready": "#saved",
        "fields": {"description": {"selector": "#description"}},
        "protected": {"price": {"selector": "#price"}},
    }


async def test_unconfigured_browser_never_opens(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("미확인 설정에서는 브라우저를 열면 안 됩니다.")

    monkeypatch.setattr(commerce, "BrowserSession", forbidden)
    client = commerce.BrowserProduct("cafe24", "demo", 1, config={})
    with pytest.raises(CommerceApiError, match="selectors_missing"):
        await client.fetch("123")


@pytest.mark.parametrize(
    "url", ["https://attacker.example/{product_no}", "http://demo.cafe24.com/{product_no}"]
)
def test_admin_domain_is_fixed(url):
    cfg = config()
    cfg["edit_url"] = url
    with pytest.raises(CommerceApiError, match="invalid_admin_url"):
        commerce.BrowserProduct("cafe24", "demo", 1, config=cfg).edit_url("123")


@pytest.mark.parametrize(
    ("source", "platform", "field", "actual", "expected", "matches"),
    [
        ("browser", "cafe24", "description", "\n<p>A</p>\n\n<p>B</p>\n", "<p>A</p>\n<p>B</p>", True),
        ("api", "cafe24", "description", "\n<p>A</p>", "<p>A</p>", False),
        ("browser", "smartstore", "description", "\n<p>A</p>", "<p>A</p>", False),
        ("browser", "cafe24", "seo.meta_title", "\nA", "A", False),
        ("browser", "cafe24", "description", "<p>A</p>\n\n<p>C</p>", "<p>A</p>\n<p>B</p>", False),
        ("browser", "cafe24", "description", "<pre>A\n\nB</pre>", "<pre>A\nB</pre>", False),
    ],
)
def test_cafe24_only_ignores_observed_editor_newlines(source, platform, field, actual, expected, matches):
    shop = SimpleNamespace(platform=platform)
    product = SimpleNamespace(snapshot_source=source)
    assert service.field_matches(shop, product, field, actual, expected) is matches


async def test_delegation_is_required_without_api_credentials(monkeypatch):
    monkeypatch.setattr(get_settings(), "commerce_edit_mode", "browser")
    shop = SimpleNamespace(
        platform="cafe24", external_id="demo", shop_no=1, manager_status="invited", delegation={}
    )
    with pytest.raises(AppError):
        await product_client(None, shop)
    shop.manager_status = "verified"
    assert isinstance(await product_client(None, shop), commerce.BrowserProduct)


@pytest.mark.parametrize("uncertain", [False, True])
@pytest.mark.parametrize("padding", [False, True])
async def test_browser_apply_reconcile_and_rollback_without_token(monkeypatch, uncertain, padding):
    monkeypatch.setattr(get_settings(), "commerce_writes_enabled", True)
    shop = SimpleNamespace(
        id=1,
        owner_id=1,
        platform="cafe24",
        external_id="demo",
        shop_no=1,
        manager_status="verified",
        api_status="not_connected",
        credentials=None,
        delegation={},
    )
    raw = {"fields": {"description": "원본"}, "protected": {"price": "10000"}}
    product = SimpleNamespace(id=2, external_id="123", snapshot_source="browser")
    plan = SimpleNamespace(
        id=3,
        status="approved",
        snapshot_hash=fingerprint(raw),
        changes=[{"field": "description", "before": "원본", "proposed": "정비", "method": "browser"}],
        approval={"fields": ["description"]},
    )
    writes = []
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(), scalar=AsyncMock(return_value=None))
    db.add = writes.append
    monkeypatch.setattr(service, "owned_plan", AsyncMock(return_value=(shop, product, plan)))
    monkeypatch.setattr(service, "event", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "plan_view", lambda value: {"status": value.status})
    calls = []

    async def fetch(number):
        return copy.deepcopy(raw)

    async def write(number, fresh, changes):
        assert db.commit.await_count > 0 and writes[-1].status == "started"
        calls.append(changes)
        raw["fields"].update(changes)
        if padding:
            raw["fields"]["description"] = "\n\n" + raw["fields"]["description"] + "\n"
        if uncertain and len(calls) == 1:
            raise CommerceApiError("browser_write_failed", uncertain=True)

    adapter = SimpleNamespace(fetch=fetch, write=write, fields=lambda value: value["fields"])
    monkeypatch.setattr(commerce, "BrowserProduct", lambda *args, **kwargs: adapter)
    user = SimpleNamespace(id=1)
    result = await service.apply(db, user, plan.id)
    assert result["status"] == ("uncertain" if uncertain else "applied")
    if uncertain:
        db.scalar.return_value = writes[-1]
        assert (await service.verify(db, user, plan.id))["status"] == "applied"
        assert len(calls) == 1
    assert shop.api_status == "not_connected" and shop.credentials is None
    db.scalar.return_value = None
    assert (await service.apply(db, user, plan.id, rollback=True))["status"] == "rolled_back"
    assert raw["fields"]["description"].strip() == "원본" and len(calls) == 2


@pytest.mark.parametrize("platform", ["cafe24", "smartstore"])
async def test_rendered_form_write_readback_restore_and_guards(monkeypatch, platform):
    pytest.importorskip("playwright.async_api")
    thread = BrowserThread()

    async def exercise():
        from playwright.async_api import async_playwright

        state = {"description": "<p>원본</p>", "price": "24900", "id": "123", "mode": "normal"}
        writes = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context()

            async def route(request):
                if request.request.url.endswith("/save"):
                    state["description"] = request.request.post_data or ""
                    writes.append(state["description"])
                    await request.fulfill(body="ok")
                    return
                if state["mode"] == "security":
                    await request.fulfill(content_type="text/html", body='<meta charset="utf-8">보안 확인')
                    return
                body = (
                    '<meta charset="utf-8">'
                    f'<main id="editor"><input id="shop" value="demo">'
                    f'<input id="product-no" value="{state["id"]}">'
                    '<input id="name" value="단백질 분말">'
                    f'<input id="price" value="{state["price"]}">'
                    f'<textarea id="description">{escape(state["description"])}</textarea>'
                    '<button id="save" onclick="save()">저장</button></main>'
                    '<script>async function save(){await fetch("/save",{method:"POST",'
                    'body:document.querySelector("#description").value});'
                    'document.body.insertAdjacentHTML("beforeend",\'<p id="saved">저장됨</p>\');}</script>'
                )
                await request.fulfill(content_type="text/html", body=body)

            await ctx.route("**/*", route)

            @asynccontextmanager
            async def session(*args, **kwargs):
                page = await ctx.new_page()
                try:
                    yield page
                finally:
                    await page.close()

            monkeypatch.setattr(commerce, "BrowserSession", session)
            client = commerce.BrowserProduct(platform, "demo", 1, config=config(platform))
            before = await client.fetch("123")
            await client.write("123", before, {"description": "<p>원료와 보관 방법</p>"})
            after = await client.fetch("123")
            assert after["fields"]["description"] == "<p>원료와 보관 방법</p>"
            assert after["protected"] == before["protected"]
            await client.write("123", after, {"description": before["fields"]["description"]})
            assert (await client.fetch("123"))["fields"] == before["fields"]
            count = len(writes)
            state["price"] = "25900"
            with pytest.raises(CommerceApiError, match="browser_source_changed"):
                await client.write("123", before, {"description": "잘못된 덮어쓰기"})
            state["id"] = "456"
            with pytest.raises(CommerceApiError, match="product_identity_mismatch"):
                await client.fetch("123")
            state["mode"] = "security"
            with pytest.raises(CommerceApiError, match="security_check"):
                await client.fetch("123")
            assert len(writes) == count == 2
            await browser.close()

    try:
        await thread.call(exercise())
    finally:
        thread.stop()


async def test_commerce_profile_reuses_encrypted_session_cookie(tmp_path):
    from seelo.integrations.browser.session import BrowserSession

    pytest.importorskip("playwright.async_api")
    thread = BrowserThread()
    profile = str(tmp_path / "commerce-profile")

    async def exercise():
        async with BrowserSession("cafe24", profile_path=profile) as page:
            await page.context.add_cookies(
                [
                    {
                        "name": "seelo_test_session",
                        "value": "test-session-marker",
                        "domain": "demo.cafe24.com",
                        "path": "/",
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ]
            )
        encrypted = (tmp_path / "commerce-profile" / ".seelo-session.enc").read_bytes()
        assert b"test-session-marker" not in encrypted
        async with BrowserSession("cafe24", profile_path=profile) as page:
            cookies = await page.context.cookies()
            assert any(
                c["name"] == "seelo_test_session" and c["value"] == "test-session-marker" for c in cookies
            )

    try:
        await thread.call(exercise())
    finally:
        thread.stop()


async def test_product_fetch_from_backend_loop(monkeypatch, tmp_path):
    import asyncio
    import sys

    from seelo.integrations.browser.session import BrowserSession

    pytest.importorskip("playwright.async_api")
    loops = []

    @asynccontextmanager
    async def session(*args, **kwargs):
        loops.append(asyncio.get_running_loop())
        async with BrowserSession("cafe24", profile_path=str(tmp_path / "worker")) as page:
            await page.route(
                "**/*",
                lambda route: route.fulfill(
                    content_type="text/html",
                    body='<meta charset="utf-8"><main id="editor">'
                    '<input id="shop" value="demo"><input id="product-no" value="123">'
                    '<input id="name" value="검증상품"><input id="price" value="10000">'
                    '<textarea id="description">원본</textarea><button id="save">저장</button></main>',
                ),
            )
            yield page

    monkeypatch.setattr(commerce, "BrowserSession", session)
    client = commerce.BrowserProduct("cafe24", "demo", 1, config=config())
    result = await client.fetch("123")
    assert result["fields"]["description"] == "원본"
    if sys.platform == "win32":
        assert isinstance(loops[0], asyncio.ProactorEventLoop)


async def test_code_editor_focus_then_select_all_reads_full_document():
    """첫 클릭이 포커스만 주고 입력 버퍼가 비어 있는 코드 편집기를 검증한다."""
    pytest.importorskip("playwright.async_api")
    thread = BrowserThread()

    async def exercise():
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(
                '<button id="code" aria-pressed="false" onclick="toggle()">코드보기</button>'
                '<script>let focused=false,doc="원문 전체";'
                'function toggle(){const b=document.querySelector("#code");'
                "if(!focused){focused=true;return;}"
                'if(b.getAttribute("aria-pressed")==="true") {'
                'doc=document.querySelector("textarea").value;document.querySelector("textarea").remove();'
                'b.setAttribute("aria-pressed","false");return;}'
                'b.setAttribute("aria-pressed","true");const t=document.createElement("textarea");'
                't.onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="a"){t.value=doc;}};'
                "document.body.append(t);}</script>"
            )
            client = commerce.BrowserProduct("cafe24", "demo", 1, config={})
            spec = {
                "selector": "textarea",
                "open": "#code",
                "opened": '#code[aria-pressed="true"]',
                "select_all": True,
            }
            assert await client._editor(page, spec) == "원문 전체"
            assert await client._editor(page, spec, "수정한 전체 본문") == "원문 전체"
            assert await client._editor(page, spec) == "수정한 전체 본문"
            assert await page.locator("#code").get_attribute("aria-pressed") == "false"
            await browser.close()

    try:
        await thread.call(exercise())
    finally:
        thread.stop()
