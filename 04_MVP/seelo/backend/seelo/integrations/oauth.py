"""구글·카카오 로그인 어댑터(05 5장).

- state는 서비스(oauth_service)가 만들어 seelo_oauth 세션 쿠키에 두고 콜백에서 직접 비교한다.
  그래서 여기서는 인가 주소 만들기와 code → 사용자 정보만 한다.
- 구글 주소: https://accounts.google.com/.well-known/openid-configuration (2026-10-27 확인).
  id_token 서명 검증 대신 userinfo 주소를 액세스 토큰으로 부른다(TLS로 구글에서 직접 받음).
- 카카오 주소·필드: 카카오 로그인 REST API 문서(2026-10-23 확인, 05 5.1).
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client

from seelo.config import get_settings
from seelo.integrations import OAuthProfile


@dataclass(frozen=True)
class Endpoints:
    authorize: str
    token: str
    userinfo: str
    scope: str


GOOGLE = Endpoints(
    authorize="https://accounts.google.com/o/oauth2/v2/auth",
    token="https://oauth2.googleapis.com/token",
    userinfo="https://openidconnect.googleapis.com/v1/userinfo",
    scope="openid email profile",
)
KAKAO = Endpoints(
    authorize="https://kauth.kakao.com/oauth/authorize",
    token="https://kauth.kakao.com/oauth/token",
    userinfo="https://kapi.kakao.com/v2/user/me",
    scope="account_email",
)
ENDPOINTS = {"google": GOOGLE, "kakao": KAKAO}


def parse_google(data: dict[str, Any]) -> OAuthProfile:
    verified = data.get("email_verified")
    return OAuthProfile(
        provider="google",
        provider_user_id=str(data["sub"]),
        email=data.get("email") or None,
        email_verified=verified is True or verified == "true",
    )


def parse_kakao(data: dict[str, Any]) -> OAuthProfile:
    """has_email은 폐지 예정이라 보지 않는다. email이 있고 유효·인증일 때만 인증된 이메일."""
    acc = data.get("kakao_account") or {}
    email = acc.get("email") or None
    verified = (
        email is not None and acc.get("is_email_valid") is True and acc.get("is_email_verified") is True
    )
    return OAuthProfile(
        provider="kakao", provider_user_id=str(data["id"]), email=email, email_verified=verified
    )


PARSERS = {"google": parse_google, "kakao": parse_kakao}


class AuthlibOAuth:
    def _credentials(self, provider: str) -> tuple[str, str]:
        s = get_settings()
        if provider == "google":
            cid, secret = s.google_oauth_client_id, s.google_oauth_client_secret.get_secret_value()
        else:
            cid, secret = s.kakao_oauth_client_id, s.kakao_oauth_client_secret.get_secret_value()
        if not cid or not secret:
            raise RuntimeError(f"{provider} OAuth 클라이언트가 설정되지 않았다(16 4장)")
        return cid, secret

    def authorize_url(self, provider: str, *, redirect_uri: str, state: str) -> str:
        ep = ENDPOINTS[provider]
        cid, _ = self._credentials(provider)
        params = {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "scope": ep.scope,
            "state": state,
        }
        return f"{ep.authorize}?{urlencode(params)}"

    async def fetch_profile(self, provider: str, *, code: str, redirect_uri: str) -> OAuthProfile:
        ep = ENDPOINTS[provider]
        cid, secret = self._credentials(provider)
        # client_secret_post: client_id·client_secret을 본문에 넣는다(카카오는 필수, 구글도 지원)
        async with AsyncOAuth2Client(
            client_id=cid,
            client_secret=secret,
            redirect_uri=redirect_uri,
            token_endpoint_auth_method="client_secret_post",
            timeout=10.0,
        ) as client:
            await client.fetch_token(ep.token, code=code, grant_type="authorization_code")
            resp = await client.get(ep.userinfo)
            resp.raise_for_status()
            data = resp.json()
        return PARSERS[provider](data)
