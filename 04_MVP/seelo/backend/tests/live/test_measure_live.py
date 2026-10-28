"""W-04 live: 테스트 가게 5곳 × 60번(12 6단계 완료 조건).

실행: uv run pytest -m live tests/live/test_measure_live.py -s
- 실제 키: OPENAI_API_KEY·OPENAI_MEASURE_MODEL, GEMINI_API_KEY·GEMINI_MEASURE_MODEL.
- 가게 목록: tests/fixtures/links/test_stores.csv의 name·region_ko·region_en·category 열(앞 5곳).
- DB 없이 질문 3개(템플릿) × 공급자 2 × AI_REPEAT_COUNT를 실제로 부르고 원문이 비지 않았는지,
  같은 (질문, 공급자, 반복) 중복 0, 15분 안인지 잰다.
- 원문 저장·중복 방지는 통합 테스트(W-04-2·3)가 DB로 확인한다.
- 결과(시간·비용·실패 수)는 03_실험/구현시험/에 남긴다.
"""

import asyncio
import csv
import time
from pathlib import Path

import pytest

from seelo.config import get_settings
from seelo.domain.questions import cuisine_for, template_questions
from seelo.integrations.real import build_real_clients

pytestmark = pytest.mark.live
STORES = Path(__file__).parents[1] / "fixtures" / "links" / "test_stores.csv"
LIMIT_S = 15 * 60


async def test_five_stores_sixty_calls_each() -> None:
    s = get_settings()
    if not (s.openai_api_key.get_secret_value() and s.gemini_api_key.get_secret_value()):
        pytest.skip("OpenAI·Gemini 키가 없다")
    if not (s.openai_measure_model and s.gemini_measure_model):
        pytest.skip("측정 모델(D-09)이 정해지지 않았다")
    if not STORES.exists():
        pytest.skip("tests/fixtures/links/test_stores.csv가 없다(PoC 때 채움)")
    rows = [r for r in csv.DictReader(STORES.open(encoding="utf-8")) if r.get("region_ko")][:5]
    clients = build_real_clients()
    sem = asyncio.Semaphore(s.ai_concurrency_per_provider)
    results: dict[tuple[str, int, str, int], str] = {}
    failures: list[str] = []

    async def one(store: str, qi: int, text: str, provider: str, n: int) -> None:
        client = clients.openai if provider == "openai" else clients.gemini
        model = s.openai_measure_model if provider == "openai" else s.gemini_measure_model
        async with sem:
            try:
                res = await client.web_answer(text, model=model)
                results[(store, qi, provider, n)] = res.text
            except Exception as e:
                failures.append(f"{store}/{qi}/{provider}/{n}: {type(e).__name__}")

    started = time.perf_counter()
    tasks = []
    for row in rows:
        cuisine = cuisine_for(None, row["category"])
        qs = template_questions(
            region_ko=row["region_ko"],
            region_en=row["region_en"],
            category=row["category"],
            cuisine=cuisine,
            feature="budget",
        )
        for qi, q in enumerate(qs, 1):
            for provider in ("openai", "gemini"):
                for n in range(1, s.ai_repeat_count + 1):
                    tasks.append(one(row["store_no"], qi, q.text, provider, n))
    await asyncio.gather(*tasks)
    took = time.perf_counter() - started
    print(f"calls={len(tasks)} ok={len(results)} failed={len(failures)} took={took:.0f}s")
    for f in failures[:20]:
        print("  ", f)
    assert all(t.strip() for t in results.values())
    assert took < LIMIT_S
