"""W-03-5 인스타그램(07 6.5): 플래그가 꺼지면 Graph API 호출 0번, 켜지면 Business Discovery 스냅샷.

프로필 주소 정규식(예약 경로 제외)은 unit/test_collect_domain.py의 test_instagram_username.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.integrations import get_clients
from seelo.integrations.http import ExternalApiError
from seelo.integrations.instagram import GraphInstagram
from seelo.models.store import SourceSnapshot, Store, StoreSource
from seelo.models.user import User
from seelo.schemas.llm import EvidenceSiteOut, WebEvidenceExtractOut
from seelo.services import collect_service
from tests.map_world import G_EN, g_detail, seed_store
from tests.support import capture_all_logs

pytestmark = pytest.mark.usefixtures("queue_app")

TOKEN = "IGQ-test-token-value"


@pytest.fixture(autouse=True)
def _settings(settings_env: Any) -> None:
    settings_env(
        OPENAI_MEASURE_MODEL="m-openai", GEMINI_MEASURE_MODEL="m-gemini", OPENAI_CHEAP_MODEL="m-cheap"
    )


def _evidence_with_instagram(ai: Any, url: str) -> None:
    ai.openai.results["WebEvidenceExtractOut"] = WebEvidenceExtractOut(
        sites=[
            EvidenceSiteOut(
                url="https://www.tripadvisor.com/x", site_name="T", name="명동교자", address=None, phone=None,
                hours_text=None, menu=[], instagram_url=url,
            )
        ]
    )  # fmt: skip


async def _collect(db: AsyncSession, maps: Any, **google: Any) -> tuple[int, int]:
    maps.places.world = [g_detail("G1", "명동교자", **google)]
    maps.places.english = {"G1": G_EN}
    store_id, run_id = await seed_store(db, naver=False)
    await collect_service.collect_store(store_id, run_id)
    db.expire_all()
    return store_id, run_id


async def _instagram(db: AsyncSession) -> tuple[StoreSource, SourceSnapshot | None]:
    src = await db.scalar(select(StoreSource).where(StoreSource.provider == "instagram"))
    snap = await db.scalar(select(SourceSnapshot).where(SourceSnapshot.provider == "instagram"))
    return src, snap


async def test_flag_off_means_zero_graph_calls(db: AsyncSession, maps: Any, ai: Any) -> None:
    _evidence_with_instagram(ai, "https://www.instagram.com/demo_restaurant/")
    await _collect(db, maps)
    src, snap = await _instagram(db)
    assert (src.match_status, src.external_id) == ("found", "demo_restaurant")  # web_evidence의 instagramUrl
    assert snap is None
    assert get_clients().instagram.calls == []


async def test_flag_on_saves_profile_and_shows_bio(
    db: AsyncSession, maps: Any, ai: Any, settings_env: Any
) -> None:
    settings_env(INSTAGRAM_BUSINESS_DISCOVERY_ENABLED="true")
    _evidence_with_instagram(ai, "https://www.instagram.com/demo_restaurant/?hl=ko")
    store_id, run_id = await _collect(db, maps)
    _, snap = await _instagram(db)
    assert snap.status == "ok" and snap.payload["biography"].startswith("명동 40년")
    assert get_clients().instagram.calls == ["demo_restaurant"]
    owner = await db.get(User, await db.scalar(select(Store.owner_id).where(Store.id == store_id)))
    info = await collect_service.collected(db, get_clients(), owner, run_id)
    intro = next(r for r in info.rows if r.key == "intro")
    assert intro.values.instagram == snap.payload["biography"]


async def test_bd_failure_is_failed_snapshot_and_collection_continues(
    db: AsyncSession, maps: Any, ai: Any, settings_env: Any
) -> None:
    settings_env(INSTAGRAM_BUSINESS_DISCOVERY_ENABLED="true")
    _evidence_with_instagram(ai, "https://www.instagram.com/personal_account/")  # 가짜 BD에 없음 = 개인 계정
    store_id, _ = await _collect(db, maps)
    _, snap = await _instagram(db)
    assert (snap.status, snap.error_code, snap.payload) == ("failed", "graph_110", None)
    assert (await db.get(Store, store_id)).status == "measuring"


async def test_candidate_order_google_website_before_web_evidence(
    db: AsyncSession, maps: Any, ai: Any
) -> None:
    _evidence_with_instagram(ai, "https://www.instagram.com/from_evidence/")
    await _collect(db, maps, websiteUri="https://www.instagram.com/from_google/")
    src, _ = await _instagram(db)
    assert (src.external_id, src.url) == ("from_google", "https://www.instagram.com/from_google/")


async def test_instagram_decided_even_after_collect_timeout(
    db: AsyncSession, maps: Any, ai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """전체 45초 제한이 AI 웹 검색을 끊어도 그때까지 모은 후보(Google websiteUri)로 인스타그램을 정한다."""
    monkeypatch.setattr(collect_service, "COLLECT_TIMEOUT_S", 0.3)
    ai.gemini.fail_next(1, "hang", only="web_answer")
    store_id, _ = await _collect(db, maps, websiteUri="https://instagram.com/kyoja_official")
    src, _ = await _instagram(db)
    assert (src.match_status, src.external_id) == ("found", "kyoja_official")
    assert (await db.get(Store, store_id)).status == "measuring"


# --- 실제 어댑터(GraphInstagram)를 가짜 전송으로 ----------------------------------------------


def _graph(handler: Any) -> GraphInstagram:
    return GraphInstagram(transport=httpx.MockTransport(handler))


async def test_graph_adapter_request_and_result(settings_env: Any) -> None:
    settings_env(
        INSTAGRAM_GRAPH_TOKEN=TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID="1784", INSTAGRAM_GRAPH_VERSION="v23.0"
    )
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200, json={"business_discovery": {"username": "kyoja", "biography": "b"}, "id": "1"}
        )

    with capture_all_logs() as logs:
        got = await _graph(handler).business_discovery("kyoja")
    assert got == {"username": "kyoja", "biography": "b"}
    url = seen[0].url
    assert (url.host, url.path) == ("graph.facebook.com", "/v23.0/1784")
    assert url.params["access_token"] == TOKEN
    assert url.params["fields"].startswith("business_discovery.username(kyoja){username,biography,website,")
    assert TOKEN not in str(logs)  # 토큰·요청 주소는 로그에 남기지 않는다


async def test_graph_adapter_errors(settings_env: Any) -> None:
    with pytest.raises(ExternalApiError) as e:  # 설정이 비면 부르지 않는다
        await _graph(lambda r: httpx.Response(200)).business_discovery("kyoja")
    assert e.value.reason == "not_configured"
    settings_env(
        INSTAGRAM_GRAPH_TOKEN=TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID="1784", INSTAGRAM_GRAPH_VERSION="v23.0"
    )
    err = {"error": {"message": "Invalid user id", "type": "OAuthException", "code": 110}}
    with pytest.raises(ExternalApiError) as e:
        await _graph(lambda r: httpx.Response(400, json=err)).business_discovery("someone")
    assert (e.value.reason, e.value.status) == ("graph_110", 400)

    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ExternalApiError) as e:
        await _graph(boom).business_discovery("kyoja")
    assert e.value.reason == "ConnectError"
