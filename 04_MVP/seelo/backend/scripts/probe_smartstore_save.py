"""기존 상품을 바꾸지 않고 저장 안내 화면을 확인한다. 주문·비공개 API는 사용하지 않는다."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.integrations.browser.commerce import BrowserProduct  # noqa: E402
from seelo.integrations.browser.session import BrowserSession  # noqa: E402


async def main():
    client = BrowserProduct("smartstore", "seelo", 1)
    async with BrowserSession("smartstore", profile_path=client.profile) as page:
        await page.goto("https://sell.smartstore.naver.com/#/products/edit/13821774578")
        await page.locator('textarea[ng-model="vm.editorContent"]').wait_for()
        await page.get_by_text("구매/리뷰 혜택 조건", exact=False).first.click()
        controls = {
            "stock": "#stock",
            "minimum": "#prd_min",
            "maximum": (
                'input[ng-model="vm.product.detailAttribute.purchaseQuantityInfo.'
                'maxPurchaseQuantityPerOrder"]'
            ),
        }
        values = {key: await page.locator(selector).input_value() for key, selector in controls.items()}
        if values != {"stock": "1", "minimum": "2", "maximum": "2"}:
            raise RuntimeError("구매 차단 조건이 예상과 달라 저장하지 않습니다.")
        dialogs = []
        event = asyncio.Event()

        async def dialog(d):
            dialogs.append({"type": d.type, "message": d.message})
            await d.dismiss()
            event.set()

        page.on("dialog", dialog)
        await page.locator('button[data-nclicks-code="flt.save"]').first.click()
        try:
            await asyncio.wait_for(event.wait(), timeout=8)
        except TimeoutError:
            pass
        result = {
            "url": page.url,
            "dialogs": dialogs,
            "purchase_conditions": values,
            "modals": await page.locator('.modal-dialog, [role="dialog"]').all_text_contents(),
        }
        path = Path(sys.argv[1])
        await asyncio.to_thread(
            path.write_text, json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(path=str(path.with_suffix(".png")))
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(
        main(), loop_factory=asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    )
