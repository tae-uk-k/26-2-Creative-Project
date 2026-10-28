"""관리 화면 HTML 저장 도구(17 3.1, PoC). 셀렉터(selectors/{provider}.yaml)를 정할 때 쓴다.

사용: python scripts/capture_admin_html.py --provider google|kakao --name info
- 자동 정비가 쓰는 영구 프로필로 **화면이 보이는** 브라우저를 연다. 관리자가 원하는 화면까지 직접 이동한 뒤
  터미널에서 Enter를 누르면 page.content()를 tests/fixtures/browser/{provider}/{name}.html로 저장한다.
- 저장 전에 이메일·전화번호·사업자등록번호를 ***로 가린다. 가게 이름·주소는 테스트에 필요해 남긴다
  (저장소를 공개하지 않는다).
- 꼭 저장할 화면: 가게 목록, 정보 화면, 칸별 편집 화면(열린 상태), 저장 직후 화면, 로그인 화면,
  보안 확인(나오면), "인증 필요" 표시가 있는 가게(있으면).
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seelo.integrations.browser.screen import load_screen_config  # noqa: E402
from seelo.integrations.browser.session import profile_dir  # noqa: E402

MASKS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # 이메일
    re.compile(r"0\d{1,2}-?\d{3,4}-?\d{4}"),  # 전화번호
    re.compile(r"\d{3}-\d{2}-\d{5}"),  # 사업자등록번호
]


def mask(html: str) -> str:
    for r in MASKS:
        html = r.sub("***", html)
    return html


async def main(provider: str, name: str) -> None:
    from playwright.async_api import async_playwright

    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise SystemExit("--name은 영문 소문자·숫자·밑줄만")
    cfg = load_screen_config(provider)
    out = ROOT / "tests" / "fixtures" / "browser" / provider / f"{name}.html"
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir(provider),
            headless=False,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(cfg.store_list_url or "about:blank")
        await asyncio.to_thread(input, f"저장할 화면({name})으로 이동한 뒤 Enter를 누르세요: ")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mask(await page.content()), encoding="utf-8")
        print(f"저장: {out.relative_to(ROOT)} ({page.url})")
        await ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["google", "kakao"], required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    asyncio.run(main(a.provider, a.name))
