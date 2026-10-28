"""W-07-1 고쳐야 할 점 판정(08 6장): 분류마다 판정·미판정, 카카오·네이버 값은 evidence에 없음."""

from dataclasses import replace
from typing import Any

import pytest

from seelo.domain.findings_rules import (
    FindingDraft,
    FindingInputs,
    TargetClaim,
    ai_wrong_drafts,
    claim_checks,
    judge_diagnosis,
    title_for,
)
from seelo.domain.metrics import RecView, ResponseView
from seelo.domain.normalize import normalize_name
from seelo.integrations import Place

HOURS = {
    "periods": [
        {"open": {"day": d, "hour": 11, "minute": 0}, "close": {"day": d, "hour": 21, "minute": 0}}
        for d in range(7)
    ],
    "weekdayDescriptions": ["월요일: 오전 11:00~오후 9:00"],
}
GOOGLE = {
    "displayName": {"text": "명동교자"},
    "formattedAddress": "대한민국 서울특별시 중구 명동10길 29",
    "nationalPhoneNumber": "02-111-3333",
    "websiteUri": "https://kyoja.example/",
    "regularOpeningHours": HOURS,
    "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    "servesVegetarianFood": True,
    "paymentOptions": {"acceptsCreditCards": True},
    "reservable": False,
    "takeout": True,
}
WEEK_11_21 = {
    "days": {
        d: [{"open": "11:00", "close": "21:00"}] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    },
    "breaks": {},
    "notes": None,
}


def _place(provider: str, name: str, address: str | None = None, phone: str | None = None) -> Place:
    return Place(provider, "1", name, address, 37.5, 127.0, phone, [], None, {})


def _resp(rid: int, qid: int, *recs: tuple[str, bool, list[str]], provider: str = "openai") -> ResponseView:
    return ResponseView(
        rid,
        provider,
        qid,
        True,
        [RecView(normalize_name(n), n, i, t, [], attrs) for i, (n, t, attrs) in enumerate(recs, 1)],
        [],
    )


def _inp(**kw: Any) -> FindingInputs:
    base = FindingInputs(
        category="restaurant",
        google_found=True,
        kakao_found=True,
        google=dict(GOOGLE),
        kakao_basic=None,
        naver_basic=None,
        website=None,
        web_sites=[],
        question_ids=[1, 2, 3],
        question_features={1: [], 2: ["vegetarian"], 3: []},
        responses=[],
        claims=[],
        competitors=[],
        competitor_facts={},
    )
    return replace(base, **kw)


def _keys(drafts: list[FindingDraft]) -> set[tuple[str, str, str]]:
    return {(d.provider, d.field, d.title_key) for d in drafts}


def test_complete_google_makes_nothing() -> None:
    assert judge_diagnosis(_inp()) == []


def test_d1_not_found_on_maps() -> None:
    drafts = judge_diagnosis(_inp(google_found=False, kakao_found=False, google=None))
    assert _keys(drafts) == {
        ("google", "listing", "map_missing.listing"),
        ("kakao", "listing", "map_missing.listing"),
    }


@pytest.mark.parametrize(
    ("drop", "field"),
    [
        ("regularOpeningHours", "regular_hours"),
        ("websiteUri", "website"),
        ("nationalPhoneNumber", "phone"),
        ("priceLevel", "menu"),
    ],
)
def test_d2_each_missing_field(drop: str, field: str) -> None:
    g = {k: v for k, v in GOOGLE.items() if k != drop}
    assert _keys(judge_diagnosis(_inp(google=g))) == {("google", field, f"map_missing.{field}")}


def test_d2_price_range_counts_as_price() -> None:
    g = {k: v for k, v in GOOGLE.items() if k != "priceLevel"} | {
        "priceRange": {"startPrice": {"units": "9000"}}
    }
    assert judge_diagnosis(_inp(google=g)) == []


def test_d2_attributes_only_missing_not_false() -> None:
    g = {k: v for k, v in GOOGLE.items() if k not in ("servesVegetarianFood", "takeout")}
    g["reservable"] = False  # 거짓은 사실 → 없음이 아님
    drafts = judge_diagnosis(_inp(google=g, question_features={}))
    assert len(drafts) == 1 and drafts[0].field == "attributes"
    assert drafts[0].evidence == {"missingKeys": ["vegetarian", "takeout"]}


def test_d2_cafe_base_keys() -> None:
    g = {k: v for k, v in GOOGLE.items() if k != "servesVegetarianFood"}  # 카페 기본 키가 아님
    assert judge_diagnosis(_inp(category="cafe", google=g | {"outdoorSeating": False})) == []


def test_no_google_snapshot_skips_google_rules() -> None:
    """Google 스냅샷이 실패(None)면 D2·D3(Google)·D4를 판정하지 않는다."""
    resp = _resp(1, 2, ("B", False, ["vegetarian"]))
    inp = _inp(google=None, website={"phone": "02-999-9999"}, responses=[resp], competitors=["b"])
    assert judge_diagnosis(inp) == []


