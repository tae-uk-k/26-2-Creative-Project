"""쇼핑몰 AI 노출 진단 판정 규칙. 2026-11-24 쇼핑몰 전후 비교 실험의 판정 기준을 따른다.

- 자연 발견: 정상 응답에서 대상 상품이 정확히 식별됨(정확한 상품명 또는 대상 상품 URL).
  원료 일반 설명·브랜드만의 언급은 발견이 아니다.
- 추천: 상위 3개 소개 목록 안에 대상 상품이 있음. 목록 구조가 없으면 순위를 비워 두고 검토 필요로 표시한다.
- 상품 링크 인용: 답변 본문 또는 검색 출처에 대상 상품 URL이 있음.
- 호출 실패는 무효다. 노출 0으로 세지 않고 분모에서 뺀다. 1회만 다시 실행하고 최초 실패도 보관한다.
- 비교는 같은 질문 세트·같은 측정 조건(공급자·모델·도구 옵션·반복 수)끼리만 한다.
"""

import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

from seelo.errors import AppError

# 실험 고정질문.json의 공통 문구. 질문 세트에서 따로 정하지 않으면 이 문구를 쓴다.
DEFAULT_SUFFIX = (
    "웹에서 제품을 찾아 3개까지 소개해줘. 제품명, 판매처, 근거 링크와 선택 이유를 알려줘. "
    "확인되지 않은 정보는 추정하지 마."
)
URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
ITEM = re.compile(r"^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*(?:\d{1,2}[.)]|[-*•])\s+")
QUERY_ID = re.compile(r"[A-Za-z0-9_-]{1,20}")


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(str(value).split())).casefold()


def url_key(value: str) -> str | None:
    """같은 상품 주소 판정용 키. 호스트의 www.·m.과 끝 슬래시, 추적용 쿼리를 무시한다."""
    try:
        parts = urlsplit(value.strip().rstrip(".,;"))
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    path = parts.path.rstrip("/")
    number = parse_qs(parts.query).get("product_no")
    return f"{host}{path}" + (f"?product_no={number[0]}" if number else "")


def check_set(queries: list[dict], targets: dict) -> None:
    names = [normalize(n) for n in targets.get("names", []) if str(n).strip()]
    keys = {k for k in (url_key(u) for u in targets.get("urls", [])) if k}
    if not names and not keys:
        raise AppError("COMMERCE_INVALID", {"reason": "measure_target_required"})
    seen = set()
    for query in queries:
        qid, text = str(query.get("id", "")), str(query.get("question", ""))
        if not QUERY_ID.fullmatch(qid) or qid in seen or not (5 <= len(text.strip()) <= 500):
            raise AppError("COMMERCE_INVALID", {"reason": "measure_query_invalid", "queryId": qid})
        seen.add(qid)
        lowered = normalize(text)
        # 자연 발견 질문에는 대상 상품명·상품 URL을 넣지 않는다(정확한 상품명 질문은 별도 진단이다).
        if any(name in lowered for name in names) or any(url_key(u) in keys for u in URL.findall(text)):
            raise AppError("COMMERCE_INVALID", {"reason": "query_contains_target", "queryId": qid})


def list_items(text: str) -> list[str]:
    """번호·글머리표 목록을 항목별로 나눈다. 다음 항목 전까지의 줄은 같은 항목으로 본다."""
    items: list[str] = []
    for line in text.splitlines():
        if ITEM.match(line):
            items.append(line)
        elif items and line.strip():
            items[-1] += "\n" + line
    return items


def evaluate(text: str, sources: list[dict], targets: dict) -> dict:
    names = [normalize(n) for n in targets.get("names", []) if str(n).strip()]
    keys = {k for k in (url_key(u) for u in targets.get("urls", [])) if k}
    cited = [*URL.findall(text), *[str(s.get("url", "")) for s in sources if s.get("url")]]
    url_hits = list(dict.fromkeys(u for u in cited if url_key(u) in keys))
    body = normalize(text)
    name_hit = any(name in body for name in names)
    identified = name_hit or bool(url_hits)

    def mentions(item: str) -> bool:
        lowered = normalize(item)
        return any(name in lowered for name in names) or any(url_key(u) in keys for u in URL.findall(item))

    items = list_items(text)
    rank = next((index + 1 for index, item in enumerate(items) if mentions(item)), None)
    return {
        "identified": identified,
        "recommended": rank is not None and rank <= 3,
        "rank": rank,
        "target_url_cited": bool(url_hits),
        "evaluation": {
            "method": "exact_name_url_v1",
            "nameHit": name_hit,
            "urlHits": url_hits[:5],
            "listItems": len(items),
            # 대상은 보이지만 목록 순위를 확정하지 못했다. 사람이 원문으로 확인한다.
            "needsReview": identified and rank is None,
        },
    }


def summarize(queries: list[dict], repeats: int, answers: list[dict]) -> dict:
    """질문별·전체 집계. 최종 판정은 질문·반복마다 정상 응답 1개만 쓴다(실험 규칙)."""
    final: dict[tuple[str, int], dict] = {}
    invalid: dict[tuple[str, int], int] = {}
    for answer in sorted(answers, key=lambda a: a["attempt"]):
        key = (answer["query_id"], answer["repeat"])
        if answer["status"] == "ok":
            final.setdefault(key, answer)
        else:
            invalid[key] = invalid.get(key, 0) + 1
    rows, totals = [], {"planned": 0, "valid": 0, "missing": 0, "identified": 0, "recommended": 0, "cited": 0}
    for query in queries:
        row = {"queryId": query["id"], "family": query.get("family", "general"), "planned": repeats}
        ok = [final[(query["id"], r)] for r in range(1, repeats + 1) if (query["id"], r) in final]
        row.update(
            {
                "valid": len(ok),
                # 정상 응답을 얻지 못한 반복. 노출 0이 아니라 무효로 남긴다.
                "missing": repeats - len(ok),
                "failedAttempts": sum(invalid.get((query["id"], r), 0) for r in range(1, repeats + 1)),
                "identified": sum(1 for a in ok if a["identified"]),
                "recommended": sum(1 for a in ok if a["recommended"]),
                "cited": sum(1 for a in ok if a["target_url_cited"]),
            }
        )
        rows.append(row)
        for key in ("valid", "missing", "identified", "recommended", "cited"):
            totals[key] += row[key]
        totals["planned"] += repeats

    def rate(count: int) -> float | None:
        return round(count / totals["valid"], 4) if totals["valid"] else None

    totals["rates"] = {
        "identified": rate(totals["identified"]),
        "recommended": rate(totals["recommended"]),
        "cited": rate(totals["cited"]),
    }
    return {"queries": rows, "totals": totals}


def comparable(before: dict, after: dict) -> None:
    keys = ("provider", "model", "toolOptions", "repeats", "suffixHash")
    if before["setId"] != after["setId"]:
        raise AppError("COMMERCE_INVALID", {"reason": "measure_set_mismatch"})
    diff = [k for k in keys if before["condition"].get(k) != after["condition"].get(k)]
    if diff:
        raise AppError("COMMERCE_INVALID", {"reason": "measure_condition_mismatch", "fields": diff})
