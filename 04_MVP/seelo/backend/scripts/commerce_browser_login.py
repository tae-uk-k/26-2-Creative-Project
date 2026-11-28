"""seelo 담당자가 위임받은 계정으로 로그인한다. 고객 비밀번호를 입력하는 코드는 없다."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.config import get_settings  # noqa: E402
from seelo.integrations.browser.commerce import BrowserProduct  # noqa: E402
from seelo.integrations.browser.session import BrowserSession  # noqa: E402


async def main(platform: str, external_id: str, shop_no: int) -> None:
    client = BrowserProduct(platform, external_id, shop_no)
    get_settings().browser_headless = False
    url = (
        f"https://{external_id}.cafe24.com/admin/"
        if platform == "cafe24"
        else (
            "https://accounts.commerce.naver.com/certify?url=https%3A%2F%2Fsell.smartstore.naver.com"
            "%2F%23%2Flogin-callback%3FreturnUrl%3Dhttps%253A%252F%252Fsell.smartstore.naver.com"
            "%252F%2523%252Fhome%252Fdashboard"
        )
    )
    async with BrowserSession(platform, profile_path=client.profile) as page:
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.to_thread(input, "위임받은 seelo 계정으로 로그인·보안 확인을 마친 뒤 Enter: ")
        print("로그인 창을 닫습니다. 상품 편집 권한은 별도 원본 수집 때 확인합니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["smartstore", "cafe24"], required=True)
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--shop-no", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(
        main(args.platform, args.external_id, args.shop_no),
        loop_factory=asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.new_event_loop,
    )