# --- D3 ------------------------------------------------------------------------------------


def test_d3_website_phone_differs() -> None:
    drafts = judge_diagnosis(_inp(website={"phone": "02-111-2222"}))
    assert _keys(drafts) == {("google", "phone", "source_mismatch.phone")}
    assert drafts[0].evidence == {
        "mapValue": "02-111-3333",
        "sources": [{"source": "website", "value": "02-111-2222", "valueStored": True}],
    }


def test_d3_one_web_site_alone_is_not_enough() -> None:
    sites = [{"url": "https://blog.example.com/a", "phone": "02-111-2222"}]
    assert judge_diagnosis(_inp(web_sites=sites)) == []


def test_d3_same_site_twice_counts_once() -> None:
    sites = [
        {"url": "https://t.example/a", "phone": "02-111-2222"},
        {"url": "https://t.example/b", "phone": "02-111-2222"},
    ]
    assert judge_diagnosis(_inp(web_sites=sites)) == []


def test_d3_two_sources_agreeing() -> None:
    sites = [
        {"url": "https://a.example/", "address": "서울 중구 명동길 99"},
        {"url": "https://b.example/", "address": "서울특별시 중구 명동길 99 2층"},
    ]
    drafts = judge_diagnosis(_inp(web_sites=sites))
    assert _keys(drafts) == {("google", "address", "source_mismatch.address")}
    assert [s["source"] for s in drafts[0].evidence["sources"]] == ["web:a.example", "web:b.example"]


def test_d3_naver_alone_never_and_its_value_not_stored() -> None:
    naver = _place("naver", "명동교자", "서울 중구 네이버로 1")
    assert judge_diagnosis(_inp(naver_basic=naver)) == []
    # 웹 사이트 1곳 + 네이버가 같은 주소로 다름 → 2곳 → finding, 네이버 값은 저장하지 않음
    sites = [{"url": "https://a.example/", "address": "서울 중구 네이버로 1"}]
    drafts = judge_diagnosis(_inp(naver_basic=naver, web_sites=sites))
    assert _keys(drafts) == {("google", "address", "source_mismatch.address")}
    assert {"source": "naver", "valueStored": False} in drafts[0].evidence["sources"]
    assert "네이버로" not in str([s for s in drafts[0].evidence["sources"] if s["source"] == "naver"])


def test_d3_name_uses_same_name_rule() -> None:
    sites = [
        {"url": "https://a.example/", "name": "명동교자 본점"},
        {"url": "https://b.example/", "name": "Myeongdong"},
    ]
    assert judge_diagnosis(_inp(web_sites=sites)) == []  # 지점명은 같은 이름, 다른 하나는 혼자


def test_d3_kakao_basic_compared_but_value_not_stored() -> None:
    kakao = _place("kakao", "명동교자", "서울 중구 명동10길 29", "02-555-5555")
    drafts = judge_diagnosis(_inp(kakao_basic=kakao, website={"phone": "02-111-3333"}))
    assert _keys(drafts) == {("kakao", "phone", "source_mismatch.phone")}
    assert "mapValue" not in drafts[0].evidence
    assert "02-555-5555" not in str(drafts[0].evidence)


def test_d3_hours_website_vs_google() -> None:
    late = {**WEEK_11_21, "days": {**WEEK_11_21["days"], "sat": [{"open": "11:00", "close": "23:00"}]}}
    drafts = judge_diagnosis(_inp(website={"hours": late, "hours_text": "토 11:00~23:00"}))
    assert _keys(drafts) == {("google", "regular_hours", "source_mismatch.regular_hours")}
    assert drafts[0].evidence["days"] == ["sat"]
    assert judge_diagnosis(_inp(website={"hours": WEEK_11_21})) == []


# --- D4 ------------------------------------------------------------------------------------


def test_d4_condition_missing_when_competitor_recommended_for_it() -> None:
    """D2(기본 편의 키 없음)와 D4는 분류가 달라 행을 따로 만든다(6.3)."""
    g = {k: v for k, v in GOOGLE.items() if k != "servesVegetarianFood"}
    resp = _resp(1, 2, ("B식당", False, ["vegetarian"]), ("우리", True, []))
    drafts = judge_diagnosis(_inp(google=g, responses=[resp], competitors=["b식당"]))
    assert _keys(drafts) == {
        ("google", "attributes", "map_missing.attributes"),
        ("google", "attributes", "condition_missing.vegetarian"),
    }
    cond = next(d for d in drafts if d.category == "condition_missing")
    assert cond.evidence == {"conditionKey": "vegetarian", "questionIds": [2], "competitors": ["B식당"]}


