"""실제 외부 연동 묶음. 어댑터는 단계마다 채운다(07~10)."""

from seelo.config import get_settings
from seelo.integrations import Clients
from seelo.integrations.gemini_client import GeminiClient
from seelo.integrations.google_places import GooglePlaces
from seelo.integrations.http import HttpShortLinkResolver
from seelo.integrations.instagram import GraphInstagram
from seelo.integrations.kakao_local import KakaoLocal
from seelo.integrations.local_cli import LocalCliClient
from seelo.integrations.mailer import SmtpMailer
from seelo.integrations.map_admins import real_map_admin
from seelo.integrations.naver_local import NaverLocal
from seelo.integrations.oauth import AuthlibOAuth
from seelo.integrations.openai_client import OpenAiClient
from seelo.integrations.website import HttpWebsiteFetcher


def build_real_clients() -> Clients:
    local = get_settings().ai_backend == "local_cli"
    return Clients(
        places=GooglePlaces(),
        short_links=HttpShortLinkResolver(),
        kakao=KakaoLocal(),
        naver=NaverLocal(),
        website=HttpWebsiteFetcher(),
        openai=LocalCliClient("openai") if local else OpenAiClient(),
        gemini=LocalCliClient("gemini") if local else GeminiClient(),
        instagram=GraphInstagram(),
        mailer=SmtpMailer(),
        oauth=AuthlibOAuth(),
        map_admin=real_map_admin,
    )
