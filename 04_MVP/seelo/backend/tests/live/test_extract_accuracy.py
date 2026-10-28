"""W-05 live: 실제 답변 100개를 사람 정답과 비교(12 7단계 완료 조건).

실행: uv run pytest -m live tests/live/test_extract_accuracy.py -s
- 실제 키: OPENAI_API_KEY·OPENAI_CHEAP_MODEL.
- 정답 파일: tests/fixtures/extract/gold.jsonl(한 줄에 답변 하나, 사람이 채움). 형식:
  {"annotated_text": "...[1]...", "sources": [{"n": 1, "url": "...", "domain": "..."}],
   "target_names": ["명동교자", "Myeongdong Kyoja"],   # 사장님 입력·Google 이름(추출 프롬프트에 들어감)
   "gold": ["명동교자", "을지면옥"],                    # 답변이 추천한 가게, 처음 나온 순서
   "gold_target": true}                                 # 우리 가게가 등장했는가
- 기준: 이름·순서 = 정규화 이름 목록이 정답과 순서까지 같은 답변 비율 ≥ 90%,
  우리 가게 판정 = 등장 여부가 정답과 같은 비율 ≥ 95%. 결과는 03_실험/구현시험/에 남긴다.
"""

import json
import time
from pathlib import Path

import pytest

from seelo.config import get_settings
from seelo.domain.extraction import extraction_prompt, postprocess
from seelo.domain.normalize import normalize_name
from seelo.integrations.llm import cost_usd
from seelo.integrations.real import build_real_clients
from seelo.schemas.llm import ExtractionOut

pytestmark = pytest.mark.live
GOLD = Path(__file__).parents[1] / "fixtures" / "extract" / "gold.jsonl"


async def test_extraction_matches_human_labels() -> None:
    s = get_settings()
    if not (s.openai_api_key.get_secret_value() and s.openai_cheap_model):
        pytest.skip("OpenAI 키·OPENAI_CHEAP_MODEL이 없다")
    if not GOLD.exists():
        pytest.skip("tests/fixtures/extract/gold.jsonl이 없다(실제 답변 100개에 사람이 정답을 붙임)")
    items = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    client = build_real_clients().openai
    order_ok = target_ok = 0
    cost = 0.0
    misses: list[str] = []
    started = time.perf_counter()
    for i, item in enumerate(items):
        prompt = extraction_prompt(item["annotated_text"], item["sources"], item["target_names"])
        res = await client.structured(prompt, ExtractionOut, model=s.openai_cheap_model)
        cost += cost_usd(
            "openai", res.model_id, input_tokens=res.input_tokens, output_tokens=res.output_tokens
        )
        got = [r.normalized_name for r in postprocess(res.parsed, item["sources"])]  # type: ignore[arg-type]
        want = [normalize_name(n) for n in item["gold"]]
        names = {normalize_name(n) for n in item["target_names"]}
        if got == want:
            order_ok += 1
        else:
            misses.append(f"#{i}: got={got} want={want}")
        if bool(names & set(got)) == item["gold_target"]:
            target_ok += 1
    n = len(items)
    took = time.perf_counter() - started
    print(f"answers={n} order_ok={order_ok / n:.1%} target_ok={target_ok / n:.1%}")
    print(f"cost=${cost:.4f} took={took:.0f}s")
    for m in misses[:20]:
        print("  ", m)
    assert order_ok / n >= 0.90
    assert target_ok / n >= 0.95