def test_d4_false_is_a_fact_and_needs_competitor_reason() -> None:
    resp = _resp(1, 2, ("B식당", False, ["vegetarian"]))
    g = GOOGLE | {"servesVegetarianFood": False}
    assert judge_diagnosis(_inp(google=g, responses=[resp], competitors=["b식당"])) == []
    g2 = {k: v for k, v in GOOGLE.items() if k != "servesVegetarianFood"}
    no_reason = _resp(1, 2, ("B식당", False, []))
    drafts = judge_diagnosis(_inp(google=g2, responses=[no_reason], competitors=["b식당"]))
    assert all(d.category != "condition_missing" for d in drafts)


def test_d4_budget_goes_to_menu() -> None:
    g = {k: v for k, v in GOOGLE.items() if k != "priceLevel"} | {
        "priceRange": {"startPrice": {"units": "1"}}
    }
    resp = _resp(1, 2, ("B식당", False, ["budget"]))
    drafts = judge_diagnosis(
        _inp(google=g, question_features={2: ["budget"]}, responses=[resp], competitors=["b식당"])
    )
    assert _keys(drafts) == {("google", "menu", "condition_missing.budget")}


# --- D5 ------------------------------------------------------------------------------------


def _claim(rid: int, field: str, value: str, provider: str = "openai", qid: int = 1) -> TargetClaim:
    return TargetClaim(rid, provider, qid, field, value)


def test_d5_checks_only_with_website_truth_and_target_appearing() -> None:
    responses = [_resp(1, 1, ("우리", True, [])), _resp(2, 1, ("남", False, []))]
    claims = [_claim(1, "hours", "Open 10-22"), _claim(2, "hours", "Open 9-18"), _claim(1, "phone", "02-1")]
    inp = _inp(responses=responses, claims=claims, website={"hours_text": "매일 11:00~21:00"})
    checks = claim_checks(inp)
    assert [(c.claim_field, c.claim, c.truth) for c in checks] == [
        ("hours", "Open 10-22", "매일 11:00~21:00")
    ]
    assert checks[0].map_value == "월요일: 오전 11:00~오후 9:00"
    assert claim_checks(replace(inp, website=None)) == []  # 정답이 없으면 판정하지 않는다


def test_d5_wrong_only_when_matches_map_or_no_map() -> None:
    responses = [_resp(1, 1, ("우리", True, [])), _resp(2, 2, ("우리", True, []), provider="gemini")]
    claims = [_claim(1, "phone", "02-111-3333"), _claim(2, "phone", "02-111-3333", "gemini", 2)]
    inp = _inp(responses=responses, claims=claims, website={"phone": "02-777-7777"})
    checks = claim_checks(inp)
    assert len(checks) == 1 and len(checks[0].claims) == 2  # 같은 문장은 한 번만 비교
    drafts = ai_wrong_drafts(checks, [(False, True)])
    assert _keys(drafts) == {("google", "phone", "ai_wrong.phone")}
    assert drafts[0].evidence["providers"] == ["gemini", "openai"] and drafts[0].evidence["questionIds"] == [
        1,
        2,
    ]
    assert ai_wrong_drafts(checks, [(False, False)]) == []  # 지도와도 다름 → 원인이 지도라고 할 수 없음
    assert ai_wrong_drafts(checks, [(True, True)]) == []


def test_only_google_and_kakao_findings() -> None:
    """인스타그램·외부 사이트 쪽 문제는 만들지 않는다."""
    g = {"displayName": {"text": "명동교자"}}
    drafts = judge_diagnosis(_inp(google=g, kakao_found=False, website={"phone": "02-0"}))
    assert {d.provider for d in drafts} <= {"google", "kakao"}


@pytest.mark.parametrize(
    ("key", "provider", "evidence", "title"),
    [
        ("map_missing.listing", "kakao", {}, "카카오맵에 가게가 없어요"),
        ("map_missing.attributes", "google", {}, "Google 지도에 편의 정보가 비어 있어요"),
        ("source_mismatch.phone", "google", {"sources": [{"source": "website"}]},
         "공식 웹사이트와 Google 지도의 전화번호가 달라요"),
        ("source_mismatch.address", "kakao", {"sources": [{"source": "web:a.com"}]},
         "외부 사이트와 카카오맵의 주소가 달라요"),
        ("condition_missing.vegetarian", "google", {}, "채식 가능 여부가 표시돼 있지 않아요"),
        ("ai_wrong.regular_hours", "google", {"providers": ["gemini"]}, "Gemini가 영업시간을 틀리게 말해요"),
        ("ai_wrong.menu", "google", {"providers": ["gemini", "openai"]}, "AI가 가격을 틀리게 말해요"),
    ],
)  # fmt: skip
def test_titles(key: str, provider: str, evidence: dict[str, Any], title: str) -> None:
    assert title_for(key, provider, evidence) == title
