"""외부 연동 묶음(13 11장). 서비스는 get_clients()로만 바깥을 부른다."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


@dataclass
class Place:
    """지도 검색 결과 하나(07 4장). raw는 Google·웹사이트만 저장에 쓴다."""

    provider: str
    external_id: str | None
    name: str
    address: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    category_raw: list[str]
    url: str | None
    raw: dict[str, Any]


class PlacesClient(Protocol):
    async def search_text(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        radius_m: float = 200.0,
        page_size: int = 5,
    ) -> list[Place]: ...

    async def details(self, place_id: str, *, fields: str, language: str = "ko") -> dict[str, Any] | None: ...


class KakaoLocalClient(Protocol):
    async def keyword(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
        sort: str = "accuracy",
        page: int = 1,
        size: int = 15,
    ) -> tuple[list[Place], bool]: ...


class NaverLocalClient(Protocol):
    async def search(self, query: str, *, display: int = 5) -> list[Place]: ...


class ShortLinkResolver(Protocol):
    """짧은 지도 링크(LinkInfo kind short)를 긴 링크로(07 2.3). 못 따라가면 AppError(LINK_UNRESOLVED)."""

    async def resolve(self, link: Any) -> Any: ...


@dataclass
class RobotsResult:
    allowed: bool
    reason: str  # ok|disallowed|robots_5xx|robots_error


@dataclass
class FetchedPage:
    url: str
    html: str
    status: int


class WebsiteFetcher(Protocol):
    async def robots_allows(self, url: str) -> RobotsResult: ...

    async def fetch(self, url: str) -> FetchedPage: ...


@dataclass
class LlmResult:
    text: str
    sources: list[dict[str, Any]]  # [{n, url, title, domain}](08 2.3)
    raw: dict[str, Any]
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    search_calls: int
    latency_ms: int
    annotated_text: str | None = None  # 출처 번호 [n]을 넣은 원문(08 3.1)


@dataclass
class StructuredResult:
    parsed: BaseModel
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class LlmClient(Protocol):
    provider: str

    async def web_answer(self, prompt: str, *, model: str) -> LlmResult: ...

    async def structured(self, prompt: str, schema: type[BaseModel], *, model: str) -> StructuredResult: ...


class InstagramClient(Protocol):
    async def business_discovery(self, username: str) -> dict[str, Any] | None: ...


class Mailer(Protocol):
    async def send(self, *, to: list[str], subject: str, text: str, html: str) -> None: ...


@dataclass
class OAuthProfile:
    """제공자가 알려 준 사용자(05 5.3).

    email_verified: 구글은 email_verified, 카카오는 is_email_valid와 is_email_verified가 모두 참.
    """

    provider: str  # google|kakao
    provider_user_id: str
    email: str | None
    email_verified: bool


class OAuthClient(Protocol):
    def authorize_url(self, provider: str, *, redirect_uri: str, state: str) -> str: ...

    async def fetch_profile(self, provider: str, *, code: str, redirect_uri: str) -> OAuthProfile: ...


@dataclass
class Clients:
    places: PlacesClient
    short_links: ShortLinkResolver
    kakao: KakaoLocalClient
    naver: NaverLocalClient
    website: WebsiteFetcher
    openai: LlmClient
    gemini: LlmClient
    instagram: InstagramClient
    mailer: Mailer
    oauth: OAuthClient
    map_admin: Callable[[str], AbstractAsyncContextManager[Any]]  # map_admin("google") → async with


_clients: Clients | None = None


def get_clients() -> Clients:
    global _clients
    if _clients is None:
        from seelo.config import get_settings

        if get_settings().fake_externals:
            from seelo.integrations.fakes import build_fake_clients

            _clients = build_fake_clients()
        else:
            from seelo.integrations.real import build_real_clients

            _clients = build_real_clients()
    return _clients


def set_clients(clients: Clients | None) -> None:
    """테스트용: 외부 연동 묶음을 바꾸거나(None이면) 초기화한다."""
    global _clients
    _clients = clients
