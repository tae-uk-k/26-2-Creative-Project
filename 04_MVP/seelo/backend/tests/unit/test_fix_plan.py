"""정비안 만들기의 순수 부분(09 4·6장)과 정비안 단계 판정(08 6.5)."""

from dataclasses import replace
from typing import Any

from seelo.domain import fix_plan as fp
from seelo.domain.field_dictionary import specs
from seelo.domain.findings_rules import FindingDraft, FindingInputs, judge_plan
from seelo.domain.metrics import RecView, ResponseView
from seelo.domain.normalize import normalize_name
from seelo.schemas.llm import MenuTextOut, PlanTextsOut, SentenceRefOut

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOURS = {"days": {d: [{"open": "11:00", "close": "21:00"}] for d in DAYS}, "breaks": {}, "notes": None}
SITE = {
    "hours": HOURS,
    "hours_text": "매일 11:00~21:00",
    "phone": "02-776-0000",
    "intro": "포장 가능한 칼국수집",
    "menu": [
        {"name": "칼국수", "price": 11000},
        {"name": "만두", "price": 10000},
        {"name": "콩국수", "price": None},
    ],
    "address": "서울 중구 명동10길 29",
}


def _f(i: int, field: str, category: str = "map_missing", key: str | None = None, **ev: Any) -> fp.FindingRef:
    return fp.FindingRef(i, "google", field, category, f"{category}.{key or field}", i, ev)


def _inp(provider: str = "google", findings: list[fp.FindingRef] | None = None, **kw: Any) -> fp.PlanInputs:
    base = fp.PlanInputs(
        provider=provider,
        category="restaurant",
        region_ko="명동",
        current={},
        findings=findings or [],
        website=SITE,
        website_url="https://demo.example/",
        google={"takeout": True, "nationalPhoneNumber": "02-1"},
        instagram_url="https://www.instagram.com/demo/",
    )
    return replace(base, **kw)


def test_facts_priority_sources_and_web_agreement() -> None:
    web = [
        {"url": "https://a.example/x", "phone": "02-555-1111"},
        {"url": "https://b.example/y", "phone": "02 555 1111"},
        {"url": "https://a.example/z", "hours_text": "10~20"},  # 1곳뿐
    ]
    facts = fp.build_facts(_inp(web_sites=web))
    kinds = [(f.kind, f.source) for f in facts]
    assert kinds[0] == ("hours", "website")  # 웹사이트가 먼저
    assert ("phone", "web") in kinds and ("hours_text", "web") not in kinds  # 2곳 이상 같을 때만
    assert ("attribute", "website") in kinds  # 소개에 "포장"
    assert ("attribute", "google") in kinds and ("instagram", "instagram") in kinds
    assert [f.id for f in facts] == [f"f{i}" for i in range(1, len(facts) + 1)]


def test_finding_to_item_and_owner_only() -> None:
    refs = [
        _f(1, "regular_hours"),
        _f(2, "menu", "condition_missing", "budget"),
        _f(3, "attributes", "condition_missing", "vegetarian"),
        _f(4, "name", "source_mismatch"),
        _f(5, "listing"),
        _f(6, "description", "english_missing"),
    ]
    assert [fp.item_field("google", r) for r in refs] == [
        "regular_hours",
        "menu",
        "attributes",
        None,
        None,
        "description",
    ]
    kakao = [replace(r, provider="kakao") for r in refs] + [
        fp.FindingRef(7, "kakao", "phone", "source_mismatch", "x", 7, {})
    ]
    assert [fp.item_field("kakao", r) for r in kakao[:3]] == ["hours", "services", "services"]
    assert [f for f, _ in fp.owner_only_fields("kakao", kakao)] == ["name", "phone"]
    assert fp.map_not_found("google", refs) and not fp.map_not_found("kakao", refs)


def test_draft_items_values_from_facts_only() -> None:
    refs = [
        _f(3, "regular_hours"),
        _f(1, "website"),
        _f(2, "phone", "source_mismatch", sources=[{"source": "website"}]),
        _f(4, "attributes", missingKeys=["takeout", "vegetarian"]),
        _f(5, "menu", "condition_missing", "budget"),
    ]
    inp = _inp(findings=refs)
    facts = fp.build_facts(inp)
    drafts = {d.field: d for d in fp.draft_items(inp, facts, specs("google"))}
    assert set(drafts) == {"regular_hours", "website", "phone", "attributes", "menu"}  # 근거 있는 칸만
    assert drafts["regular_hours"].proposed == HOURS and not drafts["regular_hours"].needs_owner_input
    assert drafts["website"].proposed == "https://demo.example/"
    assert drafts["phone"].proposed == "02-776-0000"
    assert drafts["attributes"].proposed == {"takeout": True, "vegetarian": None}
    assert drafts["attributes"].needs_owner_input  # 채식은 사실이 없어 사장님이 고름
    assert [m["name"] for m in drafts["menu"].proposed] == ["칼국수", "만두", "콩국수"]
    assert (
        drafts["website"].order_key == (1, 3)
        and drafts["phone"].reason == "공식 웹사이트와 Google 지도의 전화번호가 달라요"
    )


def test_missing_facts_mean_owner_input_or_no_item() -> None:
    refs = [_f(1, "regular_hours"), _f(2, "website"), _f(3, "phone"), _f(4, "menu")]
    inp = _inp(findings=refs, website=None, website_url=None, google={})
    drafts = {d.field: d for d in fp.draft_items(inp, fp.build_facts(inp), specs("google"))}
    assert (drafts["regular_hours"].proposed, drafts["regular_hours"].needs_owner_input) == (None, True)
    assert drafts["website"].delete  # 웹사이트 주소는 지어내지 않는다
    assert (drafts["phone"].proposed, drafts["phone"].needs_owner_input) == ("[ ]", True)
    assert (drafts["menu"].proposed, drafts["menu"].needs_owner_input) == ([], True)


