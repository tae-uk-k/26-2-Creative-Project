"""카카오·네이버 다시 부르기(07 4.2·4.3). 두 지도 값은 저장하지 않으므로 쓸 때마다 다시 부른다.

각 5초, 오류·시간 초과·못 찾음은 None(화면에는 "불러오지 못함").
"""

import asyncio

import structlog

from seelo.config import get_settings
from seelo.domain.matching import pick_same_place
from seelo.integrations import Clients, Place
from seelo.integrations.http import MAP_API_TIMEOUT_S, ExternalApiError

log = structlog.get_logger()

KAKAO_PAGES = 3


async def refetch_kakao(
    clients: Clients,
    kakao_id: str | None,
    names: list[str],
    near: tuple[float, float] | None = None,
) -> Place | None:
    """이름을 바꿔 가며 키워드 검색해 id가 같은 문서를 찾는다(가능하면 좌표 200m 안에서)."""
    if not kakao_id:
        return None
    x, y = (near[1], near[0]) if near else (None, None)
    try:
        async with asyncio.timeout(MAP_API_TIMEOUT_S):
            for name in dict.fromkeys(n for n in names if n):
                for page in range(1, KAKAO_PAGES + 1):
                    places, is_end = await clients.kakao.keyword(
                        name, x=x, y=y, radius=200 if near else None, page=page, size=15
                    )
                    hit = next((p for p in places if p.external_id == kakao_id), None)
                    if hit is not None:
                        return hit
                    if is_end:
                        break
    except (TimeoutError, ExternalApiError) as e:
        log.info("kakao_refetch_failed", error=type(e).__name__)
    return None


async def refetch_naver(clients: Clients, name: str, refs: list[Place]) -> Place | None:
    """입력 이름으로 검색 → 기준(Google·카카오) 좌표 100m 안이고 이름이 같은 결과."""
    refs = [r for r in refs if r.lat is not None and r.lng is not None]
    if not refs:
        return None
    try:
        async with asyncio.timeout(MAP_API_TIMEOUT_S):
            results = await clients.naver.search(name, display=5)
    except (TimeoutError, ExternalApiError) as e:
        log.info("naver_refetch_failed", error=type(e).__name__)
        return None
    th = get_settings().name_similarity_threshold
    for ref in refs:
        hit = pick_same_place(ref, results, names=[name, ref.name], threshold=th)
        if hit is not None:
            return hit
    return None


def google_ref(ko: dict | None) -> Place | None:
    """Google 스냅샷(ko) → 좌표 기준용 Place."""
    if not ko or not ko.get("location"):
        return None
    from seelo.integrations.google_places import to_place

    return to_place(ko)


async def refetch_basics(
    clients: Clients, store_name: str, google: dict | None, sources: dict
) -> tuple[Place | None, Place | None]:
    """카카오·네이버 기본정보를 한 번씩 다시 부른다(이름 후보·출처 비교 공용). google은 스냅샷 payload.

    sources는 provider → StoreSource. 못 찾은 지도는 부르지 않는다.
    """
    ko = (google or {}).get("ko") or {}
    gname = (ko.get("displayName") or {}).get("text")
    kakao_src, naver_src = sources.get("kakao"), sources.get("naver")
    kakao = None
    if kakao_src is not None and kakao_src.match_status == "found":
        kakao = await refetch_kakao(clients, kakao_src.external_id, [store_name, gname])
    naver = None
    if naver_src is not None and naver_src.match_status == "found":
        naver = await refetch_naver(clients, store_name, [p for p in (google_ref(ko or None), kakao) if p])
    return kakao, naver


def name_candidates(store_name: str, google: dict | None, *places: Place | None) -> list[str]:
    """우리 가게 이름 후보(08 4.2): 입력 이름, Google ko·en, 다시 부른 카카오·네이버 이름."""
    ko, en = (google or {}).get("ko") or {}, (google or {}).get("en") or {}
    names = [store_name, (ko.get("displayName") or {}).get("text"), (en.get("displayName") or {}).get("text")]
    names += [p.name for p in places if p is not None]
    return [n for n in names if n]
