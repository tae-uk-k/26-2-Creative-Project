"""위임 가게 선택·식별과 외부 상품 목록. 실제 플랫폼이 아닌 로컬 HTML 화면(실제 Chromium)에서 검사한다."""

import json
from contextlib import asynccontextmanager
from html import escape
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from seelo.integrations.browser import commerce
from seelo.integrations.commerce import CommerceApiError
from tests.browser_site import BrowserThread


def config(store_switch=True, catalog=True):
    cfg = {
        "edit_url": "https://sell.smartstore.naver.com/product/{product_no}",
        "ready": "#editor",
        "product_id": {"selector": "#product-no"},
        "shop_identity": {"selector": "#shop", "expected": "{store_name}"},
        "name": {"selector": "#name"},
        "save": "#save",
        "saved_ready": "#saved",
        "fields": {"description": {"selector": "#description"}},
        "protected": {"price": {"selector": "#price"}},
    }
    if store_switch:
        cfg["store_switch"] = {
            "open": "#switch",
            "item": ".store-item",
            "attribute": "data-name",
            "expected": "{store_name}",
            "ready": "#switched",
        }
    if catalog:
        cfg["catalog"] = {
            "url": "https://sell.smartstore.naver.com/products?page=1",
            "ready": "#list",
            "row": "tr.product",
            "product_id": {"selector": "a", "attribute": "href", "regex": r"/product/([1-9][0-9]*)"},
            "name": {"selector": ".name"},
            "next": "#next:not([disabled])",
        }
    return cfg


class Site:
    """가게마다 상품 본문이 따로 있는 위임 관리 화면. 현재 선택한 가게의 화면만 보여 준다."""

    def __init__(self, stores, current):
        self.stores, self.current = stores, current
        self.bodies = {name: f"<p>{name} 원본</p>" for name in set(stores) | {current}}
        self.catalog = {name: [] for name in self.bodies}
        self.saves = []

    def switcher(self):
        items = "".join(
            f'<li class="store-item" data-name="{escape(n)}" '
            f'onclick="choose(this.dataset.name)">{escape(n)}</li>'
            for n in self.stores
        )
        return (
            '<button id="switch" '
            'onclick="document.querySelector(\'#stores\').hidden=false">가게 전환</button>'
            f'<ul id="stores" hidden>{items}</ul>'
            "<script>async function choose(n){await fetch('/choose',{method:'POST',body:n});"
            "document.body.insertAdjacentHTML('beforeend','<p id=\"switched\">전환됨</p>');}"
            "async function save(){await fetch('/save',{method:'POST',"
            "body:document.querySelector('#description').value});"
            "document.body.insertAdjacentHTML('beforeend','<p id=\"saved\">저장됨</p>');}</script>"
        )

    async def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        if url.path == "/choose":
            self.current = request.post_data or ""
            await route.fulfill(body="ok")
            return
        if url.path == "/save":
            self.bodies[self.current] = request.post_data or ""
            self.saves.append(self.current)
            await route.fulfill(body="ok")
            return
        head = f'<meta charset="utf-8"><input id="shop" value="{escape(self.current)}">' + self.switcher()
        if url.path == "/products":
            page = int(parse_qs(url.query).get("page", ["1"])[0])
            rows = self.catalog[self.current][(page - 1) * 2 : page * 2]
            body = "".join(
                f'<tr class="product"><td><a href="/product/{n}">열기</a></td>'
                f'<td class="name">{escape(t)}</td></tr>'
                for n, t in rows
            )
            more = page * 2 < len(self.catalog[self.current])
            nxt = (
                f'<a id="next" href="/products?page={page + 1}">다음</a>'
                if more
                else '<button id="next" disabled>다음</button>'
            )
            await route.fulfill(content_type="text/html", body=head + f'<table id="list">{body}</table>{nxt}')
            return
        body = (
            head + '<main id="editor"><input id="product-no" value="123"><input id="name" value="벌꿀">'
            '<input id="price" value="10000">'
            f'<textarea id="description">{escape(self.bodies[self.current])}</textarea>'
            '<button id="save" onclick="save()">저장</button></main>'
        )
        await route.fulfill(content_type="text/html", body=body)


async def run_with_site(monkeypatch, site, scenario):
    pytest.importorskip("playwright.async_api")
    thread = BrowserThread()

    async def exercise():
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context()
            await ctx.route("**/*", site.route)

            @asynccontextmanager
            async def session(*args, **kwargs):
                page = await ctx.new_page()
                try:
                    yield page
                finally:
                    await page.close()

            monkeypatch.setattr(commerce, "BrowserSession", session)
            try:
                await scenario()
            finally:
                await browser.close()

    try:
        return await thread.call(exercise())
    finally:
        thread.stop()


