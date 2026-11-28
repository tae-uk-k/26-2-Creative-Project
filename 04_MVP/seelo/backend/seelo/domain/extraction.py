"""추천 추출 프롬프트와 후처리(08 3.2·3.3). IO 없음.

- 프롬프트에 넣는 우리 가게 이름은 사장님 입력 이름과 Google 이름(ko·en)만. 카카오·네이버 이름은 넣지 않는다.
- 후처리: 빈 이름 삭제 → order로 정렬해 rank 1부터 → 같은 정규화 이름은 첫 번째만 → 출처 번호를 주소로.
"""

from dataclasses import dataclass, field
from typing import Any

from seelo.domain.attributes import ATTRIBUTES
from seelo.domain.normalize import normalize_name
from seelo.schemas.llm import ExtractionOut

ANSWER_START = "Answer:\n<<<\n"
ANSWER_END = "\n>>>"


def extraction_prompt(annotated_text: str, sources: list[dict[str, Any]], target_names: list[str]) -> str:
    reasons = "; ".join(f"{a.key} ({a.en})" for a in ATTRIBUTES.values())
    targets = ", ".join(dict.fromkeys(n for n in target_names if n)) or "(none)"
    source_lines = "\n".join(f"[{s['n']}] {s.get('domain') or 'unknown'}" for s in sources) or "(none)"
    return (
        "You read an AI assistant's answer about places to eat or drink.\n"
        "1) List every specific, named business the answer recommends, in the order they first appear.\n"
        "   Do not list areas, streets, dishes, or chains mentioned only in passing.\n"
        "   For each, give the citation numbers [n] attached to sentences about it,\n"
        f"   and which of these reasons the answer gives for it: {reasons}.\n"
        f"2) If the answer talks about any of these target places: {targets},\n"
        "   list its factual claims about opening hours, location, price, or phone, copied from the answer.\n"
        "If no specific businesses are recommended, return empty lists.\n\n"
        f"Sources:\n{source_lines}\n\n"
        f"{ANSWER_START}{annotated_text}{ANSWER_END}"
    )


@dataclass
class RecRow:
    """recommendations 행 하나(is_target은 마무리에서 정한다)."""

    name: str
    normalized_name: str
    rank: int
    source_urls: list[dict[str, str]] = field(default_factory=list)  # [{url, domain}]
    mentioned_attributes: list[str] = field(default_factory=list)


def postprocess(out: ExtractionOut, sources: list[dict[str, Any]]) -> list[RecRow]:
    """3.3 1~3번. sources는 ai_responses.source_urls([{n, url, title, domain}])."""
    by_n = {s["n"]: s for s in sources}
    items = [
        (r.order, i, r)
        for i, r in enumerate(out.recommendations)
        if r.name.strip() and normalize_name(r.name)
    ]
    rows: list[RecRow] = []
    seen: set[str] = set()
    for _, _, r in sorted(items, key=lambda t: (t[0], t[1])):
        norm = normalize_name(r.name)
        if norm in seen:
            continue
        seen.add(norm)
        urls = [
            {"url": by_n[n]["url"], "domain": by_n[n].get("domain") or "unknown"}
            for n in dict.fromkeys(r.source_numbers)
            if n in by_n
        ]
        rows.append(
            RecRow(
                name=r.name.strip(),
                normalized_name=norm,
                rank=len(rows) + 1,
                source_urls=urls,
                mentioned_attributes=list(dict.fromkeys(r.mentioned_attributes)),
            )
        )
    return rows
