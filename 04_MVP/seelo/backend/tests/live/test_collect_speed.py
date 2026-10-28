"""W-03 live: 테스트 가게 20곳 수집 30초 안(12 5단계 완료 조건, 07 6.1).

실행: uv run pytest -m live tests/live/test_collect_speed.py -s
- 실제 키: GOOGLE_PLACES_API_KEY(그리고 웹사이트 정리에 OPENAI_API_KEY·OPENAI_CHEAP_MODEL).
- 가게 목록: tests/fixtures/links/test_stores.csv의 expected_google_id 열(test_identify_accuracy와 같은 파일).
- DB 없이 수집 핵심 호출(Google 상세 ko·en → 웹사이트 robots·첫 페이지)만 잰다.
- 결과는 03_실험/구현시험/에 남긴다.
"""

import csv
import time
from pathlib import Path

import pytest

from seelo.config import get_settings
from seelo.integrations.real import build_real_clients
from seelo.services.collect_service import GOOGLE_DETAIL_FIELDS, GOOGLE_EN_FIELDS

pytestmark = pytest.mark.live
STORES = Path(__file__).parents[1] / "fixtures" / "links" / "test_stores.csv"
TARGET_S = 30.0


async def test_collect_under_30s() -> None:
    if not get_settings().google_places_api_key.get_secret_value():
        pytest.skip("GOOGLE_PLACES_API_KEY가 없다")
    if not STORES.exists():
        pytest.skip("tests/fixtures/links/test_stores.csv가 없다(PoC 때 채움)")
    rows = [r for r in csv.DictReader(STORES.open(encoding="utf-8")) if r.get("expected_google_id")]
    clients = build_real_clients()
    slow = []
    for row in rows:
        started = time.perf_counter()
        ko = await clients.places.details(
            row["expected_google_id"], fields=GOOGLE_DETAIL_FIELDS, language="ko"
        )
        await clients.places.details(row["expected_google_id"], fields=GOOGLE_EN_FIELDS, language="en")
        site = (ko or {}).get("websiteUri")
        if site and (await clients.website.robots_allows(site)).allowed:
            try:
                await clients.website.fetch(site)
            except Exception as e:  # 실패도 시간에 포함해 기록만
                print(row["store_no"], "website", type(e).__name__)
        took = time.perf_counter() - started
        print(f"{row['store_no']}\t{took:.1f}s\twebsite={'y' if site else 'n'}")
        if took > TARGET_S:
            slow.append(row["store_no"])
    assert not slow, f"30초 넘은 가게: {slow}"