def test_kakao_items_featured_links_services() -> None:
    refs = [
        fp.FindingRef(i, "kakao", f, "map_missing", f"map_missing.{f}", i, {})
        for i, f in enumerate(["price_items", "links", "services"], 1)
    ]
    inp = _inp("kakao", refs)
    drafts = {d.field: d for d in fp.draft_items(inp, fp.build_facts(inp), specs("kakao"))}
    assert [m["featured"] for m in drafts["price_items"].proposed] == [True, True, False]
    assert drafts["links"].proposed == ["https://demo.example/", "https://www.instagram.com/demo/"]
    assert drafts["services"].proposed == ["포장"]


def test_apply_texts_checks_facts_and_lengths() -> None:
    refs = [_f(1, "description"), _f(2, "menu")]
    inp = _inp(findings=refs)
    facts = fp.build_facts(inp)
    sp = {s.key: s for s in specs("google")}
    drafts = fp.draft_items(inp, facts, list(sp.values()))
    menu_fact = next(f.id for f in facts if f.kind == "menu_item")
    texts = PlanTextsOut(
        google_description=[
            SentenceRefOut(text="Famous noodles near Myeong-dong.", fact_ids=["f999"]),  # 없는 id는 무시
            SentenceRefOut(text="Open since 1966.", fact_ids=[]),  # 사실에 없는 숫자 → [ ]
            SentenceRefOut(text="All dishes are halal.", fact_ids=[]),  # 지움
            SentenceRefOut(text="명동의 칼국수집이에요.", fact_ids=["f1"]),
        ],
        kakao_intro=None,
        menu_texts=[
            MenuTextOut(fact_id=menu_fact, name_en="Knife-cut noodles", description_en="Gluten free.")
        ],
        kakao_tags=[],
    )
    fp.apply_texts(inp, facts, drafts, texts)
    by = {d.field: d for d in drafts}
    assert (
        by["description"].proposed
        == "Famous noodles near Myeong-dong. Open since [ ].\n\n명동의 칼국수집이에요."
    )
    assert by["description"].needs_owner_input and by["description"].fact_ids == ["f1"]
    assert (
        by["menu"].proposed[0]["nameEn"] == "Knife-cut noodles"
        and by["menu"].proposed[0]["description"] is None
    )
    long = "A very long sentence about noodles. " * 30
    assert fp.fit_length(long.strip(), 750)[0].count(".") < 30
    one, cut = fp.fit_length("x" * 800, 750)
    assert len(one) == 750 and cut


# --- 08 6.5 정비안 단계 판정 ------------------------------------------------------------------


def _rules(plan_values: dict[str, Any] | None, **kw: Any) -> FindingInputs:
    resp = ResponseView(
        1, "openai", 2, True, [RecView(normalize_name("B식당"), "B식당", 1, False, [], ["takeout"])], []
    )
    base = FindingInputs(
        category="restaurant",
        google_found=True,
        kakao_found=True,
        google={},
        kakao_basic=None,
        naver_basic=None,
        website={"hours": HOURS, "hours_text": "매일 11:00~21:00"},
        web_sites=[],
        question_ids=[1, 2, 3],
        question_features={2: ["takeout"]},
        responses=[resp],
        claims=[],
        competitors=["b식당"],
        competitor_facts={},
        plan_values=plan_values,
    )
    return replace(base, **kw)


def _keys(drafts: list[FindingDraft]) -> set[str]:
    return {f"{d.provider}:{d.title_key}" for d in drafts}


def test_plan_rules_skip_without_current_values() -> None:
    assert judge_plan(_rules(None), "google", []) == []
    assert judge_plan(_rules({"description": None, "menu": None}), "google", []) == []


def test_plan_rules_google() -> None:
    pv = {
        "description": "명동 칼국수",
        "menu": [{"name": "칼국수", "nameEn": None}],
        "attributes": {"takeout": None},
    }
    got = judge_plan(_rules(pv), "google", [])
    assert _keys(got) == {
        "google:english_missing.description",  # 라틴 문자 단어 5개 미만
        "google:english_missing.menu",  # 영문 이름이 절반 미만
        "google:condition_missing.takeout",  # P8: 지금 값에 포장 표시 없음, 주변 가게가 포장으로 추천됨
    }
    assert all(d.stage == "plan" for d in got)
    assert _keys(judge_plan(_rules({"description": "", "menu": []}), "google", [])) == {
        "google:map_missing.description",
        "google:map_missing.menu",
    }


def test_plan_rules_kakao_and_existing_dedup() -> None:
    late = {**HOURS, "days": {**HOURS["days"], "sun": [{"open": "11:00", "close": "18:00"}]}}
    pv = {
        "intro": "칼국수",
        "hours": late,
        "price_items": [],
        "links": ["https://a.example"],
        "services": ["예약"],
        "tags": ["명동맛집"],
    }
    got = judge_plan(_rules(pv), "kakao", [])
    assert _keys(got) == {
        "kakao:map_missing.price_items",
        "kakao:source_mismatch.regular_hours",
        "kakao:condition_missing.takeout",
    }
    assert "칼국수" not in str([d.evidence for d in got])  # 카카오 지금 값은 evidence에 넣지 않는다
    existing = [FindingDraft("diagnosis", "map_missing", "map_missing.price_items", "kakao", "price_items")]
    assert "kakao:map_missing.price_items" not in _keys(judge_plan(_rules(pv), "kakao", existing))
