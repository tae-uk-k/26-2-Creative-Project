"""관리자가 seelo 공용 계정으로 직접 로그인할 브라우저를 연다(09 8.5). 코드는 비밀번호를 입력하지 않는다.

사용(정비 워커 이미지 또는 Playwright가 설치된 곳): python scripts/browser_login.py --provider google|kakao
- 자동 정비가 쓰는 영구 프로필(BROWSER_PROFILE_DIR_GOOGLE·_KAKAO)로 **화면이 보이는** 브라우저를 열고
  로그인 화면으로 간다. 관리자가 2단계 인증까지 직접 마친 뒤 터미널에서 Enter를 누른다.
- 가게 목록 화면에서 로그인 표시 요소(selectors/{provider}.yaml의 login.logged_in)를 확인하고 닫는다.
  로그인이 풀려 작업이 AutomationBlocked("login_required")로 멈추면 이 도구로 다시 로그인한다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.integrations.browser.screen import load_screen_config  # noqa: E402
from seelo.integrations.browser.session import profile_dir  # noqa: E402


async def main(provider: str) -> int:
    from playwright.async_api import async_playwright

    cfg = load_screen_config(provider)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir(provider),
            headless=False,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(cfg.login_url or "about:blank")
        await asyncio.to_thread(input, "브라우저에서 로그인(2단계 인증 포함)을 마친 뒤 Enter를 누르세요: ")
        ok = True
        if cfg.logged_in and cfg.store_list_url:
            await page.goto(cfg.store_list_url)
            try:
                await page.locator(cfg.logged_in).first.wait_for(timeout=15_000)
                print("로그인 확인됨")
            except Exception:
                print("로그인 표시를 찾지 못했어요. 다시 로그인하거나 selectors 파일을 확인하세요.")
                ok = False
        else:
            print("selectors 파일의 login.logged_in·가게 목록 주소가 비어 있어 확인을 건너뜀([PoC])")
        await ctx.close()
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["google", "kakao"], required=True)
    raise SystemExit(asyncio.run(main(ap.parse_args().provider)))
