"""자동화 차단 감지(09 8.3). 로그인·보안 확인·캡차·예상하지 못한 화면이면 즉시 멈춘다(우회하지 않음).

- AutomationBlocked: 다시 시도하지 않는다 → 그 칸 manual_required.
  연결 확인이면 연결 상태를 바꾸지 않고 관리자 메일.
- TransientAutomationError: 페이지 이동의 네트워크 시간 초과·연결 오류만. 1번 다시.
- StoreNotVisible: 가게가 안 보임 → 연결 확인이면 needs_attention(store_not_visible).
  연결 뒤라면 권한 회수(E18).
- AttentionNeeded: 연결 확인에서 고칠 문제를 찾음(인증 필요·대표 권한 없음 등) → needs_attention + 사유.
- FieldWriteFailed: 그 칸만 쓸 수 없음(셀렉터를 아직 정하지 못한 칸, API가 받지 않는 값)
  → 그 칸 manual_required(write_failed). 다른 칸은 계속한다.
"""

from typing import Any
from urllib.parse import urlparse

LOGIN_HOSTS = {"google": {"accounts.google.com"}, "kakao": {"accounts.kakao.com", "logins.daum.net"}}  # [PoC]
CAPTCHA_SELECTOR = 'iframe[src*="recaptcha"], iframe[title*="reCAPTCHA"], iframe[src*="captcha"]'
BLOCK_TEXTS = [
    "보안 확인",
    "본인 확인",
    "verify it's you",
    "unusual traffic",
    "로봇이 아닙니다",
    "자동 입력 방지",
]
READY_TIMEOUT_MS = 10_000


class AutomationBlocked(Exception):
    # login_required|captcha|security_check|unexpected_screen|selectors_missing|api_error
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TransientAutomationError(Exception): ...


class StoreNotVisible(Exception): ...


class AttentionNeeded(Exception):
    def __init__(self, reason: str) -> None:  # map_connections.attention_reason 값
        self.reason = reason
        super().__init__(reason)


class FieldWriteFailed(Exception):
    def __init__(self, reason: str) -> None:  # unsupported_field|hours_incomplete|rejected
        self.reason = reason
        super().__init__(reason)


async def _blocked_reason(page: Any, provider: str) -> str | None:
    """로그인 화면·캡차·보안 확인이면 그 사유."""
    if (urlparse(page.url).hostname or "") in LOGIN_HOSTS[provider]:
        return "login_required"
    try:
        if await page.locator(CAPTCHA_SELECTOR).count() > 0:
            return "captcha"
        body = (await page.locator("body").inner_text(timeout=3000)).lower()
    except Exception:  # 화면이 바뀌는 중이면 본문을 못 읽을 수 있다: 다음 확인에 맡긴다
        return None
    return "security_check" if any(t.lower() in body for t in BLOCK_TEXTS) else None


async def guard(page: Any, provider: str, ready_selector: str, *, not_found: str | None = None) -> None:
    """모든 이동·클릭·저장 뒤에 부른다. 막히면 AutomationBlocked.

    not_found(가게 없음 표시)가 ready보다 먼저 보이면 StoreNotVisible. 준비 요소가 끝내 안 보이면
    한 번 더 살핀다(불러온 뒤 스크립트로 로그인 화면에 가는 경우) → 그 사유, 아니면 unexpected_screen.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # 정비 워커에만 설치

    reason = await _blocked_reason(page, provider)
    if reason:
        raise AutomationBlocked(reason)
    target = page.locator(ready_selector)
    if not_found:
        target = target.or_(page.locator(not_found))
    try:
        await target.first.wait_for(timeout=READY_TIMEOUT_MS)
    except PlaywrightTimeoutError as e:
        raise AutomationBlocked(await _blocked_reason(page, provider) or "unexpected_screen") from e
    if not_found and await page.locator(not_found).count() > 0:
        raise StoreNotVisible()
