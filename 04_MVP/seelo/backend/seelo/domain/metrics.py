"""측정 지표(08 2.4·5장, 14 2.6): 실패율, 등장률·평균 순서, 주변 가게 5곳, 출처. IO 없음.

- 성공한 답변 S(p) = 공급자 p의 추출 성공 응답. 추출 실패 응답은 분모에서 뺀다(실패 실행은 아예 없음).
- 등장: 응답의 추천 중 그 대상에 해당하는 것이 있음. 순위는 해당 추천들의 최소 rank.
- 출처 도메인 "unknown"(Gemini에서 원래 사이트를 알 수 없음)은 출처 지표에 넣지 않는다.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from seelo.domain.states import MetricName, SubjectType

FAILURE_RATE_LIMIT = 0.30
PROVIDERS = ("openai", "gemini")
COMPETITOR_LIMIT = 5
SOURCE_TOP = 20
UNKNOWN_DOMAIN = "unknown"


def failure_rate(failed: int, total: int) -> float:
    return failed / total if total else 1.0


def is_run_failed(failed: int, total: int) -> bool:
    """실패율이 30%를 넘으면 실패(정확히 30%는 통과). 실행이 0개면 실패."""
    return total == 0 or failed * 100 > total * 30  # 부동소수 오차 없이 비교


@dataclass
class RecView:
    normalized_name: str
    name: str
    rank: int
    is_target: bool
    source_domains: list[str]
    mentioned_attributes: list[str]


@dataclass
class ResponseView:
    response_id: int
    provider: str  # openai|gemini
    question_id: int
    extraction_ok: bool
    recs: list[RecView]
    source_domains: list[str]
    source_urls: list[str] = field(default_factory=list)  # 응답 전체 출처(중복 제거)


@dataclass
class MetricRow:
    provider: str
    question_id: int | None
    subject_type: str
    subject_name: str
    metric_name: str
    value: float | None
    denominator: int | None
    rank_order: int | None = None
    display_name: str | None = None


@dataclass
class RunMetrics:
    rows: list[MetricRow]
    competitors: list[str]  # 정규화 이름, 순서대로
    failure_rate: float


def _four(
    provider: str,
    question_id: int | None,
    subject_type: str,
    subject_name: str,
    responses: list[ResponseView],
    match: Callable[[RecView], bool],
    *,
    rank_order: int | None = None,
    display_name: str | None = None,
) -> list[MetricRow]:
    """success_count·appearance_count·appearance_rate·avg_rank(5.2)."""
    ranks = [min(hits) for r in responses if (hits := [x.rank for x in r.recs if match(x)])]
    n, k = len(responses), len(ranks)

    def row(name: str, value: float | None, denominator: int | None) -> MetricRow:
        return MetricRow(
            provider,
            question_id,
            subject_type,
            subject_name,
            name,
            value,
            denominator,
            rank_order,
            display_name,
        )

    return [
        row(MetricName.SUCCESS_COUNT, n, None),
        row(MetricName.APPEARANCE_COUNT, k, n),
        row(MetricName.APPEARANCE_RATE, k / n if n else None, n),
        row(MetricName.AVG_RANK, sum(ranks) / k if k else None, k),
    ]


def _is_target(x: RecView) -> bool:
    return x.is_target


def competitors(responses: Sequence[ResponseView]) -> list[tuple[str, str]]:
    """주변 가게 5곳(5.4): [(정규화 이름, 화면 이름)]. 두 공급자의 성공 응답에서 우리 가게가 아닌 추천."""
    count: Counter[str] = Counter()
    ranks: dict[str, list[int]] = defaultdict(list)
    names: dict[str, Counter[str]] = defaultdict(Counter)
    first: dict[tuple[str, str], int] = {}
    for r in sorted((r for r in responses if r.extraction_ok), key=lambda r: r.response_id):
        best: dict[str, int] = {}
        for x in sorted(r.recs, key=lambda x: x.rank):
            if x.is_target:
                continue
            names[x.normalized_name][x.name] += 1
            first.setdefault((x.normalized_name, x.name), len(first))
            best[x.normalized_name] = min(best.get(x.normalized_name, x.rank), x.rank)
        for norm, rank in best.items():  # 응답당 1번
            count[norm] += 1
            ranks[norm].append(rank)
    top = sorted(count, key=lambda nn: (-count[nn], sum(ranks[nn]) / len(ranks[nn]), nn))[:COMPETITOR_LIMIT]
    return [(nn, max(names[nn].items(), key=lambda kv: (kv[1], -first[(nn, kv[0])]))[0]) for nn in top]


def _source_rows(provider: str, ok: list[ResponseView]) -> list[MetricRow]:
    cite: Counter[str] = Counter()
    target_cite: Counter[str] = Counter()
    appeared = 0
    for r in ok:
        cite.update(set(r.source_domains) - {UNKNOWN_DOMAIN})
        hits = [x for x in r.recs if x.is_target]
        if hits:
            appeared += 1
            target_cite.update({d for x in hits for d in x.source_domains} - {UNKNOWN_DOMAIN})
    top = sorted(cite, key=lambda d: (-cite[d], d))[:SOURCE_TOP]
    keep = top + sorted(d for d in target_cite if d not in top)
    rows: list[MetricRow] = []
    for d in keep:
        rows.append(
            MetricRow(provider, None, SubjectType.SOURCE, d, MetricName.CITATION_COUNT, cite[d], len(ok))
        )
        rows.append(
            MetricRow(
                provider,
                None,
                SubjectType.SOURCE,
                d,
                MetricName.TARGET_CITATION_COUNT,
                target_cite[d],
                appeared,
            )
        )
    return rows


def compute_run_metrics(
    responses: list[ResponseView],
    *,
    question_ids: list[int],
    failed: int,
    total: int,
    providers: Sequence[str] = PROVIDERS,
) -> RunMetrics:
    """5.3의 저장 행 전부. 공급자마다 우리 가게(전체·질문별), 주변 가게 5곳, 출처."""
    rows: list[MetricRow] = []
    comps = competitors(responses)
    for p in providers:
        ok = [r for r in responses if r.provider == p and r.extraction_ok]
        for q in [None, *question_ids]:
            sub = ok if q is None else [r for r in ok if r.question_id == q]
            rows += _four(p, q, SubjectType.TARGET, "target", sub, _is_target)
        for order, (norm, display) in enumerate(comps, 1):

            def match(x: RecView, norm: str = norm) -> bool:
                return not x.is_target and x.normalized_name == norm

            rows += _four(
                p, None, SubjectType.COMPETITOR, norm, ok, match, rank_order=order, display_name=display
            )
        rows += _source_rows(p, ok)
    return RunMetrics(rows=rows, competitors=[c for c, _ in comps], failure_rate=failure_rate(failed, total))


def _overall(rows: list[MetricRow], subject_type: str, subject_name: str) -> tuple[int, float]:
    """두 공급자 합산 (등장 수, 평균 순위). 등장 0이면 평균 순위는 무한대(맨 뒤)."""
    count, rank_sum = 0, 0.0
    by_provider: dict[str, dict[str, float | None]] = defaultdict(dict)
    for r in rows:
        if r.subject_type == subject_type and r.subject_name == subject_name and r.question_id is None:
            by_provider[r.provider][r.metric_name] = r.value
    for vals in by_provider.values():
        k = int(vals.get(MetricName.APPEARANCE_COUNT) or 0)
        avg = vals.get(MetricName.AVG_RANK)
        if k and avg is not None:
            count += k
            rank_sum += float(avg) * k
    return count, (rank_sum / count if count else math.inf)


def competitor_position(rows: list[MetricRow]) -> tuple[int, int]:
    """주변 가게와 비교한 위치(5.5): (우리 가게 순서, 전체 수). 완전히 같으면 우리 가게를 앞에 둔다."""
    comps = sorted(
        {(r.rank_order or 0, r.subject_name) for r in rows if r.subject_type == SubjectType.COMPETITOR}
    )
    subjects = [(SubjectType.TARGET, "target")] + [(SubjectType.COMPETITOR, name) for _, name in comps]
    keyed = []
    for st, name in subjects:
        count, avg = _overall(rows, st, name)
        keyed.append(((-count, avg), st))
    order = sorted(
        range(len(keyed)), key=lambda i: keyed[i][0]
    )  # 안정 정렬: 같으면 원래 순서(우리 가게 먼저)
    return order.index(0) + 1, len(subjects)


def _sum_by_domain(rows: list[MetricRow], metric: str) -> Counter[str]:
    total: Counter[str] = Counter()
    for r in rows:
        if r.subject_type == SubjectType.SOURCE and r.metric_name == metric and r.value:
            total[r.subject_name] += int(r.value)
    return total


def top_sources(rows: list[MetricRow], limit: int = 5) -> list[tuple[str, int]]:
    """S11 sources.top(5.6): 두 공급자 citation_count 합 내림차순(같으면 도메인 이름순)."""
    total = _sum_by_domain(rows, MetricName.CITATION_COUNT)
    return sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def target_sources(rows: list[MetricRow]) -> list[tuple[str, int]]:
    """S11 sources.targetSources(5.6): target_citation_count 합이 0보다 큰 도메인, 내림차순."""
    total = _sum_by_domain(rows, MetricName.TARGET_CITATION_COUNT)
    return sorted(((d, n) for d, n in total.items() if n > 0), key=lambda kv: (-kv[1], kv[0]))
