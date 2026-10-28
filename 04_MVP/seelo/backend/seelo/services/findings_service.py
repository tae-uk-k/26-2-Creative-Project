"""고쳐야 할 점 판정(08 6장): 주변 가게 사실 조회(6.6), AI 주장 비교(6.4 LLM), 규칙 적용.

- 외부 호출(Places·LLM)이 있으므로 finalizeRun은 저장 트랜잭션을 열기 **전에** 이것을 부른다.
- 주변 가게 사실은 저장하지 않는다. 그 Places 비용은 측정 cost_usd에 넣지 않고 로그로 남긴다.
- AI 비교 LLM 입력은 AI 주장·공식 웹사이트 값·Google 지도 값뿐이다(카카오·네이버 값 없음).
"""

import asyncio
from typing import Any

import structlog

from seelo.config import get_settings
from seelo.domain import findings_rules as rules
from seelo.domain.findings_rules import ClaimCheck, FindingDraft, FindingInputs
from seelo.integrations import Clients
from seelo.integrations.http import ExternalApiError
from seelo.integrations.llm import LlmError, cost_usd
from seelo.schemas.llm import ClaimChecksOut

log = structlog.get_logger()

FACT_FIELDS = ",".join(
    [
        "regularOpeningHours",
        "websiteUri",
        "nationalPhoneNumber",
        "priceLevel",
        "servesVegetarianFood",
        "paymentOptions",
        "reservable",
        "takeout",
        "outdoorSeating",
        "servesBeer",
        "servesWine",
        "servesCocktails",
        "goodForChildren",
        "goodForGroups",
    ]
)
LOOKUP_TIMEOUT_S = 5.0
LOOKUP_RADIUS_M = 2000.0
COMPARE_TIMEOUT_S = 60.0
COMPARE_PROMPT = (
    "Decide whether the claim states the same fact as the reference. Ignore formatting differences.\n"
    "For each item answer claim_matches_truth (claim vs reference) and claim_matches_map "
    "(claim vs map value, null when there is no map value). Use the item number as index.\n\n"
)


async def lookup_competitor_facts(
    clients: Clients,
    competitors: list[tuple[str, str]],
    *,
    region: str | None,
    coords: tuple[float, float] | None,
) -> dict[str, dict[str, Any]] | None:
    """주변 가게마다 Text Search(이름 + 지역, 반경 2km, 1건) → Place Details. 각 5초, 동시에.

    돌려주는 값: {정규화 이름: 상세(못 찾으면 {})}. 조회할 수 없거나 모두 실패하면 None(근거 부족).
    """
    if not competitors or coords is None or not get_settings().competitor_facts_enabled:
        return None

    async def one(norm: str, display: str) -> tuple[str, dict[str, Any]]:
        query = f"{display} {region}" if region else display
        async with asyncio.timeout(LOOKUP_TIMEOUT_S):
            found = await clients.places.search_text(
                query, lat=coords[0], lng=coords[1], radius_m=LOOKUP_RADIUS_M, page_size=1
            )
        if not found or not found[0].external_id:
            return norm, {}
        async with asyncio.timeout(LOOKUP_TIMEOUT_S):
            detail = await clients.places.details(found[0].external_id, fields=FACT_FIELDS, language="ko")
        return norm, detail or {}

    results = await asyncio.gather(*(one(n, d) for n, d in competitors), return_exceptions=True)
    facts: dict[str, dict[str, Any]] = {}
    failed = 0
    for r in results:
        if isinstance(r, Exception):  # 실패해도 계속(시간 초과·API 오류 등)
            failed += 1
            if not isinstance(r, (TimeoutError, ExternalApiError)):
                log.warning("competitor_facts_error", error_type=type(r).__name__)
        elif isinstance(r, BaseException):
            raise r
        else:
            facts[r[0]] = r[1]
    log.info(
        "competitor_facts",
        competitors=len(competitors),
        failed=failed,
        found=sum(bool(f) for f in facts.values()),
        places_calls=len(competitors) + sum(bool(f) for f in facts.values()),  # 비용은 로그로만
    )
    return None if failed == len(competitors) else facts


def compare_prompt(checks: list[ClaimCheck]) -> str:
    items = []
    for i, c in enumerate(checks, 1):
        items.append(
            f"[{i}] field: {c.claim_field}\nclaim: {c.claim}\nreference: {c.truth}\n"
            f"map value: {c.map_value if c.map_value else '(none)'}"
        )
    return COMPARE_PROMPT + "\n\n".join(items)


async def compare_claims(
    clients: Clients, checks: list[ClaimCheck]
) -> tuple[list[tuple[bool, bool | None]] | None, float]:
    """(주장마다 (claimMatchesTruth, claimMatchesMap), 비용). 실패하면 (None, 0) — D5를 판정하지 않는다.

    답에 빠진 번호는 "다르지 않음"(맞음)으로 본다(잘못된 판정 방지).
    """
    model = get_settings().openai_cheap_model
    try:
        async with asyncio.timeout(COMPARE_TIMEOUT_S):
            res = await clients.openai.structured(compare_prompt(checks), ClaimChecksOut, model=model)
    except (TimeoutError, LlmError) as e:
        log.warning("claim_compare_failed", reason=e.reason if isinstance(e, LlmError) else "timeout")
        return None, 0.0
    out: ClaimChecksOut = res.parsed  # type: ignore[assignment]
    by_index = {r.index: (r.claim_matches_truth, r.claim_matches_map) for r in out.results}
    results = [by_index.get(i, (True, None)) for i in range(1, len(checks) + 1)]
    cost = cost_usd("openai", res.model_id, input_tokens=res.input_tokens, output_tokens=res.output_tokens)
    return results, cost


async def judge_for_run(clients: Clients, inp: FindingInputs) -> tuple[list[FindingDraft], float]:
    """진단 단계 고쳐야 할 점(D1~D5)과 순서. (finding 초안, AI 비교 비용)."""
    drafts = rules.judge_diagnosis(inp)
    cost = 0.0
    checks = rules.claim_checks(inp)
    if checks:
        results, cost = await compare_claims(clients, checks)
        if results is not None:
            drafts += rules.ai_wrong_drafts(checks, results)
    return rules.prioritize(drafts, inp), cost
