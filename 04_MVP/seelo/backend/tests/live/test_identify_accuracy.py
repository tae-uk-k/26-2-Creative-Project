"""W-02-3 live: 테스트 가게 20곳 가게 찾기 정확도(11 4장, 07 2.2 [PoC]).

실행: uv run pytest -m live tests/live/test_identify_accuracy.py -s
- 실제 키가 필요하다: GOOGLE_PLACES_API_KEY, KAKAO_REST_API_KEY, NAVER_API_KEY_ID·NAVER_API_KEY.
- 가게 목록: tests/fixtures/links/test_stores.csv
  (열: store_no, name, link, expected_google_id, expected_kakao_id, expect_naver(y/n)). PoC 때 채운다.
- 결과(정확도·시간·비용)는 03_실험/구현시험/W-02-3.md에 남긴다. DB에는 쓰지 않는다.
"""

import csv
import time
from pathlib import Path

import pytest

from seelo.config import get_settings
from seelo.domain.links import pick_supported
from seelo.integrations.real import build_real_clients
from seelo.services import identify_service

pytestmark = pytest.mark.live
STORES = Path(__file__).parents[1] / "fixtures" / "links" / "test_stores.csv"


def _rows() -> list[dict[str, str]]:
    if not STORES.exists():
        return []
    return list(csv.DictReader(STORES.open(encoding="utf-8")))


async def test_identify_accuracy() -> None:
    s = get_settings()
    if not (
        s.google_places_api_key.get_secret_value()
        and s.kakao_rest_api_key.get_secret_value()
        and s.naver_api_key.get_secret_value()
    ):
        pytest.skip("지도 API 키가 없다")
    rows = _rows()
    if not rows:
        pytest.skip("tests/fixtures/links/test_stores.csv가 없다(PoC 때 채움)")
    clients = build_real_clients()
    ok = 0
    for row in rows:
        started = time.perf_counter()
        link = pick_supported(row["link"])
        if link.kind == "short":
            link = await clients.short_links.resolve(link)
        outcome = await identify_service.find_on_base(clients, link, row["name"])
        base = outcome.place or (outcome.candidates or [None])[0]
        others = await identify_service.find_others(clients, base, row["name"]) if base else {}
        found = {base.provider: base, **others} if base else {}
        google = found.get("google")
        kakao = found.get("kakao")
        hit = (
            (not row["expected_google_id"] or (google and google.external_id == row["expected_google_id"]))
            and (not row["expected_kakao_id"] or (kakao and kakao.external_id == row["expected_kakao_id"]))
            and ((row["expect_naver"] == "y") == (found.get("naver") is not None))
        )
        ok += bool(hit)
        print(f"{row['store_no']}\t{'OK' if hit else 'MISS'}\t{time.perf_counter() - started:.1f}s")
    print(f"정확도 {ok}/{len(rows)}")
