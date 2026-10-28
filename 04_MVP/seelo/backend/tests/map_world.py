"""가게 찾기·수집 테스트용 지도 세계 만들기(07 4장 응답 형태 그대로)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

LAT0, LNG0 = 37.5627, 126.9858  # 명동 근처 기준점
LAT_PER_M = 1 / 111_195.08  # haversine 지구 반지름 기준 위도 1m


def north(m: float) -> float:
    return LAT0 + m * LAT_PER_M


def g(
    pid: str,
    name: str,
    lat: float = LAT0,
    lng: float = LNG0,
    *,
    primary: str | None = "korean_restaurant",
    types: list[str] | None = None,
    address: str = "대한민국 서울특별시 중구 명동10길 29",
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": pid,
        "displayName": {"text": name, "languageCode": "ko"},
        "formattedAddress": address,
        "location": {"latitude": lat, "longitude": lng},
        "types": types or ([primary, "restaurant", "food"] if primary else ["point_of_interest"]),
        "googleMapsUri": f"https://maps.google.com/?cid={pid}",
    }
    if primary:
        raw["primaryType"] = primary
    return raw


def k(
    kid: str,
    name: str,
    lat: float = LAT0,
    lng: float = LNG0,
    *,
    code: str = "FD6",
    category: str = "음식점 > 한식",
    road: str = "서울 중구 명동10길 29",
) -> dict[str, Any]:
    return {
        "id": kid,
        "place_name": name,
        "category_name": category,
        "category_group_code": code,
        "category_group_name": "",
        "phone": "02-776-5348",
        "address_name": "서울 중구 명동2가 25-2",
        "road_address_name": road,
        "x": str(lng),
        "y": str(lat),
        "place_url": f"http://place.map.kakao.com/{kid}",
    }


def n(
    name: str,
    lat: float = LAT0,
    lng: float = LNG0,
    *,
    category: str = "음식점>한식",
    road: str = "서울특별시 중구 명동10길 29",
) -> dict[str, Any]:
    return {
        "title": f"<b>{name}</b>",
        "link": "",
        "category": category,
        "description": "",
        "telephone": "",
        "address": "서울특별시 중구 명동2가 25-2",
        "roadAddress": road,
        "mapx": str(round(lng * 1e7)),
        "mapy": str(round(lat * 1e7)),
    }


def g_detail(pid: str, name: str, **extra: Any) -> dict[str, Any]:
    """수집용 Google 상세 응답(g()에 상세 필드를 더함)."""
    raw = g(pid, name)
    raw.update(
        {
            "primaryTypeDisplayName": {"text": "한식당", "languageCode": "ko"},
            "addressComponents": [
                {"longText": "명동2가", "types": ["sublocality_level_2", "sublocality", "political"]},
                {"longText": "중구", "types": ["sublocality_level_1", "sublocality", "political"]},
            ],
            "nationalPhoneNumber": "02-776-5348",
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": d, "hour": 10, "minute": 30},
                        "close": {"day": d, "hour": 21, "minute": 0},
                    }
                    for d in range(7)
                ],
                "weekdayDescriptions": ["월요일: 오전 10:30~오후 9:00"],
            },
            "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
            "takeout": True,
            "reservable": False,
            "editorialSummary": {"text": "칼국수로 유명한 곳", "languageCode": "ko"},
            "photos": [{"name": "p1"}, {"name": "p2"}, {"name": "p3"}],
        }
    )
    raw.update(extra)
    return raw


G_EN = {
    "displayName": {"text": "Myeongdong Kyoja", "languageCode": "en"},
    "addressComponents": [{"longText": "Myeong-dong 2(i)-ga", "types": ["sublocality_level_2"]}],
}


async def seed_store(
    db: AsyncSession,
    *,
    email: str = "owner@seelo.test",
    name: str = "명동교자",
    google_id: str | None = "G1",
    kakao_id: str | None = "K1",
    naver: bool = True,
    with_run: bool = True,
    kind: str = "diagnosis",
) -> tuple[int, int | None]:
    """가게 확정(E1) 직후 상태를 DB에 만든다: 가게 collecting, 지도 출처 3행, 측정 queued."""
    from seelo.models.measurement import MeasurementRun
    from seelo.models.store import Store, StoreSource
    from tests.support import make_user

    user = await make_user(db, email)
    store = Store(
        owner_id=user.id,
        name=name,
        input_url="https://place.map.kakao.com/K1",
        input_provider="kakao",
        category="restaurant",
        status="collecting",
    )
    db.add(store)
    await db.flush()
    rows = [
        ("google", google_id, f"https://maps.google.com/?cid={google_id}" if google_id else None),
        ("kakao", kakao_id, f"http://place.map.kakao.com/{kakao_id}" if kakao_id else None),
        ("naver", None, None),
    ]
    for provider, ext, url in rows:
        found = ext is not None if provider != "naver" else naver
        db.add(
            StoreSource(
                store_id=store.id,
                provider=provider,
                external_id=ext,
                url=url,
                match_status="found" if found else "not_found",
            )
        )
    run_id = None
    if with_run:
        run = MeasurementRun(
            store_id=store.id, kind=kind, is_free=kind == "diagnosis", trigger="initial", status="queued"
        )
        db.add(run)
        await db.flush()
        run_id = run.id
    store_id = store.id
    await db.commit()
    return store_id, run_id


QUESTIONS = [
    ("en", "basic", "Any good Korean restaurants near Myeong-dong?", "명동 근처 괜찮은 한식당 있어?"),
    (
        "en",
        "conditional",
        "Can you recommend Korean restaurants with takeout near Myeong-dong?",
        "포장 되는 곳",
    ),
    ("ko", "basic", "명동 근처 한식당 추천해줘", None),
]


async def seed_google_snapshot(
    db: AsyncSession, store_id: int, run_id: int | None, ko: dict[str, Any]
) -> None:
    """수집이 끝난 상태의 Google 스냅샷(07 6.2 형식)."""
    from datetime import timedelta

    from sqlalchemy import select

    from seelo.models.store import SourceSnapshot, StoreSource
    from seelo.timeutil import now_utc

    source_id = await db.scalar(
        select(StoreSource.id).where(StoreSource.store_id == store_id, StoreSource.provider == "google")
    )
    ko = {k: v for k, v in ko.items() if k != "photos"}
    db.add(
        SourceSnapshot(
            source_id=source_id,
            store_id=store_id,
            run_id=run_id,
            provider="google",
            status="ok",
            payload={"ko": ko, "en": G_EN, "photoCount": 0},
            expires_at=now_utc() + timedelta(days=30),
        )
    )
    await db.commit()


async def seed_measuring(
    db: AsyncSession, *, email: str = "owner@seelo.test", with_questions: bool = True, **kw: Any
) -> tuple[int, int, list[int]]:
    """질문 생성 직전(with_questions=False) 또는 AI 호출 직전 상태: 가게 measuring, 측정 running.

    돌려주는 값: (store_id, run_id, question_ids).
    """
    from sqlalchemy import text

    from seelo.models.measurement import MeasurementRun, Question, QuestionSet

    store_id, run_id = await seed_store(db, email=email, **kw)
    await db.execute(text("UPDATE stores SET status = 'measuring' WHERE id = :i"), {"i": store_id})
    run = await db.get(MeasurementRun, run_id)
    run.status, run.stage = "running", "generating_questions"
    qids: list[int] = []
    if with_questions:
        qset = QuestionSet(
            store_id=store_id, version=1, region_ko="명동", region_en="Myeong-dong", category="restaurant",
            features=["takeout"], generated_by="llm",
        )  # fmt: skip
        db.add(qset)
        await db.flush()
        for i, (lang, intent, q, q_ko) in enumerate(QUESTIONS, 1):
            row = Question(
                question_set_id=qset.id, order_no=i, lang=lang, intent_type=intent, text=q, text_ko=q_ko
            )
            db.add(row)
            await db.flush()
            qids.append(row.id)
        run.question_set_id, run.stage = qset.id, "calling_ai"
    await db.commit()
    return store_id, run_id, qids


async def measure_to_end(db: AsyncSession, run_id: int, *, finalize: bool = True) -> None:
    """runMeasurement → callAi 전부 → 추출 전부 → (finalizeRun). 가짜 LLM(ai 픽스처)이 있어야 한다."""
    from sqlalchemy import select

    from seelo.models.measurement import AiExecution, AiResponse
    from seelo.services import extract_service, finalize_service, measure_service

    await measure_service.run(run_id)
    for ex_id in (await db.scalars(select(AiExecution.id).where(AiExecution.run_id == run_id))).all():
        await measure_service.call_ai(ex_id)
    ids = (
        await db.scalars(
            select(AiResponse.id)
            .join(AiExecution, AiExecution.id == AiResponse.execution_id)
            .where(AiExecution.run_id == run_id)
        )
    ).all()
    for rid in ids:
        await extract_service.extract(rid)
    if finalize:
        await finalize_service.finalize(run_id)
    db.expire_all()


PLAN_SITE = {
    "hours": {
        "days": {
            d: [{"open": "11:00", "close": "21:00"}]
            for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        },
        "breaks": {},
        "notes": None,
    },
    "hours_text": "매일 11:00~21:00",
    "phone": "02-776-0000",
    "menu": [
        {"name": "칼국수", "price": 11000, "description": None},
        {"name": "만두", "price": 10000, "description": None},
    ],
    "intro": "명동 칼국수집",
    "address": "서울 중구 명동10길 29",
}
# (provider, field, category, title_key, priority, evidence)
PLAN_FINDINGS = [
    ("google", "website", "map_missing", "map_missing.website", 1, {}),
    (
        "google",
        "attributes",
        "map_missing",
        "map_missing.attributes",
        2,
        {"missingKeys": ["vegetarian", "card_payment"]},
    ),
    (
        "google",
        "phone",
        "source_mismatch",
        "source_mismatch.phone",
        3,
        {
            "mapValue": "02-776-5348",
            "sources": [{"source": "website", "value": "02-776-0000", "valueStored": True}],
        },
    ),
    (
        "google",
        "menu",
        "condition_missing",
        "condition_missing.budget",
        4,
        {"conditionKey": "budget", "questionIds": []},
    ),
    ("google", "name", "source_mismatch", "source_mismatch.name", 5, {"sources": [{"source": "website"}]}),
]


async def seed_plan_world(
    db: AsyncSession,
    *,
    email: str = "owner@seelo.test",
    findings: list[tuple] | None = None,
    status: str = "connecting",
) -> dict[str, Any]:
    """정비안 직전: 진단 끝난 가게, 기준 측정(완료), 진단 finding, Google·웹사이트 스냅샷, 연결된 신청."""
    from datetime import timedelta

    from sqlalchemy import select, text

    from seelo.models.finding import Finding
    from seelo.models.fix import FixRequest, MapConnection
    from seelo.models.store import SourceSnapshot, Store, StoreSource
    from seelo.timeutil import now_utc

    store_id, run_id = await seed_store(db, email=email)
    await db.execute(text("UPDATE stores SET status = 'diagnosed' WHERE id = :i"), {"i": store_id})
    await db.execute(text("UPDATE measurement_runs SET status = 'completed' WHERE id = :i"), {"i": run_id})
    await db.commit()
    await seed_google_snapshot(db, store_id, run_id, g_detail("G1", "명동교자"))
    src = StoreSource(
        store_id=store_id, provider="website", url="https://demo.example/", match_status="found"
    )
    db.add(src)
    await db.flush()
    db.add(
        SourceSnapshot(
            source_id=src.id,
            store_id=store_id,
            run_id=run_id,
            provider="website",
            status="ok",
            payload={"url": "https://demo.example/", "extract": PLAN_SITE},
            expires_at=now_utc() + timedelta(days=30),
        )
    )
    for provider, field_, category, key, priority, evidence in (
        findings if findings is not None else PLAN_FINDINGS
    ):
        db.add(
            Finding(
                run_id=run_id,
                stage="diagnosis",
                category=category,
                title_key=key,
                provider=provider,
                field=field_,
                priority=priority,
                evidence=evidence,
            )
        )
    owner_id = await db.scalar(select(Store.owner_id).where(Store.id == store_id))
    req = FixRequest(user_id=owner_id, store_id=store_id, status=status, base_run_id=run_id)
    db.add(req)
    await db.flush()
    conns = {}
    for p in ("google", "kakao"):
        c = MapConnection(fix_request_id=req.id, provider=p, status="connected", connected_at=now_utc())
        db.add(c)
        await db.flush()
        conns[p] = c.id
    out = {"store_id": store_id, "run_id": run_id, "request_id": req.id, "connections": conns}
    await db.commit()
    return out


async def new_plan(db: AsyncSession, request_id: int, provider: str, run_id: int) -> int:
    from seelo.models.fix import FixPlan

    plan = FixPlan(
        fix_request_id=request_id, provider=provider, version=1, status="generating", base_run_id=run_id
    )
    db.add(plan)
    await db.flush()
    plan_id = plan.id
    await db.commit()
    return plan_id


async def approved_plan(
    db: AsyncSession,
    w: dict[str, Any],
    provider: str,
    items: dict[str, Any],
    *,
    status: str = "queued",
    method: str = "browser",
) -> dict[str, Any]:
    """승인된 정비안과 칸마다 fix_logs(자동 정비 전 queued). items: 칸 → 승인 값. 신청은 fixing으로."""
    from sqlalchemy import text

    from seelo.models.fix import FixLog, FixPlan, FixPlanItem
    from seelo.timeutil import now_utc

    await db.execute(text("UPDATE fix_requests SET status = 'fixing' WHERE id = :i"), {"i": w["request_id"]})
    plan = FixPlan(
        fix_request_id=w["request_id"],
        provider=provider,
        version=1,
        status="approved",
        base_run_id=w["run_id"],
        approved_at=now_utc(),
    )
    db.add(plan)
    await db.flush()
    logs = {}
    for n, (field, value) in enumerate(items.items(), 1):
        item = FixPlanItem(
            fix_plan_id=plan.id, order_no=n, field=field, proposed_value=value, approved_value=value
        )
        db.add(item)
        await db.flush()
        lg = FixLog(
            fix_plan_item_id=item.id,
            fix_request_id=w["request_id"],
            provider=provider,
            field=field,
            method=method,
            applied_value=value,
            status=status,
        )
        db.add(lg)
        await db.flush()
        logs[field] = lg.id
    await db.commit()
    return {"plan_id": plan.id, "logs": logs}
