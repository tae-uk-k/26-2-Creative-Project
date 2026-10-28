"""W-09-2 사실 검사(09 6.6)·칸 사전 값 검사(09 3장)·정비안 글 스키마(08 0.4)."""

import json
from pathlib import Path
from typing import Any

import pytest

from seelo.domain.fact_check import Fact, check_text
from seelo.domain.field_dictionary import is_incomplete, load_dictionary, same_value, spec, validate_value
from seelo.schemas.llm import PlanTextsOut

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "fact_check" / "wrong_20.json").read_text("utf-8")
)
FACTS = [Fact(f["id"], f["kind"], f.get("value"), f["source"], f["text"]) for f in CASES["facts"]]


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["text"] for c in CASES["cases"]])
def test_wrong_20_all_caught(case: dict[str, Any]) -> None:
    assert len(CASES["cases"]) == 20
    r = check_text(case["text"], FACTS, provider="kakao", field="intro")
    assert case["wrong"] not in r.text
    if case["expect"] == "removed":
        assert r.text == "" and r.removed == [case["text"]]
    else:
        assert "[ ]" in r.text and r.needs_owner_input


@pytest.mark.parametrize(
    ("text", "provider", "field", "out"),
    [
        ("Open daily 11:00–21:00.", "kakao", "intro", "Open daily 11:00–21:00."),
        ("Takeout available.", "kakao", "intro", "Takeout available."),  # 포장 사실이 있음
        ("Kalguksu 11,000 won.", "kakao", "intro", "Kalguksu 11,000 won."),  # 가격 사실과 같음
        ("Kalguksu 11,000 won.", "google", "description", ""),  # 소개에는 가격 금지(사실이 있어도)
        ("Call 02-776-0000 to book.", "google", "description", ""),  # 소개에는 전화 금지
        ("Visit www.demo.example today.", "google", "description", ""),
        ("Ask about our discount.", "google", "description", ""),
    ],
)
def test_keeps_facts_and_forbidden_content(text: str, provider: str, field: str, out: str) -> None:
    assert check_text(text, FACTS, provider=provider, field=field).text == out


def test_sensitive_kept_only_when_in_facts_and_flagged() -> None:
    facts = [*FACTS, Fact("f9", "intro_text", None, "website", "모든 메뉴는 할랄 인증 재료를 써요")]
    r = check_text("할랄 재료를 써요.", facts, provider="kakao", field="intro")
    assert (r.text, r.sensitive) == ("할랄 재료를 써요.", True)


def test_paragraphs_rejoined_by_language() -> None:
    r = check_text("Popular noodle spot. Halal food. 명동 칼국수 집이에요. 가게 소개예요.", FACTS,
                   provider="google", field="description")  # fmt: skip
    assert r.text == "Popular noodle spot.\n\n명동 칼국수 집이에요. 가게 소개예요."


# --- 칸 사전 ------------------------------------------------------------------------------


def test_dictionary_has_no_owner_only_fields() -> None:
    d = load_dictionary()
    assert set(d["google"]) == {"description", "regular_hours", "website", "phone", "menu", "attributes"}
    assert not ({"name", "address", "category"} & (set(d["google"]) | set(d["kakao"])))


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOURS = {"days": {d: [{"open": "11:00", "close": "21:00"}] for d in DAYS}, "breaks": {}, "notes": None}
BAD_HOURS = HOURS | {"days": {**HOURS["days"], "mon": [{"open": "11", "close": "21:00"}]}}


@pytest.mark.parametrize(
    ("provider", "field", "value", "reason"),
    [
        ("google", "description", "A" * 751, "too_long"),
        ("google", "description", "Visit https://x.com", "bad_format"),
        ("google", "description", "Open [ ] daily", "placeholder_left"),
        ("google", "description", "Fine text.", None),
        ("kakao", "intro", "가" * 51, "too_long"),
        ("google", "regular_hours", HOURS, None),
        ("google", "regular_hours", {"days": {"mon": []}}, "bad_format"),
        ("google", "regular_hours", BAD_HOURS, "bad_format"),
        ("google", "website", "https://demo.example/", None),
        ("google", "website", "demo.example", "bad_format"),
        ("google", "phone", "02-776-0000", None),
        ("google", "phone", "123", "bad_format"),
        ("google", "phone", "[ ]", "placeholder_left"),
        ("google", "menu", [{"name": "칼국수", "price": 11000}], None),
        ("google", "menu", [{"name": "", "price": 1}], "bad_format"),
        ("google", "menu", [{"name": "x", "price": -1}], "bad_format"),
        ("google", "menu", [{"name": "x"}] * 101, "too_many"),
        ("kakao", "price_items", [{"name": "x", "featured": True}] * 3, "too_many"),
        ("google", "attributes", {"vegetarian": True, "takeout": False}, None),
        ("google", "attributes", {"wifi": True}, "bad_format"),
        ("google", "attributes", {"vegetarian": None}, "bad_format"),
        ("kakao", "links", ["https://a.example", "nope"], "bad_format"),
        ("kakao", "tags", ["a", "b", "c", "d", "e", "f"], "too_many"),
        ("kakao", "tags", ["가" * 21], "too_long"),
    ],
)  # fmt: skip
def test_validate_value(provider: str, field: str, value: Any, reason: str | None) -> None:
    assert validate_value(spec(provider, field), value) == reason


def test_incomplete_and_same_value() -> None:
    attrs = spec("google", "attributes")
    assert is_incomplete(attrs, {"vegetarian": None}) and not is_incomplete(attrs, {"vegetarian": False})
    assert is_incomplete(spec("google", "phone"), "[ ]") and is_incomplete(spec("google", "menu"), [])
    assert same_value("phone", "02-776-0000", "+82 2-776-0000")
    assert same_value("url", "https://Demo.example/", "https://demo.example")
    assert same_value("text", " a  b ", "a b") and not same_value("text", "a", "b")
    assert same_value("hours", HOURS, json.loads(json.dumps(HOURS)))
    assert same_value("tags", ["b", "a"], ["a", "b"])


def test_plan_texts_schema_is_strict_compatible() -> None:
    js = PlanTextsOut.model_json_schema()
    for name, sub in [("PlanTextsOut", js), *js.get("$defs", {}).items()]:
        if sub.get("type") == "object":
            assert set(sub.get("required", [])) == set(sub["properties"]), name
