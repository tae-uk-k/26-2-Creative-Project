"""가게 찾기·후보 선택·가게 확정(07 3장, 03 E1·E27, W-02-3·4·5).

- 외부 호출 전체를 10초로 묶는다. 넘거나 기준 지도가 오류면 503 TRY_LATER이고 아무것도 저장하지 않는다.
- 이 단계의 외부 호출은 재시도하지 않는다. 다른 두 지도는 각 5초, 오류·시간 초과면 not_found로 두고 계속한다.
- 카카오·네이버 응답 값은 저장하지 않는다(카카오는 id·place_url, 네이버는 입력 링크와 번호만).
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.domain.categories import classify_category, classify_one
from seelo.domain.links import LinkInfo, classify, pick_supported
from seelo.domain.matching import naver_fingerprint, pick_same_place, same_name_results, within
from seelo.domain.normalize import normalize_name
from seelo.domain.states import (
    MatchStatus,
    RunKind,
    RunStage,
    RunStatus,
    RunTrigger,
    ScheduleStatus,
    StoreStatus,
    transition,
)
from seelo.errors import AppError
from seelo.integrations import Clients, Place
from seelo.integrations.google_places import IDENTIFY_FIELDS
from seelo.integrations.google_places import to_place as google_place
from seelo.integrations.http import MAP_API_TIMEOUT_S, ExternalApiError
from seelo.models.fix import FixRequest, RemeasureSchedule
from seelo.models.measurement import MeasurementRun
from seelo.models.store import IdentifySession, Store, StoreSource
from seelo.models.user import User
from seelo.schemas.store import (
    Candidate,
    IdentifyCandidates,
    IdentifyConfirmed,
    IdentifyRequest,
    IdentifySelectRequest,
)
from seelo.security import ratelimit
from seelo.security.tokens import hash_token, new_token
from seelo.services import audit, jobs
from seelo.services.eligibility import active_request, current_store, has_used_free
from seelo.timeutil import now_utc

log = structlog.get_logger()

IDENTIFY_TIMEOUT_S = 10.0
CANDIDATE_TTL = timedelta(minutes=30)
GOOGLE_LINK_RADIUS_M = 200.0
SAME_PLACE_M = 100.0
KAKAO_MAX_PAGES = 3
PROVIDERS = ("google", "kakao", "naver")


@dataclass
class BaseOutcome:
    """기준 지도 결과: 확정 1곳(place) 또는 후보 여러 곳(candidates)."""

    place: Place | None = None
    candidates: list[Place] | None = None


def _threshold() -> int:
    return get_settings().name_similarity_threshold


# --- 3.2 기준 지도에서 찾기 -------------------------------------------------------


async def _kakao_pages(clients: Clients, query: str, *, want_id: str | None = None) -> list[Place]:
    """키워드 검색 1~3쪽(15개씩). want_id를 찾으면 거기서 멈춘다."""
    out: list[Place] = []
    for page in range(1, KAKAO_MAX_PAGES + 1):
        places, is_end = await clients.kakao.keyword(query, page=page, size=15)
        out.extend(places)
        if is_end or (want_id and any(p.external_id == want_id for p in places)):
            break
    return out


async def find_on_base(clients: Clients, link: LinkInfo, input_name: str) -> BaseOutcome:
    th = _threshold()
    if link.provider == "google":
        if link.place_id:
            raw = await clients.places.details(link.place_id, fields=IDENTIFY_FIELDS)
            if raw is None:
                raise AppError("STORE_NOT_FOUND")
            return BaseOutcome(place=google_place(raw))
        query = link.name or input_name
        results = await clients.places.search_text(
            query, lat=link.lat, lng=link.lng, radius_m=GOOGLE_LINK_RADIUS_M, page_size=5
        )
        if link.lat is not None and link.lng is not None:
            results = within(results, (link.lat, link.lng), GOOGLE_LINK_RADIUS_M)
        hits = same_name_results(results, [n for n in (link.name, input_name) if n], th)
    elif link.provider == "kakao":
        results = await _kakao_pages(clients, input_name, want_id=link.external_id)
        exact = next((p for p in results if p.external_id == link.external_id), None)
        if exact is not None:
            return BaseOutcome(place=exact)
        hits = same_name_results(results, [input_name], th)
        return _as_candidates_or_none(hits)
    else:  # naver: 장소 번호를 주지 않으므로 이름으로만 정한다
        results = await clients.naver.search(input_name, display=5)
        target = normalize_name(input_name)
        exact = [p for p in results if normalize_name(p.name) == target]
        if len(exact) == 1:
            return BaseOutcome(place=exact[0])
        hits = exact or same_name_results(results, [input_name], th)
        return _as_candidates_or_none(hits)

    if len(hits) == 1:
        return BaseOutcome(place=hits[0])
    return _as_candidates_or_none(hits)


def _as_candidates_or_none(hits: list[Place]) -> BaseOutcome:
    if not hits:
        raise AppError("STORE_NOT_FOUND")
    return BaseOutcome(candidates=hits[:5])


# --- 3.3 다른 지도에서 같은 가게 찾기 ------------------------------------------------


async def _search(clients: Clients, provider: str, name: str, ref: Place) -> list[Place]:
    if provider == "google":
        return await clients.places.search_text(name, lat=ref.lat, lng=ref.lng, radius_m=200.0, page_size=5)
    if provider == "kakao":
        places, _ = await clients.kakao.keyword(name, x=ref.lng, y=ref.lat, radius=200, sort="distance")
        return places
    return await clients.naver.search(name, display=5)


async def _find_one_other(clients: Clients, provider: str, base: Place, input_name: str) -> Place | None:
    """기준 좌표 100m 안 + 같은 이름. 확정 이름으로 못 찾으면 입력 이름으로 한 번 더. 오류는 None."""
    if base.lat is None or base.lng is None:
        return None
    names = [base.name, input_name]
    queries = [base.name] + ([input_name] if normalize_name(input_name) != normalize_name(base.name) else [])
    try:
        for q in queries:
            async with asyncio.timeout(MAP_API_TIMEOUT_S):
                results = await _search(clients, provider, q, base)
            found = pick_same_place(
                base, results, names=names, threshold=_threshold(), max_distance_m=SAME_PLACE_M
            )
            if found is not None:
                return found
    except (TimeoutError, ExternalApiError) as e:
        log.warning("identify_other_map_failed", provider=provider, error=type(e).__name__)
    return None


async def find_others(clients: Clients, base: Place, input_name: str) -> dict[str, Place | None]:
    others = [p for p in PROVIDERS if p != base.provider]
    found = await asyncio.gather(*(_find_one_other(clients, p, base, input_name) for p in others))
    return dict(zip(others, found, strict=True))


# --- 가게 변경 확인(3.1의 2번) --------------------------------------------------------


async def check_replace(db: AsyncSession, user: User, confirm_replace: bool) -> None:
    store = await current_store(db, user.id)
    if store is None:
        return
    if await active_request(db, store.id) is not None:
        raise AppError("FIX_IN_PROGRESS")
    if not confirm_replace:
        raise AppError("CONFIRM_REPLACE_REQUIRED", {"usedFree": await has_used_free(db, user.email)})


# --- POST /api/stores/identify --------------------------------------------------


async def identify(
    db: AsyncSession, clients: Clients, user: User, body: IdentifyRequest
) -> IdentifyConfirmed | IdentifyCandidates:
    await ratelimit.hit(db, "identify", user.id)
    await db.commit()
    await check_replace(db, user, body.confirm_replace)
    link = pick_supported(body.link)
    others: dict[str, Place | None] = {}
    try:
        async with asyncio.timeout(IDENTIFY_TIMEOUT_S):
            if link.kind == "short":
                link = await clients.short_links.resolve(link)
            outcome = await find_on_base(clients, link, body.name)
            if outcome.place is not None:
                if classify_one(outcome.place) is None:
                    raise AppError("NOT_TARGET_CATEGORY")
                others = await find_others(clients, outcome.place, body.name)
    except (TimeoutError, ExternalApiError) as e:
        log.warning("identify_try_later", provider=link.provider, error=type(e).__name__)
        raise AppError("TRY_LATER") from e
    if outcome.candidates is not None:
        return await _save_candidates(db, user, body, link, outcome.candidates)
    assert outcome.place is not None
    return await confirm(db, user, input_name=body.name, link=link, base=outcome.place, others=others)


async def _save_candidates(
    db: AsyncSession, user: User, body: IdentifyRequest, link: LinkInfo, places: list[Place]
) -> IdentifyCandidates:
    """후보는 식별자만 저장한다(카카오·네이버 이름·주소 저장 금지). 표시값은 지금 불러온 값으로."""
    stored: list[dict[str, Any]] = []
    shown: list[Candidate] = []
    for i, p in enumerate(places):
        if p.provider == "naver":
            cid, ext, fp = f"naver:{i}", None, naver_fingerprint(p)
        else:
            cid, ext, fp = f"{p.provider}:{p.external_id}", p.external_id, None
        stored.append({"candidateId": cid, "provider": p.provider, "externalId": ext, "fingerprint": fp})
        shown.append(
            Candidate(
                candidate_id=cid,
                name=p.name,
                address=p.address,
                category=classify_one(p),
                providers=[p.provider],  # type: ignore[list-item]
            )
        )
    token = new_token()
    db.add(
        IdentifySession(
            user_id=user.id,
            mode=body.mode,
            input_name=body.name,
            input_url=link.url,  # 짧은 링크면 따라간 긴 링크
            input_provider=link.provider,
            candidates=stored,
            token_hash=hash_token(token),
            expires_at=now_utc() + CANDIDATE_TTL,
        )
    )
    await db.commit()
    return IdentifyCandidates(candidate_token=token, candidates=shown)


# --- POST /api/stores/identify/select ---------------------------------------------


async def _refetch_candidate(clients: Clients, sess: IdentifySession, cand: dict[str, Any]) -> Place | None:
    provider, ext = cand["provider"], cand.get("externalId")
    if provider == "google":
        raw = await clients.places.details(ext, fields=IDENTIFY_FIELDS)
        return google_place(raw) if raw else None
    if provider == "kakao":
        results = await _kakao_pages(clients, sess.input_name, want_id=ext)
        return next((p for p in results if p.external_id == ext), None)
    results = await clients.naver.search(sess.input_name, display=5)
    return next((p for p in results if naver_fingerprint(p) == cand.get("fingerprint")), None)


async def select_candidate(
    db: AsyncSession, clients: Clients, user: User, body: IdentifySelectRequest
) -> IdentifyConfirmed:
    sess = await db.scalar(
        select(IdentifySession).where(
            IdentifySession.token_hash == hash_token(body.candidate_token), IdentifySession.user_id == user.id
        )
    )
    if sess is None or sess.expires_at <= now_utc():
        raise AppError("CANDIDATE_EXPIRED")
    cand = next((c for c in sess.candidates if c["candidateId"] == body.candidate_id), None)
    if cand is None:
        raise AppError("CANDIDATE_EXPIRED")
    store = await current_store(db, user.id)
    if store is not None and await active_request(db, store.id) is not None:
        raise AppError("FIX_IN_PROGRESS")
    link = classify(sess.input_url)
    if link is None:
        raise AppError("CANDIDATE_EXPIRED")
    try:
        async with asyncio.timeout(IDENTIFY_TIMEOUT_S):
            base = await _refetch_candidate(clients, sess, cand)
            if base is None:
                raise AppError("CANDIDATE_EXPIRED")
            if classify_one(base) is None:
                raise AppError("NOT_TARGET_CATEGORY")
            others = await find_others(clients, base, sess.input_name)
    except (TimeoutError, ExternalApiError) as e:
        log.warning("identify_select_try_later", provider=cand["provider"], error=type(e).__name__)
        raise AppError("TRY_LATER") from e
    sess_id, input_name = sess.id, sess.input_name
    await db.execute(delete(IdentifySession).where(IdentifySession.id == sess_id))
    return await confirm(db, user, input_name=input_name, link=link, base=base, others=others)


# --- E1 가게 확정(+ E27 가게 변경) ------------------------------------------------------


async def archive_store(db: AsyncSession, store: Store) -> None:
    """E27: 진행 중 측정·예약 취소, 가게 보관, 작업 취소. 진행 중인 신청이 있으면 409."""
    if await active_request(db, store.id) is not None:
        raise AppError("FIX_IN_PROGRESS")
    now = now_utc()
    await jobs.cancel_jobs(db, store_ids=[store.id])
    await db.execute(
        update(MeasurementRun)
        .where(
            MeasurementRun.store_id == store.id,
            MeasurementRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PARSING]),
        )
        .values(status=RunStatus.CANCELED)
    )
    await db.execute(
        update(RemeasureSchedule)
        .where(
            RemeasureSchedule.status == ScheduleStatus.SCHEDULED,
            RemeasureSchedule.fix_request_id.in_(
                select(FixRequest.id).where(FixRequest.store_id == store.id)
            ),
        )
        .values(status=ScheduleStatus.CANCELED)
    )
    archived = await transition(
        db,
        Store,
        store.id,
        from_={
            StoreStatus.COLLECTING,
            StoreStatus.COLLECTED,
            StoreStatus.MEASURING,
            StoreStatus.DIAGNOSED,
            StoreStatus.MEASURE_FAILED,
        },
        to=StoreStatus.ARCHIVED,
        values={"archived_at": now},
    )
    if not archived:
        raise AppError("INVALID_STATE", {"currentStatus": store.status})


def _source_rows(link: LinkInfo, base: Place, others: dict[str, Place | None]) -> list[StoreSource]:
    found = {base.provider: base, **others}
    rows = []
    for provider in PROVIDERS:
        p = found.get(provider)
        if p is None:
            rows.append(StoreSource(provider=provider, match_status=MatchStatus.NOT_FOUND))
        elif provider == "naver":
            # 네이버는 입력 링크가 네이버일 때만 링크와 번호를 남긴다. 검색 결과 값은 저장하지 않는다
            ext, url = (link.external_id, link.url) if link.provider == "naver" else (None, None)
            rows.append(
                StoreSource(provider="naver", external_id=ext, url=url, match_status=MatchStatus.FOUND)
            )
        else:  # google: place id·googleMapsUri, kakao: id·place_url
            rows.append(
                StoreSource(
                    provider=provider, external_id=p.external_id, url=p.url, match_status=MatchStatus.FOUND
                )
            )
    return rows


async def confirm(
    db: AsyncSession,
    user: User,
    *,
    input_name: str,
    link: LinkInfo,
    base: Place,
    others: dict[str, Place | None],
) -> IdentifyConfirmed:
    """E1(같은 트랜잭션): 기존 가게 보관 → 가게·출처·측정 → collectStore 등록 → 감사 기록."""
    category = classify_category([base] + [p for p in others.values() if p is not None]) or classify_one(base)
    old = await current_store(db, user.id, for_update=True)
    if old is not None:
        await archive_store(db, old)
    store = Store(
        owner_id=user.id,
        name=input_name,
        input_url=link.url,
        input_provider=link.provider,
        category=category,
        status=StoreStatus.COLLECTING,
    )
    db.add(store)
    try:
        await db.flush()
    except IntegrityError as e:  # 같은 사용자가 동시에 두 번 확정(uq_store_owner_active)
        await db.rollback()
        raise AppError("INVALID_STATE", {"currentStatus": "store_exists"}) from e
    for row in _source_rows(link, base, others):
        row.store_id = store.id
        db.add(row)

    run: MeasurementRun | None = None
    if not await has_used_free(db, user.email):
        run = MeasurementRun(
            store_id=store.id,
            kind=RunKind.DIAGNOSIS,
            is_free=True,
            trigger=RunTrigger.INITIAL,
            status=RunStatus.QUEUED,
            stage=RunStage.COLLECTING,
        )
        db.add(run)
        await db.flush()
    run_id = run.id if run is not None else None

    from seelo.worker.tasks_collect import collect_store  # 순환 import 방지

    await jobs.defer(
        db,
        collect_store,
        args={"store_id": store.id, "run_id": run_id},
        links=jobs.JobLinks(store_id=store.id, run_id=run_id),
        queueing_lock=f"collect:{store.id}:{run_id}",
        lock=f"store:{store.id}",
    )
    if old is not None:
        audit.record(
            db,
            actor_id=user.id,
            action="store.change",
            target_type="store",
            target_id=old.id,
            detail={"newStoreId": store.id},
        )
    store_id = store.id
    await db.commit()
    log.info(
        "store_confirmed", store_id=store_id, run_id=run_id, provider=link.provider, changed=old is not None
    )
    return IdentifyConfirmed(store_id=store_id, run_id=run_id, next=f"/runs/{run_id}" if run_id else "/home")
