"""브라우저 세션(09 8.2) 골격. 화면 조작 구현은 13단계.

- 관리자가 `scripts/browser_login.py`(13단계)로 만든 영구 프로필만 쓴다. 코드는 로그인하지 않는다.
- Playwright 기본값 그대로(스텔스·사용자 에이전트 위장·무작위 대기 없음).
- 한 지도에 브라우저 하나(작업 lock fix:{provider}).
- 실패 화면 캡처·HTML은 /data/browser/artifacts/{task}/{job_id}/에 남기고, 열 때마다 7일 넘은 폴더를 지운다.
"""

import shutil
import time
from pathlib import Path
from typing import Any

import structlog

from seelo.config import get_settings

log = structlog.get_logger()

ARTIFACTS_DIR = Path("/data/browser/artifacts")
ARTIFACT_KEEP_S = 7 * 24 * 3600


def profile_dir(provider: str) -> str:
    s = get_settings()
    return s.browser_profile_dir_google if provider == "google" else s.browser_profile_dir_kakao


def prune_artifacts(root: Path = ARTIFACTS_DIR, now: float | None = None) -> int:
    """7일 넘은 하위 폴더(작업별)를 지운다. 지운 수."""
    if not root.exists():
        return 0
    cutoff = (now or time.time()) - ARTIFACT_KEEP_S
    removed = 0
    for task_dir in root.iterdir():
        for job_dir in task_dir.iterdir() if task_dir.is_dir() else []:
            if job_dir.is_dir() and job_dir.stat().st_mtime < cutoff:
                shutil.rmtree(job_dir, ignore_errors=True)
                removed += 1
    return removed


async def save_artifacts(page: Any, task: str, root: Path = ARTIFACTS_DIR) -> Path | None:
    """실패한 화면의 캡처와 HTML을 {root}/{task}/{UTC 시각}/에 남긴다(관리자 진단용, 7일 보관).

    남기다 실패해도 넘어간다.
    """
    out = root / task / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    try:
        out.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out / "screen.png"), full_page=True)
        (out / "page.html").write_text(await page.content(), encoding="utf-8")
    except Exception as e:  # 진단용 기록이 본래 오류를 가리지 않게
        log.warning("browser_artifacts_failed", task=task, error=type(e).__name__)
        return None
    log.info("browser_artifacts_saved", task=task, path=str(out))
    return out


class BrowserSession:
    """async with BrowserSession("google") as page: ..."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._pw: Any = None
        self._ctx: Any = None
        self.page: Any = None

    async def __aenter__(self) -> Any:
        from playwright.async_api import async_playwright  # 정비 워커에만 설치(의존성 그룹 browser)

        prune_artifacts()
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir(self.provider),
            headless=get_settings().browser_headless,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
        )
        self.page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        return self.page

    async def __aexit__(self, *exc: object) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()
