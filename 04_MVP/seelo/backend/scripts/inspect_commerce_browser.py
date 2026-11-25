"""전용 브라우저 프로필의 화면 구조를 읽는다. 비밀번호·쿠키·비공개 API는 출력하지 않는다."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.integrations.browser.commerce import BrowserProduct  # noqa: E402
from seelo.integrations.browser.session import BrowserSession  # noqa: E402


async def main(args):
    client = BrowserProduct(args.platform, args.external_id, 1)
    async with BrowserSession(args.platform, profile_path=client.profile) as page:
        await page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        await page.locator("body").wait_for()
        try:
            await page.locator("a").filter(has_text="상품").first.wait_for(timeout=20000)
        except Exception:
            await page.wait_for_load_state("domcontentloaded")
        if args.search:
            await page.get_by_role("button", name="검색", exact=True).click()
            try:
                await page.get_by_text(args.wait_text, exact=True).first.wait_for(timeout=10000)
            except Exception:
                pass  # 번호 열이 없거나 채널 번호를 표시하면 현재 화면을 보고 판단한다.
            await page.screenshot(path=args.screenshot)
        if args.open_channel:
            row = page.locator('[role="row"]').filter(has=page.get_by_text(args.open_channel, exact=True))
            await row.get_by_text("수정", exact=True).click()
            try:
                await page.wait_for_url(lambda url: "origin-list" not in url, timeout=10000)
            except Exception:
                pass
            await page.screenshot(path=args.screenshot)
            print("화면 URL: " + page.url, file=sys.stderr)
        if args.expand_purchase:
            await page.get_by_text("구매/리뷰 혜택 조건", exact=False).first.click()
        result = {"url": page.url, "title": await page.title()}
        result["links"] = await page.locator("a").evaluate_all(
            "els => els.filter(e => /상품|스토어/.test(e.textContent)).map(e => "
            "({text: e.textContent.trim().slice(0,60), href: e.getAttribute('href')})).slice(0,40)"
        )
        result["inputs"] = await page.locator("input:not([type=password]),textarea,select").evaluate_all(
            "els => els.map(e => ({tag:e.tagName,id:e.id,name:e.name,type:e.type,placeholder:e.placeholder,"
            "visible:!!e.getClientRects().length,model:e.getAttribute('ng-model')})).slice(0,220)"
        )
        result["identity_nodes"] = {
            "product": await page.get_by_text("상품번호", exact=True).evaluate_all(
                "els => els.map(e => e.parentElement.outerHTML.slice(0,1200))"
            ),
            "shop": await page.get_by_text("seelo", exact=True).evaluate_all(
                "els => els.map(e => e.parentElement.outerHTML.slice(0,1200))"
            ),
            "sections": [
                line
                for line in (await page.locator("body").inner_text()).splitlines()
                if any(word in line for word in ["최소", "최대", "구매/", "판매상태", "판매 상태"])
            ][:30],
        }
        result["editor_details"] = {
            "store_links": await page.locator('a[href*="smartstore.naver.com"]').evaluate_all(
                "els => els.map(e => ({text:e.textContent.trim(),href:e.getAttribute('href')}))"
            ),
            "controls": await page.locator("a,button").evaluate_all(
                "els => els.filter(e => e.getClientRects().length && "
                "/구매|혜택|상세설명|HTML|저장하기/.test(e.textContent))"
                ".map(e => e.outerHTML.slice(0,700)).slice(0,30)"
            ),
            "identity": await page.get_by_text("상품번호", exact=False).all_text_contents(),
        }
        result["buttons"] = await page.locator("button").evaluate_all(
            "els => els.filter(e => e.getClientRects().length)"
            ".map(e => ({text:e.textContent.trim().slice(0,80),"
            "id:e.id,action:e.getAttribute('ng-click')})).slice(0,90)"
        )
        result["product_links"] = await page.locator("a[href]").evaluate_all(
            "els => els.filter(e => /products\\//.test(e.getAttribute('href'))).map(e => "
            "({text:e.textContent.trim().slice(0,80),href:e.getAttribute('href')})).slice(0,80)"
        )
        result["rows"] = (await page.locator('[role="row"], tbody tr').all_text_contents())[:30]
        result["row_links"] = await page.locator('[role="row"] a, [role="row"] button').evaluate_all(
            "els => els.map(e => ({text:e.textContent.trim().slice(0,80),href:e.getAttribute('href'),"
            "action:e.getAttribute('ng-click'),row:e.closest('[role=row]').outerHTML.slice(0,160)})).slice(0,40)"
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["cafe24", "smartstore"], required=True)
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--expand-purchase", action="store_true")
    parser.add_argument("--open-channel", default="")
    parser.add_argument("--wait-text", default="")
    parser.add_argument("--screenshot", default="browser-inspect.png")
    asyncio.run(
        main(parser.parse_args()),
        loop_factory=asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.new_event_loop,
    )
