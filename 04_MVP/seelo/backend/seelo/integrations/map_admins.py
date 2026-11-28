"""실제 지도 관리 화면 묶음(Clients.map_admin, 09 8·9장). map_admin("google") → async with → MapAdmin.

- google이고 GOOGLE_FIX_MODE=api면 GoogleAdminApi(gbp_api.py).
- 그 밖에는 영구 프로필 브라우저 세션 하나를 열어 GoogleAdminBrowser·KakaoPartnerBrowser.
  셀렉터 파일이 비어 있으면(PoC 전) 브라우저를 열지 않고 AutomationBlocked("selectors_missing").
  작업이 화면 문제로 실패하면 화면 캡처·HTML을 남긴다(session.save_artifacts).
- Playwright는 정비 워커 이미지에만 있다. 브라우저를 쓸 때만 불러온다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from seelo.config import get_settings
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    StoreNotVisible,
    TransientAutomationError,
)

SCREEN_ERRORS = (AutomationBlocked, AttentionNeeded, StoreNotVisible, TransientAutomationError)


@asynccontextmanager
async def real_map_admin(provider: str) -> AsyncIterator[Any]:
    if provider == "google" and get_settings().google_fix_mode == "api":
        from seelo.integrations.gbp_api import GoogleAdminApi, api_client

        async with api_client() as http:
            yield GoogleAdminApi(http)
        return

    from seelo.integrations.browser.google_admin import GoogleAdminBrowser
    from seelo.integrations.browser.kakao_partner import KakaoPartnerBrowser
    from seelo.integrations.browser.screen import load_screen_config
    from seelo.integrations.browser.session import BrowserSession, save_artifacts

    cfg = load_screen_config(provider)
    if not cfg.usable:
        raise AutomationBlocked("selectors_missing")
    cls = GoogleAdminBrowser if provider == "google" else KakaoPartnerBrowser
    async with BrowserSession(provider) as page:
        try:
            yield cls(page, cfg)
        except SCREEN_ERRORS:
            await save_artifacts(page, provider)
            raise
