"""정보 수집 collectStore(07 6장, W-03-1·2·3)와 모은 정보 표(07 7장, W-03-6).

순서(6.1): 대상 확인 → Google 상세 → (동시에) 웹사이트·AI 웹 검색 → 인스타그램 → 지역 확인 → E2/E3.
- 출처마다 따로 감싸 하나가 실패해도 나머지를 저장한다. 출처 결과는 끝날 때마다 커밋한다.
- 외부 호출 동안 트랜잭션을 열어 두지 않는다(01 7.2). 전체 45초를 넘으면 그때까지 저장한 것으로 넘어간다.
- 카카오·네이버 값은 저장하지 않는다(DB CHECK로도 막힘). LLM 요청에도 넣지 않는다.
- AI 웹 검색(6.4)에는 가게 이름과 주소(Google, 없으면 카카오 도로명)만 보낸다. 네이버 값은 넣지 않는다.
- 인스타그램(6.5)은 45초 제한이 끊어도 그때까지 모은 후보 주소로 정한다(Business Discovery는 따로 5초).
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import session_scope
from seelo.domain.attributes import true_labels
from seelo.domain.hours import to_weekly_hours
from seelo.domain.labels import COLLECTED_ROW_LABEL, PRICE_LEVEL_LABEL
from seelo.domain.matching import evidence_matches
from seelo.domain.normalize import domain_of
from seelo.domain.region import from_google, from_kakao_address
from seelo.domain.states import (
    MatchStatus,
    RunKind,
    RunStage,
    RunStatus,
    SnapshotStatus,
    StoreStatus,
    transition,
)
from seelo.domain.webpage import find_menu_link, has_english_page, instagram_username, links, page_text
from seelo.errors import AppError
from seelo.integrations import Clients, Place, get_clients
from seelo.integrations.http import ExternalApiError
from seelo.integrations.llm import LlmError, cost_usd
from seelo.integrations.website import WebsiteError
from seelo.models.measurement import MeasurementRun
from seelo.models.store import SourceSnapshot, Store, StoreSource, WebEvidence
from seelo.models.user import User
from seelo.schemas.llm import WebEvidenceExtractOut, WebsiteExtractOut
from seelo.schemas.run import CollectedInfo, CollectedRow, CollectedValues
from seelo.services import jobs
from seelo.services.refetch import google_ref, refetch_kakao, refetch_naver
from seelo.services.run_failure import fail_run
from seelo.timeutil import now_utc

log = structlog.get_logger()

COLLECT_TIMEOUT_S = 45.0
GOOGLE_RETRY_DELAY_S = 1.0
AI_WEB_TIMEOUT_S = 60.0  # 단계마다. 실제로는 전체 45초가 먼저 끊을 수 있다
INSTAGRAM_TIMEOUT_S = 5.0
AI_WEB_PROMPT = (  # 07 6.4 1단계(그대로)
    "Find publicly available information about this place.\n"
    "Name: {name}\n"
    "Address: {address}\n"
    "Search the web and list every website that has information about this exact place.\n"
    "For each website, give the URL, the site name, and the place's name, address, phone number,\n"
    "opening hours, and menu items with prices exactly as stated on that site."
)
EVIDENCE_PROMPT = (  # 07 6.4 2단계 정리
    "Below is an AI answer that lists websites with information about one place, and its sources.\n"
    "For each website in the answer, copy the URL, the site name, and the place's name, address, phone,\n"
    "opening hours text, menu items (price in KRW only when written as a number), and any Instagram\n"
    "profile URL, exactly as stated. Use null or empty lists for anything not stated. Do not guess.\n\n"
)
GOOGLE_DETAIL_FIELDS = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "addressComponents",
        "location",
        "types",
        "photos",
        "primaryType",
        "primaryTypeDisplayName",
        "googleMapsUri",
        "businessStatus",
        "accessibilityOptions",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "websiteUri",
        "regularOpeningHours",
        "priceLevel",
        "priceRange",
        "rating",
        "userRatingCount",
        "editorialSummary",
        "reviews",
        "dineIn",
        "takeout",
        "delivery",
        "reservable",
        "paymentOptions",
        "servesVegetarianFood",
        "servesBreakfast",
        "servesLunch",
        "servesDinner",
        "servesBeer",
        "servesWine",
        "servesCocktails",
        "servesCoffee",
        "servesDessert",
        "goodForChildren",
        "goodForGroups",
        "outdoorSeating",
        "allowsDogs",
        "restroom",
        "parkingOptions",
    ]
)
GOOGLE_EN_FIELDS = "displayName,addressComponents"

WEBSITE_PROMPT = (
    "아래는 한 가게의 공식 웹사이트에서 읽은 글이다. 주어진 텍스트에 있는 내용만 옮긴다. "
    "없는 값은 null 또는 빈 목록. 추측 금지.\n"
    "영업시간 hours_text는 원문 그대로, hours는 요일별로(텍스트에 나온 요일만, 시각은 HH:MM). "
    "메뉴 가격은 원 단위 숫자로 적혀 있을 때만.\n\n"
)


@dataclass
class Ctx:
    clients: Clients
    store_id: int
    store_name: str
    owner_id: int
    run_id: int | None
    run_kind: str | None
    sources: dict[str, StoreSource]
    google_ko: dict[str, Any] | None = None
    google_en: dict[str, Any] | None = None
    instagram_candidates: list[str] = field(default_factory=list)  # 웹사이트 첫 페이지 링크
    evidence_instagram: list[str] = field(default_factory=list)  # web_evidence의 instagramUrl·site_url


def _expires() -> Any:
    return now_utc() + timedelta(days=get_settings().snapshot_retention_days)


async def _upsert_source(
    s: AsyncSession,
    store_id: int,
    provider: str,
    status: str,
    *,
    external_id: str | None = None,
    url: str | None = None,
) -> int:
    stmt = (
        insert(StoreSource)
        .values(store_id=store_id, provider=provider, external_id=external_id, url=url, match_status=status)
        .on_conflict_do_update(
            constraint="uq_store_source",
            set_={"external_id": external_id, "url": url, "match_status": status, "matched_at": now_utc()},
        )
        .returning(StoreSource.id)
    )
    return (await s.execute(stmt)).scalar_one()


async def _save_snapshot(
    ctx: Ctx,
    provider: str,
    status: str,
    *,
    payload: dict[str, Any] | None = None,
    error_code: str | None = None,
    source_id: int | None = None,
) -> None:
    async with session_scope() as s:
        s.add(
            SourceSnapshot(
                source_id=source_id or ctx.sources[provider].id,
                store_id=ctx.store_id,
                run_id=ctx.run_id,
                provider=provider,
                status=status,
                error_code=error_code,
                payload=payload,
                expires_at=_expires(),
            )
        )
        await s.commit()


async def add_run_cost(run_id: int | None, usd: float) -> None:
    """측정에 속한 LLM 호출 비용을 측정 cost_usd에 더한다(06 6장)."""
    if run_id is None or usd <= 0:
        return
    async with session_scope() as s:
        await s.execute(
            update(MeasurementRun)
            .where(MeasurementRun.id == run_id)
            .values(cost_usd=MeasurementRun.cost_usd + usd)
        )
        await s.commit()


# --- 6.2 Google 상세 -----------------------------------------------------------------------


async def _google_details(ctx: Ctx, place_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ko, en = await asyncio.gather(
        ctx.clients.places.details(place_id, fields=GOOGLE_DETAIL_FIELDS, language="ko"),
        ctx.clients.places.details(place_id, fields=GOOGLE_EN_FIELDS, language="en"),
        return_exceptions=True,
    )
    if isinstance(ko, BaseException):
        raise ko
    if isinstance(en, BaseException):  # 영문은 지역 이름에만 쓴다. 실패해도 한국어로 계속
        log.info("google_en_failed", store_id=ctx.store_id, error=type(en).__name__)
        en = None
    return ko, en


async def collect_google(ctx: Ctx) -> None:
    src = ctx.sources.get("google")
    if src is None or src.match_status != MatchStatus.FOUND or not src.external_id:
        return  # 못 찾은 가게는 스냅샷 없음(08 6장 listing 판정으로)
    error = "unknown"
    for attempt in (1, 2):
        try:
            ko, en = await _google_details(ctx, src.external_id)
            if ko is None:
                error = "not_found"
                break
            photos = ko.pop("photos", None) or []
            ctx.google_ko, ctx.google_en = ko, en
            payload = {"ko": ko, "en": en, "photoCount": len(photos)}
            await _save_snapshot(ctx, "google", SnapshotStatus.OK, payload=payload)
            return
        except ExternalApiError as e:
            error = e.reason if e.status is None else f"http_{e.status}"
            log.warning("google_details_failed", store_id=ctx.store_id, attempt=attempt, error=error)
            if attempt == 1:
                await asyncio.sleep(GOOGLE_RETRY_DELAY_S)
    await _save_snapshot(ctx, "google", SnapshotStatus.FAILED, error_code=error)


# --- 6.3 공식 웹사이트 ---------------------------------------------------------------------


async def _website_url(ctx: Ctx) -> str | None:
    """Google websiteUri → 없으면 네이버 다시 부르기 결과의 link(값 자체는 저장·AI 입력하지 않음)."""
    if ctx.google_ko and ctx.google_ko.get("websiteUri"):
        return ctx.google_ko["websiteUri"]
    naver = ctx.sources.get("naver")
    if naver is None or naver.match_status != MatchStatus.FOUND:
        return None
    refs = [p for p in [google_ref(ctx.google_ko)] if p is not None]
    if not refs:
        kakao = ctx.sources.get("kakao")
        k = await refetch_kakao(ctx.clients, kakao.external_id if kakao else None, [ctx.store_name])
        refs = [k] if k else []
    hit = await refetch_naver(ctx.clients, ctx.store_name, refs)
    return (hit.raw.get("link") or None) if hit else None


async def _set_source(ctx: Ctx, provider: str, status: str, **kw: str | None) -> int:
    async with session_scope() as s:
        sid = await _upsert_source(s, ctx.store_id, provider, status, **kw)
        await s.commit()
    return sid


async def _extract(ctx: Ctx, texts: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    prompt = WEBSITE_PROMPT + "\n\n".join(f"[페이지 {i + 1}]\n{t}" for i, t in enumerate(texts) if t)
    model = get_settings().openai_cheap_model
    try:
        res = await ctx.clients.openai.structured(prompt, WebsiteExtractOut, model=model)
    except (LlmError, NotImplementedError) as e:
        reason = e.reason if isinstance(e, LlmError) else "not_implemented"
        log.warning("website_extract_failed", store_id=ctx.store_id, reason=reason)
        return None, reason
    await add_run_cost(
        ctx.run_id,
        cost_usd("openai", res.model_id, input_tokens=res.input_tokens, output_tokens=res.output_tokens),
    )
    out: WebsiteExtractOut = res.parsed  # type: ignore[assignment]
    extract = out.model_dump(exclude={"hours"})
    extract["hours"] = to_weekly_hours(out.hours)
    return extract, None


async def collect_website(ctx: Ctx) -> None:
    url = await _website_url(ctx)
    if not url:
        sid = await _set_source(ctx, "website", MatchStatus.NOT_FOUND)
        await _save_snapshot(ctx, "website", SnapshotStatus.SKIPPED, error_code="no_url", source_id=sid)
        return
    if domain_of(url) == "instagram.com":
        ctx.instagram_candidates.append(url)
        sid = await _set_source(ctx, "website", MatchStatus.NOT_FOUND)
        await _save_snapshot(ctx, "website", SnapshotStatus.SKIPPED, error_code="instagram", source_id=sid)
        return
    sid = await _set_source(ctx, "website", MatchStatus.FOUND, url=url)
    site = ctx.clients.website
    robots = await site.robots_allows(url)
    if not robots.allowed:
        # 공인 주소가 아니면 robots 금지가 아니라 실패로 남긴다
        status = (
            SnapshotStatus.FAILED if robots.reason == "blocked_host" else SnapshotStatus.ROBOTS_DISALLOWED
        )
        await _save_snapshot(ctx, "website", status, error_code=robots.reason, source_id=sid)
        return
    try:
        home = await site.fetch(url)
    except WebsiteError as e:
        status = (
            SnapshotStatus.ROBOTS_DISALLOWED if e.reason == "robots_disallowed" else SnapshotStatus.FAILED
        )
        await _save_snapshot(ctx, "website", status, error_code=e.reason, source_id=sid)
        return
    ctx.instagram_candidates.extend(u for u, _ in links(home.html, home.url))
    texts = [page_text(home.html)]
    menu_url = find_menu_link(home.html, home.url)
    if menu_url:
        try:
            if (await site.robots_allows(menu_url)).allowed:
                texts.append(page_text((await site.fetch(menu_url)).html))
            else:
                menu_url = None
        except WebsiteError as e:
            log.info("website_menu_failed", store_id=ctx.store_id, reason=e.reason)
            menu_url = None
    extract, extract_error = await _extract(ctx, texts)
    payload = {
        "url": home.url,
        "menuUrl": menu_url,
        "hasEnglishPage": has_english_page(home.html, home.url),
        "extract": extract,
        "fetchedAt": now_utc().isoformat(),
    }
    if extract_error:
        payload["extractError"] = extract_error
    await _save_snapshot(ctx, "website", SnapshotStatus.OK, payload=payload, source_id=sid)


# --- 6.4 AI 웹 검색 --------------------------------------------------------------------------


async def _ai_web_target(ctx: Ctx) -> tuple[str | None, list[str]]:
    """(주소, 우리 가게 이름 후보). 주소는 Google formattedAddress → 없으면 카카오 다시 부르기 도로명 주소.

    네이버 값은 쓰지 않는다. 카카오 이름은 거르기(코드 비교)에만 쓰고 AI에 보내지 않는다.
    """
    ko, en = ctx.google_ko or {}, ctx.google_en or {}
    names = [
        ctx.store_name,
        (ko.get("displayName") or {}).get("text"),
        (en.get("displayName") or {}).get("text"),
    ]
    address = ko.get("formattedAddress")
    if not address:
        kakao = ctx.sources.get("kakao")
        if kakao is not None and kakao.match_status == MatchStatus.FOUND:
            place = await refetch_kakao(ctx.clients, kakao.external_id, [n for n in names if n])
            if place is not None:
                address = place.raw.get("road_address_name") or None
                names.append(place.name)
    return address, [n for n in dict.fromkeys(names) if n]


async def _ai_web_one(ctx: Ctx, provider: str, prompt: str, names: list[str], address: str) -> None:
    """공급자 하나: 웹 검색 답변 → 정리(structured) → 거르기 → web_evidence 저장. 실패하면 그 공급자만 빔."""
    s = get_settings()
    client = ctx.clients.openai if provider == "openai" else ctx.clients.gemini
    model = s.openai_measure_model if provider == "openai" else s.gemini_measure_model
    try:
        async with asyncio.timeout(AI_WEB_TIMEOUT_S):
            answer = await client.web_answer(prompt, model=model)
    except (TimeoutError, LlmError) as e:
        reason = e.reason if isinstance(e, LlmError) else "timeout"
        log.warning("ai_web_search_failed", store_id=ctx.store_id, provider=provider, step=1, reason=reason)
        return
    await add_run_cost(
        ctx.run_id,
        cost_usd(
            provider,
            answer.model_id or model,
            input_tokens=answer.input_tokens,
            output_tokens=answer.output_tokens,
            search_calls=answer.search_calls,
        ),
    )
    sources = "\n".join(f"[{x['n']}] {x['url']}" for x in answer.sources) or "(none)"
    text_ = EVIDENCE_PROMPT + f"Answer:\n{answer.annotated_text or answer.text}\n\nSources:\n{sources}"
    try:
        async with asyncio.timeout(AI_WEB_TIMEOUT_S):
            res = await ctx.clients.openai.structured(
                text_, WebEvidenceExtractOut, model=s.openai_cheap_model
            )
    except (TimeoutError, LlmError) as e:
        reason = e.reason if isinstance(e, LlmError) else "timeout"
        log.warning("ai_web_search_failed", store_id=ctx.store_id, provider=provider, step=2, reason=reason)
        return
    await add_run_cost(
        ctx.run_id,
        cost_usd("openai", res.model_id, input_tokens=res.input_tokens, output_tokens=res.output_tokens),
    )
    out: WebEvidenceExtractOut = res.parsed  # type: ignore[assignment]
    kept = [
        site
        for site in out.sites
        if site.url.strip()
        and evidence_matches(
            site.name, site.address, names=names, our_address=address, threshold=s.name_similarity_threshold
        )
    ]
    if kept:
        async with session_scope() as db:
            db.add_all(
                WebEvidence(
                    store_id=ctx.store_id,
                    run_id=ctx.run_id,
                    provider=provider,
                    site_url=site.url.strip(),
                    site_name=site.site_name,
                    fields=site.model_dump(),
                    expires_at=_expires(),
                )
                for site in kept
            )
            await db.commit()
    for site in kept:  # 6.5 1번: web_evidence의 instagramUrl·site_url
        ctx.evidence_instagram.extend(u for u in (site.instagram_url, site.url) if u)
    log.info("ai_web_search", store_id=ctx.store_id, provider=provider, sites=len(out.sites), kept=len(kept))


async def collect_ai_web(ctx: Ctx) -> None:
    """6.4: 공급자별 웹 검색 1회(가게 이름·주소) → 정리 → 이름·주소가 맞는 사이트만 저장."""
    address, names = await _ai_web_target(ctx)
    if not address:  # 이 가게라고 특정할 수 없다
        log.info("ai_web_search_skip", store_id=ctx.store_id, reason="no_address")
        return
    prompt = AI_WEB_PROMPT.format(name=ctx.store_name, address=address)
    await asyncio.gather(*(_ai_web_one(ctx, p, prompt, names, address) for p in ("openai", "gemini")))


# --- 6.5 인스타그램 --------------------------------------------------------------------------


async def collect_instagram(ctx: Ctx) -> None:
    """후보 주소(웹사이트 첫 페이지 링크 → Google websiteUri → web_evidence)에서 첫 프로필 주소.

    INSTAGRAM_BUSINESS_DISCOVERY_ENABLED일 때만 Business Discovery를 부른다(꺼져 있으면 Graph 호출 0번).
    """
    candidates = list(ctx.instagram_candidates)
    if ctx.google_ko and ctx.google_ko.get("websiteUri"):
        candidates.append(ctx.google_ko["websiteUri"])
    candidates += ctx.evidence_instagram
    username, url = next(
        ((instagram_username(u), u) for u in candidates if instagram_username(u)), (None, None)
    )
    if not username:
        await _set_source(ctx, "instagram", MatchStatus.NOT_FOUND)
        return
    sid = await _set_source(ctx, "instagram", MatchStatus.FOUND, external_id=username, url=url)
    if not get_settings().instagram_business_discovery_enabled:
        return
    try:
        async with asyncio.timeout(INSTAGRAM_TIMEOUT_S):
            profile = await ctx.clients.instagram.business_discovery(username)
    except (TimeoutError, ExternalApiError) as e:
        reason = e.reason if isinstance(e, ExternalApiError) else "timeout"
        await _save_snapshot(ctx, "instagram", SnapshotStatus.FAILED, error_code=reason, source_id=sid)
        return
    if not profile:
        await _save_snapshot(ctx, "instagram", SnapshotStatus.FAILED, error_code="no_profile", source_id=sid)
        return
    await _save_snapshot(ctx, "instagram", SnapshotStatus.OK, payload=profile, source_id=sid)


# --- 6.1 전체 ---------------------------------------------------------------------------


async def _start(store_id: int, run_id: int | None, clients: Clients) -> Ctx | None:
    """1번: 대상 확인. 측정 queued → running(stage collecting)."""
    async with session_scope() as s:
        store = await s.get(Store, store_id)
        if store is None or store.archived_at is not None:
            log.info("collect_skip_store", store_id=store_id)
            return None
        run_kind = None
        if run_id is not None:
            run = await s.get(MeasurementRun, run_id)
            started = run is not None and await transition(
                s,
                MeasurementRun,
                run_id,
                from_={RunStatus.QUEUED},
                to=RunStatus.RUNNING,
                values={"started_at": now_utc(), "stage": RunStage.COLLECTING},
            )
            if not started:
                log.info("collect_skip_run", store_id=store_id, run_id=run_id)
                return None
            run_kind = run.kind
        elif store.status != StoreStatus.COLLECTING:
            return None
        rows = (await s.scalars(select(StoreSource).where(StoreSource.store_id == store_id))).all()
        ctx = Ctx(
            clients=clients,
            store_id=store_id,
            store_name=store.name,
            owner_id=store.owner_id,
            run_id=run_id,
            run_kind=run_kind,
            sources={r.provider: r for r in rows},
        )
        await s.commit()
    return ctx


async def _region_ok(ctx: Ctx) -> bool:
    """6.6: 한글 지역을 얻을 수 있는가(업종은 stores.category에 이미 있음)."""
    ko, _ = from_google(ctx.google_ko, ctx.google_en)
    if ko:
        return True
    kakao = ctx.sources.get("kakao")
    if kakao is None or kakao.match_status != MatchStatus.FOUND:
        return False
    names = [ctx.store_name, ((ctx.google_ko or {}).get("displayName") or {}).get("text")]
    place = await refetch_kakao(ctx.clients, kakao.external_id, names)  # type: ignore[arg-type]
    return bool(place and from_kakao_address(place.raw.get("address_name")))


async def _finish(ctx: Ctx) -> None:
    """E2 수집 완료 / E3 지역·업종을 얻지 못함(같은 트랜잭션에서 다음 작업·메일 등록)."""
    region_ok = True if ctx.run_kind != RunKind.DIAGNOSIS else await _region_ok(ctx)
    async with session_scope() as s:
        if ctx.run_id is None:  # 무료 사용 뒤 바꾼 가게: 측정 없이 수집만
            await transition(s, Store, ctx.store_id, from_={StoreStatus.COLLECTING}, to=StoreStatus.COLLECTED)
            await s.commit()
            return
        run = await s.get(MeasurementRun, ctx.run_id, with_for_update=True)
        if run is None or run.status != RunStatus.RUNNING:
            log.info("collect_finish_skip", run_id=ctx.run_id)
            return
        if not region_ok:  # E3: 측정 실패·가게 measure_failed·결과 메일(run_failure)
            await fail_run(s, run, "collect_insufficient")
            await s.commit()
            log.info("collect_insufficient", store_id=ctx.store_id, run_id=ctx.run_id)
            return
        links_ = jobs.JobLinks(store_id=ctx.store_id, run_id=ctx.run_id)
        if ctx.run_kind == RunKind.DIAGNOSIS:  # E2 진단
            await transition(s, Store, ctx.store_id, from_={StoreStatus.COLLECTING}, to=StoreStatus.MEASURING)
            run.stage = RunStage.GENERATING_QUESTIONS
            from seelo.worker.tasks_measure import generate_questions

            await jobs.defer(
                s,
                generate_questions,
                args={"run_id": ctx.run_id},
                links=links_,
                queueing_lock=f"questions:{ctx.run_id}",
            )
        else:  # E2 재측정: 가게 상태는 그대로, 질문은 기준 측정의 것을 쓴다
            run.stage = RunStage.CALLING_AI
            from seelo.worker.tasks_measure import run_measurement

            await jobs.defer(
                s,
                run_measurement,
                args={"run_id": ctx.run_id},
                links=links_,
                queueing_lock=f"measure:{ctx.run_id}",
            )
        await s.commit()


async def collect_store(store_id: int, run_id: int | None, *, clients: Clients | None = None) -> None:
    ctx = await _start(store_id, run_id, clients or get_clients())
    if ctx is None:
        return
    try:
        async with asyncio.timeout(COLLECT_TIMEOUT_S):
            await _guard("google", collect_google(ctx))
            await asyncio.gather(
                _guard("website", collect_website(ctx)), _guard("ai_web", collect_ai_web(ctx))
            )
    except TimeoutError:
        log.warning("collect_timeout", store_id=store_id, run_id=run_id)
    await _guard("instagram", collect_instagram(ctx))  # 그때까지 모은 후보로
    await _finish(ctx)


async def _guard(name: str, coro: Any) -> None:
    """출처 하나의 예상 못 한 오류가 나머지 수집을 막지 않게."""
    try:
        await coro
    except asyncio.CancelledError:  # 전체 45초 제한이 끊음 → 바깥에서 TimeoutError로 바뀐다
        raise
    except Exception as e:  # 출처 안의 시간 초과(TimeoutError)도 그 출처의 실패로 본다
        log.exception("collect_source_failed", source=name, error_type=type(e).__name__)


# --- 7장 모은 정보 표 ------------------------------------------------------------------------


def _won(n: int) -> str:
    return f"{n:,}원"


def _price_range(pr: dict[str, Any] | None) -> str | None:
    if not pr:
        return None

    def units(p: dict[str, Any] | None) -> int | None:
        return int(p["units"]) if p and p.get("units") is not None else None

    a, b = units(pr.get("startPrice")), units(pr.get("endPrice"))
    if a is None and b is None:
        return None
    return f"{_won(a) if a is not None else ''}~{_won(b) if b is not None else ''}"


def _menu_price_range(menu: list[dict[str, Any]]) -> str | None:
    prices = [m["price"] for m in menu if m.get("price") is not None]
    if not prices:
        return None
    lo, hi = min(prices), max(prices)
    return _won(lo) if lo == hi else f"{_won(lo)}~{_won(hi)}"


def _menu_text(menu: list[dict[str, Any]]) -> str | None:
    items = [
        f"{m['name']} {_won(m['price'])}" if m.get("price") else m["name"] for m in menu[:5] if m.get("name")
    ]
    return ", ".join(items) or None


async def latest_snapshot(
    db: AsyncSession, store_id: int, run_id: int, provider: str
) -> dict[str, Any] | None:
    """그 측정의 ok 스냅샷. 없으면(수집만 한 가게 등) 가게의 최근 ok 스냅샷."""
    base = select(SourceSnapshot.payload).where(
        SourceSnapshot.store_id == store_id,
        SourceSnapshot.provider == provider,
        SourceSnapshot.status == SnapshotStatus.OK,
    )
    payload = await db.scalar(
        base.where(SourceSnapshot.run_id == run_id).order_by(SourceSnapshot.id.desc()).limit(1)
    )
    if payload is None:
        payload = await db.scalar(base.order_by(SourceSnapshot.collected_at.desc()).limit(1))
    return payload


async def collected(db: AsyncSession, clients: Clients, user: User, run_id: int) -> CollectedInfo:
    run = await db.get(MeasurementRun, run_id)
    store = await db.get(Store, run.store_id) if run else None
    if run is None or store is None or (store.owner_id != user.id and user.role != "admin"):
        raise AppError("NOT_FOUND")
    sources = {
        r.provider: r for r in (await db.scalars(select(StoreSource).where(StoreSource.store_id == store.id)))
    }
    google_snap = await latest_snapshot(db, store.id, run_id, "google")
    web_snap = await latest_snapshot(db, store.id, run_id, "website")
    insta_snap = await latest_snapshot(db, store.id, run_id, "instagram")
    g = (google_snap or {}).get("ko") or {}
    name, gname = store.name, (g.get("displayName") or {}).get("text")
    await db.commit()  # 외부 호출 동안 트랜잭션을 열어 두지 않는다

    kakao_src, naver_src = sources.get("kakao"), sources.get("naver")
    kakao: Place | None = None
    if kakao_src and kakao_src.match_status == MatchStatus.FOUND:
        kakao = await refetch_kakao(clients, kakao_src.external_id, [name, gname], near=_coords(g))
    naver: Place | None = None
    if naver_src and naver_src.match_status == MatchStatus.FOUND:
        naver = await refetch_naver(clients, name, [p for p in (google_ref(g or None), kakao) if p])

    ext = (web_snap or {}).get("extract") or {}
    insta = sources.get("instagram")
    insta_found = insta is not None and insta.match_status == MatchStatus.FOUND
    hours = g.get("regularOpeningHours") or {}
    k_raw, n_raw = (kakao.raw if kakao else {}), (naver.raw if naver else {})
    amenities = ", ".join(true_labels(g)) or None
    table: dict[str, dict[str, str | None]] = {
        "name": {
            "google": gname,
            "kakao": k_raw.get("place_name"),
            "naver": naver.name if naver else None,
            "instagram": insta.external_id if insta_found else None,
        },
        "address": {
            "google": g.get("formattedAddress"),
            "kakao": k_raw.get("road_address_name"),
            "naver": n_raw.get("roadAddress"),
            "website": ext.get("address"),
        },
        "phone": {
            "google": g.get("nationalPhoneNumber"),
            "kakao": k_raw.get("phone"),
            "website": ext.get("phone"),
        },
        "hours": {
            "google": "\n".join(hours.get("weekdayDescriptions") or []) or None,
            "website": ext.get("hours_text"),
        },
        "website": {
            "google": g.get("websiteUri"),
            "naver": n_raw.get("link") or None,
            "website": (web_snap or {}).get("url"),
        },
        "price": {
            "google": PRICE_LEVEL_LABEL.get(g.get("priceLevel", "")) or _price_range(g.get("priceRange")),
            "website": _menu_price_range(ext.get("menu") or []),
        },
        "category": {
            "google": (g.get("primaryTypeDisplayName") or {}).get("text"),
            "kakao": (k_raw.get("category_name") or "").split(">")[-1].strip() or None,
            "naver": n_raw.get("category") or None,
        },
        "menu": {"website": _menu_text(ext.get("menu") or [])},
        "intro": {
            "google": (g.get("editorialSummary") or {}).get("text"),
            "website": ext.get("intro"),
            "instagram": (insta_snap or {}).get("biography") if insta_found else None,
        },
        "amenities": {
            "google": amenities,
            "website": "영문 페이지 있음" if (web_snap or {}).get("hasEnglishPage") else None,
        },
        "instagram": {"instagram": insta.url if insta_found else None},
    }
    rows = [
        CollectedRow(key=key, label=COLLECTED_ROW_LABEL[key], values=CollectedValues(**vals))
        for key, vals in table.items()
        if any(v for v in vals.values())
    ]
    return CollectedInfo(rows=rows)


def _coords(g: dict[str, Any]) -> tuple[float, float] | None:
    loc = g.get("location") or {}
    if loc.get("latitude") is None or loc.get("longitude") is None:
        return None
    return loc["latitude"], loc["longitude"]


# --- purgeSnapshots(06 5장) -------------------------------------------------------------------


async def purge_expired(s: AsyncSession) -> dict[str, int]:
    """보관 기한이 지난 스냅샷·웹 근거 삭제(D-10). 커밋은 부르는 쪽."""
    snaps = await s.execute(text("DELETE FROM source_snapshots WHERE expires_at < now()"))
    evid = await s.execute(text("DELETE FROM web_evidence WHERE expires_at < now()"))
    orphan = await s.execute(
        text(
            "DELETE FROM job_links jl WHERE NOT EXISTS "
            "(SELECT 1 FROM procrastinate_jobs j WHERE j.id = jl.procrastinate_job_id)"
        )
    )
    return {
        "snapshots": snaps.rowcount or 0,
        "web_evidence": evid.rowcount or 0,
        "job_links": orphan.rowcount or 0,
    }  # type: ignore[attr-defined]
