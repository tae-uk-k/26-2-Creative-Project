"""가짜 외부 연동(17 1장). 메일은 가짜 모드에서도 실제 SMTP(개발은 Mailpit)로 보낸다.

지도(Places·카카오·네이버·짧은 링크)는 fake_maps.py, 웹사이트·LLM 구조화는 fake_web.py의 데모 세계.
인스타그램 Business Discovery도 fake_web.py. 관리 화면은 fake_admin.py.
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

from seelo.config import get_settings
from seelo.integrations import Clients, OAuthProfile
from seelo.integrations.fake_admin import fake_map_admins
from seelo.integrations.fake_maps import demo_maps
from seelo.integrations.fake_web import FakeInstagram, FakeLlm, demo_web_server, fake_website
from seelo.integrations.mailer import SmtpMailer

# 가짜 모드 기본 사용자: 구글은 인증된 이메일, 카카오는 이메일 없음(S04 흐름을 시험)
DEMO_OAUTH = {
    "google": OAuthProfile("google", "demo-google-1", "google-demo@seelo.test", True),
    "kakao": OAuthProfile("kakao", "demo-kakao-1", None, False),
}


@dataclass
class FakeOAuth:
    """동의 화면 없이 바로 콜백으로 돌아오는 가짜 로그인. profiles[code]가 있으면 그 사용자를 준다."""

    profiles: dict[str, OAuthProfile] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def authorize_url(self, provider: str, *, redirect_uri: str, state: str) -> str:
        return f"{redirect_uri}?{urlencode({'code': f'demo-{provider}', 'state': state})}"

    async def fetch_profile(self, provider: str, *, code: str, redirect_uri: str) -> OAuthProfile:
        self.calls.append((provider, code))
        if code in self.profiles:
            return self.profiles[code]
        if code == f"demo-{provider}":
            return DEMO_OAUTH[provider]
        raise ValueError("fake oauth: 모르는 code")


def build_fake_clients() -> Clients:
    return Clients(
        **demo_maps(),
        website=fake_website(demo_web_server()),
        openai=FakeLlm(provider="openai"),
        gemini=FakeLlm(provider="gemini"),
        instagram=FakeInstagram(),
        mailer=SmtpMailer(),
        oauth=FakeOAuth(),
        map_admin=fake_map_admins(get_settings().fake_map_behavior),
    )