def client(cfg=None, store_name="seelo"):
    return commerce.BrowserProduct(
        "smartstore", "seelo", 1, config=cfg or config(), identity={"storeName": store_name}
    )


@pytest.mark.parametrize("order", [["seelo2", "seelo", "다른가게"], ["seelo", "다른가게", "seelo2"]])
async def test_switches_to_exact_store_regardless_of_order_and_similar_names(monkeypatch, order):
    site = Site(order, current="다른가게")

    async def scenario():
        result = await client().fetch("123")
        assert result["fields"]["description"] == "<p>seelo 원본</p>"
        assert site.current == "seelo"
        # 저장도 전환한 가게에만 한다. 다른 가게 본문은 그대로다.
        site.current = "다른가게"
        await client().write("123", result, {"description": "<p>정비</p>"})
        assert site.saves == ["seelo"] and site.bodies["다른가게"] == "<p>다른가게 원본</p>"

    await run_with_site(monkeypatch, site, scenario)


@pytest.mark.parametrize(
    ("stores", "reason"),
    [
        (["seelo2", "다른가게"], "shop_not_delegated"),  # 권한 회수·다른 계정
        (["seelo", "seelo"], "shop_selection_ambiguous"),
        ([], "shop_not_delegated"),
    ],
)
async def test_stops_when_store_is_missing_or_ambiguous(monkeypatch, stores, reason):
    site = Site(stores, current="다른가게")

    async def scenario():
        with pytest.raises(CommerceApiError, match=reason):
            await client().fetch("123")
        assert site.saves == []

    await run_with_site(monkeypatch, site, scenario)


async def test_without_switch_config_wrong_store_is_identity_mismatch(monkeypatch):
    site = Site(["seelo"], current="다른가게")

    async def scenario():
        with pytest.raises(CommerceApiError, match="shop_identity_mismatch"):
            await client(config(store_switch=False)).fetch("123")
        # 기록한 스토어 이름이 화면 이름과 다르면 비슷해도 같은 가게로 보지 않는다.
        site.current = "seelo"
        with pytest.raises(CommerceApiError, match="shop_identity_mismatch"):
            await client(config(store_switch=False), store_name="seelo 스토어").fetch("123")

    await run_with_site(monkeypatch, site, scenario)


async def test_catalog_reads_all_pages_of_selected_store_only(monkeypatch):
    site = Site(["seelo", "다른가게"], current="다른가게")
    site.catalog["seelo"] = [("101", "벌꿀"), ("102", "수박씨"), ("103", "사차인치")]
    site.catalog["다른가게"] = [("901", "다른 상품")]

    async def scenario():
        result = await client().catalog()
        assert [item["productNo"] for item in result["items"]] == ["101", "102", "103"]
        assert result["pages"] == 2 and result["truncated"] is False
        limited = await client().catalog(max_items=2)
        assert len(limited["items"]) == 2 and limited["truncated"] is True

    await run_with_site(monkeypatch, site, scenario)


def test_unconfigured_catalog_never_opens_browser():
    with pytest.raises(CommerceApiError, match="catalog_not_configured"):
        commerce.BrowserProduct("smartstore", "seelo", 1, config=config(catalog=False)).catalog_url()
    cfg = config()
    cfg["catalog"]["url"] = "https://attacker.example/products"
    with pytest.raises(CommerceApiError, match="invalid_admin_url"):
        commerce.BrowserProduct("smartstore", "seelo", 1, config=cfg).catalog_url()


@pytest.mark.parametrize(("registered", "matches"), [(2, True), (1, False), (3, False)])
async def test_cafe24_final_shop_number_must_match(registered, matches):
    cfg = commerce.load_config("cafe24")
    product = commerce.BrowserProduct("cafe24", "demo01", registered, config=cfg)
    page = SimpleNamespace(
        url="https://demo01.cafe24.com/disp/admin/shop2/product/ProductRegister?product_no=9"
    )
    assert await product._shop_matches(page) is matches
    # 기본 설정의 편집 주소는 자기 쇼핑몰 번호 검사를 통과한다.
    own = SimpleNamespace(url=product.edit_url("9"))
    assert await product._shop_matches(own) is True


def test_expected_identity_uses_recorded_store_name():
    product = client(config(store_switch=False), store_name="  seelo   벌꿀  ")
    assert product.expected("{store_name}") == "seelo 벌꿀"
    fallback = commerce.BrowserProduct("smartstore", "seelo", 1, config=config(store_switch=False))
    assert fallback.expected("{store_name}") == "seelo"
    assert json.dumps(fallback.expected_values, ensure_ascii=False)
