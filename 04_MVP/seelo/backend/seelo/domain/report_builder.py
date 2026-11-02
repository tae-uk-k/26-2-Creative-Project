"""계산값과 고정 문구로만 만드는 보고서(10 3장). IO·LLM 호출 없음."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from seelo.domain.metrics import PROVIDERS, MetricRow, ResponseView, competitor_position, target_sources
from seelo.domain.normalize import domain_of, map_kind
from seelo.schemas.common import ProviderRates, RateSummary
from seelo.schemas.report import ChangeView, ReportContent

HEADLINE_CHANGE = "{ai} 추천 등장률이 {before:.1f}%에서 {after:.1f}%로 바뀌었어요."
HEADLINE_NO_CHANGE = "이번 측정에서는 큰 변화가 없었어요."
NOTE_DIFFERS = "지금 지도 값이 달라요(사장님이 바꿨거나 아직 반영 전)"
UNKNOWN_VALUE = "확인하지 못함"
NO_CHANGE_THRESHOLD_PP = 10
BANNED_TERMS = (
    "보장",
    "1위",
    "상위 노출",
    "반드시",
    "확실히",
    "효과가 있",
    "덕분에",
    "때문에 올랐",
    "guarantee",
    "#1",
    "top rank",
    "rank first",
)


@dataclass
class RunMetricsView:
    rows: list[MetricRow]
    responses: list[ResponseView]
    measured_at: datetime
    question_set_id: int
    repeat_count: int
    models: dict[str, str | None]


@dataclass
class QuestionView:
    id: int
    order_no: int
    lang: str
    text: str
    text_ko: str | None


def rate(
    rows: list[MetricRow], provider: str, *, name: str = "target", qid: int | None = None
) -> RateSummary:
    subject = "target" if name == "target" else "competitor"
    vals = {
        r.metric_name: r.value
        for r in rows
        if r.provider == provider
        and r.subject_type == subject
        and r.subject_name == name
        and r.question_id == qid
    }
    return RateSummary(
        success_count=int(vals.get("success_count") or 0),
        appearance_count=int(vals.get("appearance_count") or 0),
        rate=None if vals.get("appearance_rate") is None else round(vals["appearance_rate"], 4),
        avg_rank=None if vals.get("avg_rank") is None else round(vals["avg_rank"], 1),
    )


def rates(rows: list[MetricRow], name: str = "target") -> ProviderRates:
    return ProviderRates(**{p: rate(rows, p, name=name) for p in PROVIDERS})


def _competitors(rows: list[MetricRow]) -> list[tuple[str, str]]:
    return [
        (name, display)
        for _, name, display in sorted(
            {
                (r.rank_order or 0, r.subject_name, r.display_name or r.subject_name)
                for r in rows
                if r.subject_type == "competitor"
            }
        )
    ]


def _recount(responses: list[ResponseView], name: str) -> ProviderRates:
    """기준 주변 가게가 재측정 상위 5곳에서 빠져도 다시 계산한다(10 3.3)."""
    out = {}
    for p in PROVIDERS:
        ok = [r for r in responses if r.provider == p and r.extraction_ok]
        ranks = [
            min(hits)
            for r in ok
            if (hits := [x.rank for x in r.recs if not x.is_target and x.normalized_name == name])
        ]
        out[p] = RateSummary(
            success_count=len(ok),
            appearance_count=len(ranks),
            rate=round(len(ranks) / len(ok), 4) if ok else None,
            avg_rank=round(sum(ranks) / len(ranks), 1) if ranks else None,
        )
    return ProviderRates(**out)


def _map_citations(responses: list[ResponseView]) -> dict[str, int]:
    """원 응답의 URL·경로로 지도 인용을 센다(08 5.6, 7단계 주의 사항)."""
    counts = {"googleMaps": 0, "kakaoMap": 0}
    keys = {"google_maps": "googleMaps", "kakao_map": "kakaoMap"}
    for r in responses:
        if not r.extraction_ok:
            continue
        # 한 응답에서 같은 도메인은 한 번만 센다(08 5.6).
        sources = {(domain_of(u), map_kind(domain_of(u), u)) for u in r.source_urls}
        sources |= {(d, map_kind(d)) for d in r.source_domains if d not in {x[0] for x in sources}}
        for _, kind in sources:
            if kind in keys:
                counts[keys[kind]] += 1
    return counts


def build_report(
    *,
    before: RunMetricsView,
    after: RunMetricsView,
    questions: list[QuestionView],
    changes: list[ChangeView],
    fix_completed_at: datetime,
    interval_days: int,
    early: bool,
) -> ReportContent:
    # 반복 횟수·전송 경로가 바뀐 결과는 동일 조건의 전후 보고서로 묶지 않는다.
    def transport(model: str | None) -> str:
        if not model:
            return "unknown"
        return "local_cli" if model.startswith(("codex-cli/", "gemini-cli/")) else "api"

    if (
        before.question_set_id != after.question_set_id
        or before.repeat_count != after.repeat_count
        or any(transport(before.models.get(p)) != transport(after.models.get(p)) for p in PROVIDERS)
    ):
        raise ValueError("report_conditions_mismatch")
    local_cli = any(transport(model) == "local_cli" for model in before.models.values())
    comparisons: dict[str, Any] = {}
    for p in PROVIDERS:
        b, a = rate(before.rows, p), rate(after.rows, p)
        delta = None if b.rate is None or a.rate is None else round((a.rate - b.rate) * 100, 1)
        comparisons[p] = {"before": b, "after": a, "rateDeltaPp": delta}
    no_change = all(
        v["rateDeltaPp"] is None or abs(v["rateDeltaPp"]) < NO_CHANGE_THRESHOLD_PP
        for v in comparisons.values()
    )
    headline = HEADLINE_NO_CHANGE
    if not no_change:
        chosen = max(PROVIDERS, key=lambda p: abs(comparisons[p]["rateDeltaPp"] or 0))
        v = comparisons[chosen]
        headline = HEADLINE_CHANGE.format(
            ai={"openai": "ChatGPT", "gemini": "Gemini"}[chosen],
            before=v["before"].rate * 100,
            after=v["after"].rate * 100,
        )
    question_rows = []
    for q in questions:
        bq, aq, excluded = {}, {}, []
        for p in PROVIDERS:
            b, a = rate(before.rows, p, qid=q.id), rate(after.rows, p, qid=q.id)
            if not b.success_count or not a.success_count:
                excluded.append(p)
                bq[p] = aq[p] = None
            else:
                bq[p] = {"appearanceCount": b.appearance_count, "successCount": b.success_count}
                aq[p] = {"appearanceCount": a.appearance_count, "successCount": a.success_count}
        question_rows.append(
            {
                "orderNo": q.order_no,
                "lang": q.lang,
                "text": q.text,
                "textKo": q.text_ko,
                "before": bq,
                "after": aq,
                "excludedProviders": excluded,
            }
        )
    before_comps = _competitors(before.rows)
    names = {name for name, _ in before_comps}
    positions = {}
    for key, view in (("before", before), ("after", after)):
        pos, total = competitor_position(view.rows)
        positions[key] = {"position": pos, "total": total}
    return ReportContent.model_validate(
        {
            "measuredAt": {"before": before.measured_at, "after": after.measured_at},
            "fixCompletedAt": fix_completed_at,
            "intervalDays": interval_days,
            "earlyRemeasure": early,
            "summary": {
                "providers": comparisons,
                "competitorPosition": positions,
                "noChange": no_change,
                "headline": headline,
            },
            "competitors": {
                "beforeTop5": [
                    {
                        "name": display,
                        "before": rates(before.rows, name),
                        "after": _recount(after.responses, name),
                    }
                    for name, display in before_comps
                ],
                "newTop5After": [
                    {"name": display, "after": rates(after.rows, name)}
                    for name, display in _competitors(after.rows)
                    if name not in names
                ],
                "target": {"before": rates(before.rows), "after": rates(after.rows)},
            },
            "questions": question_rows,
            "sources": {
                "targetSources": {
                    key: [{"domain": d, "count": n} for d, n in target_sources(view.rows)]
                    for key, view in (("before", before), ("after", after))
                },
                "mapCitations": {
                    "before": _map_citations(before.responses),
                    "after": _map_citations(after.responses),
                },
            },
            "changes": [
                c.model_copy(
                    update={
                        "before_value": UNKNOWN_VALUE if c.before_value is None else c.before_value,
                        "note": NOTE_DIFFERS if c.remeasure_match == "differs" else None,
                    }
                )
                for c in changes
            ],
            "conditions": {
                "questionSetId": before.question_set_id,
                "repeatCount": before.repeat_count,
                "providers": list(PROVIDERS),
                "models": {"before": before.models, "after": after.models},
            },
            "notices": []
            + (
                ["이 보고서는 로컬 CLI 시험 결과예요. AI 서비스의 웹·앱과 측정 조건이 다를 수 있어요."]
                if local_cli
                else []
            ),
        }
    )


def assert_no_banned_terms(content: ReportContent | dict) -> None:
    """공지문만 제외하고 모든 문자열을 재귀 검사한다(10 3.4)."""
    data = content.model_dump(mode="json", by_alias=True) if isinstance(content, ReportContent) else content

    def check(value: Any) -> None:
        if isinstance(value, str) and any(term in value.casefold() for term in BANNED_TERMS):
            raise ValueError("report_banned_term")
        if isinstance(value, dict):
            for v in value.values():
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)

    check({k: v for k, v in data.items() if k != "notices"})
