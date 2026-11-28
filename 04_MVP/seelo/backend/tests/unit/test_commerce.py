"""상품 정보의 근거·한도·원본 보존 규칙."""

import pytest
from pydantic import ValidationError

from seelo.domain.commerce import draft, fingerprint, public_url, verified_facts
from seelo.errors import AppError
from seelo.schemas.commerce import FactInput, ShopCreate


def fact(key="material", value="면 100%", **kwargs):
    return {
        "key": key,
        "value": value,
        "quote": f"확인한 소재: {value}",
        "identity": "티셔츠 A / 검정 M",
        "source_url": "https://maker.example.com/a",
        **kwargs,
    }


@pytest.mark.parametrize("platform", ["shopify", "imweb", "google", "kakao"])
def test_only_two_platforms(platform):
    with pytest.raises(ValidationError):
        ShopCreate(platform=platform, external_id="demo", name="테스트")


@pytest.mark.parametrize(
    "url",
    [
        "http://maker.example.com",
        "https://user:pass@maker.example.com",
        "https://127.0.0.1/",
        "https://metadata.google.internal/",
        "https://maker.example.com:8443",
        "https://[broken/",
        "https://maker.example.com:port",
        "https://localhost/",
        "https://[::ffff:127.0.0.1]/",
    ],
)
def test_source_urls_reject_credentials_and_internal_hosts(url):
    with pytest.raises(AppError, match="COMMERCE_INVALID"):
        public_url(url)


def test_fact_requires_same_model_and_literal_source():
    for changed in ({"identity": "다른 모델"}, {"quote": "폴리에스터"}):
        with pytest.raises(AppError, match="COMMERCE_INVALID"):
            verified_facts([FactInput(**fact(**changed))], "티셔츠 A / 검정 M")
    with pytest.raises(AppError, match="COMMERCE_INVALID"):
        verified_facts([FactInput(**fact()), FactInput(**fact(value="울 100%"))], "티셔츠 A / 검정 M")


def test_html_is_preserved_and_facts_are_escaped():
    original = '<div class="editor"><img src="https://cdn.example.com/a.jpg"></div>'
    facts = [fact(value='<script>alert("test")</script>')]
    changes, questions, deferred, asked = draft(
        "cafe24", {"description": original}, facts, ["description"], ["size"], [], [], editor_conversion=False
    )
    value = changes[0]["proposed"]
    assert value.startswith(original)
    assert "<script>" not in value and "&lt;script&gt;" in value
    assert questions[0]["field"] == "size" and deferred == ["fact:size"] and asked == ["size"]
    assert changes[0]["method"] == "api"
    again = draft(
        "cafe24", {"description": value}, facts, ["description"], [], [], [], editor_conversion=False
    )
    assert again[0] == []  # 같은 사실을 다시 정리해도 설명이 중복되지 않는다.


def test_configured_question_budget_survives_regeneration_and_answers():
    _, q, _, asked = draft(
        "cafe24",
        {},
        [],
        ["description"],
        ["size", "power"],
        [],
        [],
        editor_conversion=False,
        question_limit=3,
    )
    assert len(q) == 2
    _, q, _, asked = draft(
        "cafe24",
        {},
        [fact("size", "10cm")],
        ["description"],
        ["size", "power", "care", "weight"],
        asked,
        [],
        editor_conversion=False,
        question_limit=3,
    )
    assert asked == ["size", "power", "care"]
    assert [x["field"] for x in q] == ["power", "care"]
    result = draft(
        "cafe24",
        {},
        [],
        ["description"],
        ["weight", "components"],
        asked,
        [],
        editor_conversion=False,
        question_limit=3,
    )
    assert result[1] == [] and result[3] == asked


def test_no_facts_do_not_erase_existing_product():
    changes, _, deferred, _ = draft(
        "cafe24", {"description": "원본"}, [], ["description"], [], [], [], editor_conversion=False
    )
    assert not changes and deferred == ["description"]


def test_smart_editor_conversion_is_separate_approval():
    result = draft(
        "smartstore", {}, [fact()], ["description", "attributes"], [], [], [], editor_conversion=False
    )
    assert [c["method"] for c in result[0]] == ["manual", "manual"]
    result = draft("smartstore", {}, [fact()], ["description"], [], [], [], editor_conversion=True)
    assert result[0][0]["method"] == "api"


def test_protected_fields_and_existing_summary():
    with pytest.raises(AppError, match="COMMERCE_INVALID"):
        draft("cafe24", {}, [fact()], ["price"], [], [], [], editor_conversion=False)
    result = draft(
        "cafe24",
        {"summary_description": "충분한 기존 설명"},
        [fact()],
        ["summary_description"],
        [],
        [],
        [],
        editor_conversion=False,
    )
    assert result[0] == []
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_browser_field_support_matches_configured_inputs():
    from seelo.domain.commerce import field_support
    from seelo.integrations.browser.commerce import configured_fields

    cafe = field_support("cafe24", "browser", configured_fields("cafe24"))
    assert "mobile_description" not in cafe["automatic"] + cafe["manual"]
    assert {"field": "mobile_description", "reason": "browser_field_not_configured"} in cafe["unavailable"]
    assert {"description", "summary_description", "seo.meta_title"} <= set(cafe["automatic"])
    naver = field_support("smartstore", "browser", configured_fields("smartstore"))
    assert naver["automatic"] == ["description"] and naver["manual"] == ["attributes"]
    api = field_support("smartstore", "api")
    assert api["conditions"] == {"description": "editor_conversion_approval"}
    assert field_support("cafe24", "browser", set())["automatic"] == []


def test_unsupported_field_is_rejected_before_plan():
    from seelo.domain.commerce import check_supported, field_support

    support = field_support("cafe24", "browser", {"description"})
    with pytest.raises(AppError) as error:
        check_supported(support, ["description", "mobile_description"])
    assert error.value.details["fields"] == ["mobile_description"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://smartstore.naver.com/seelo", ("smartstore", "seelo", 1, "not_applicable")),
        ("smartstore.naver.com/Seelo/products/13892740658", ("smartstore", "seelo", 1, "not_applicable")),
        ("https://m.smartstore.naver.com/seelo/products/1", ("smartstore", "seelo", 1, "not_applicable")),
        ("https://xodnrdl06066.cafe24.com/", ("cafe24", "xodnrdl06066", 1, "default")),
        ("https://m.demo01.cafe24.com/product/list.html", ("cafe24", "demo01", 1, "default")),
        (
            "https://demo01.cafe24.com/disp/admin/shop2/product/ProductRegister?product_no=9",
            ("cafe24", "demo01", 2, "url_path"),
        ),
        ("https://demo01.cafe24.com/product/detail.html?shop_no=3", ("cafe24", "demo01", 3, "url_query")),
    ],
)
def test_store_url_is_parsed_without_guessing(url, expected):
    from seelo.domain.commerce import parse_store_url

    result = parse_store_url(url)
    keys = ("platform", "external_id", "shop_no", "shop_no_source")
    assert tuple(result[key] for key in keys) == expected


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://www.mybrand.co.kr/", "custom_domain_requires_mall_id"),
        ("https://sell.smartstore.naver.com/#/products/edit/1", "smartstore_store_url_required"),
        ("https://smartstore.naver.com/main/products/1", "smartstore_store_url_required"),
        ("https://www.cafe24.com/", "cafe24_mall_url_required"),
        ("https://user:pw@demo01.cafe24.com/", "store_url_invalid"),
        ("ftp://demo01.cafe24.com/", "store_url_invalid"),
        ("https://demo01.cafe24.com.evil.example/", "custom_domain_requires_mall_id"),
    ],
)
def test_store_url_rejects_unknown_or_unsafe_hosts(url, reason):
    from seelo.domain.commerce import parse_store_url

    with pytest.raises(AppError) as error:
        parse_store_url(url)
    assert error.value.details["reason"] == reason


def test_cafe24_product_url_reads_same_product_number():
    from seelo.domain.commerce import parse_cafe24_product_url

    assert (
        parse_cafe24_product_url("https://demo01.cafe24.com/product/detail.html?product_no=14")["product_no"]
        == "14"
    )
    assert (
        parse_cafe24_product_url("https://demo01.cafe24.com/product/name/15/category/1/display/2/")[
            "product_no"
        ]
        == "15"
    )
    with pytest.raises(AppError):
        parse_cafe24_product_url("https://smartstore.naver.com/seelo/products/13892740658")
    with pytest.raises(AppError):
        parse_cafe24_product_url("https://demo01.cafe24.com/product/list.html")


def test_quantities_need_units_and_matching_source():
    from seelo.domain.commerce import check_quantity

    found = check_quantity("nutrition", "단백질 12 g (1회 30 g당)", "1회 30 g당 단백질 12 g, 지방 2 g")
    assert found == [{"amount": "12", "unit": "g"}, {"amount": "30", "unit": "g"}]
    assert check_quantity("ingredients", "사차인치 100%", None) == []
    with pytest.raises(AppError) as error:
        check_quantity("nutrition", "단백질 많음", None)
    assert error.value.details["reason"] == "quantity_unit_required"
    with pytest.raises(AppError) as error:
        check_quantity("serving", "1회 20 g", "1회 30 g 섭취")
    assert error.value.details["reason"] == "quantity_not_in_quote"


def _tags(value: str) -> set[str]:
    import re

    return set(re.findall(r"<([a-z0-9]+)", value))


FOOD = [
    fact("ingredients", "수박씨 100%", quote="원재료: 수박씨 100%", source="fetched_page"),
    fact("weight", "300g", quote="내용량 300g", source="browser", source_url="https://admin.example.com/p"),
    fact("storage", "서늘한 곳", quote="서늘한 곳", source="owner_answer", source_url=None),
]


def test_cafe24_section_has_summary_spec_use_faq_and_folded_quotes():
    changes, *_ = draft(
        "cafe24", {"description": "<p>원본</p>"}, FOOD, ["description"], [], [], [], editor_conversion=False
    )
    value = changes[0]["proposed"]
    assert value.startswith("<p>원본</p>")
    # 요약 문단은 상품명과 앞쪽 사실을 잇는다. 새 문구를 만들지 않는다.
    assert "<p>티셔츠 A / 검정 M. 원재료 수박씨 100% · 무게 300g · 보관 방법 서늘한 곳</p>" in value
    assert (
        "<h3>상품 사양</h3><dl><dt>원재료</dt><dd>수박씨 100% (출처: <cite>maker.example.com</cite>)</dd>"
        in value
    )
    # 기존 본문에서 읽은 사실은 관리 화면 주소를 공개 출처로 쓰지 않는다.
    assert "admin.example.com" not in value and "판매자 상품 정보" in value
    assert "<h3>사용·보관·주의</h3>" in value
    assert "<p>Q. 보관 방법은 어떻게 되나요?</p><p>A. 서늘한 곳</p>" in value
    # 외부 자료의 인용문만 접힘 영역에 넣는다.
    assert value.count("<details>") == 1 and "“원재료: 수박씨 100%”" in value and "“내용량 300g”" not in value
    assert "<script" not in value  # 보조 JSON-LD는 설정으로 켠 경우에만 넣는다.
    again = draft(
        "cafe24", {"description": value}, FOOD, ["description"], [], [], [], editor_conversion=False
    )
    assert again[0] == []


def test_smartstore_section_uses_only_verified_tags():
    changes, *_ = draft("smartstore", {}, FOOD, ["description"], [], [], [], editor_conversion=True)
    value = changes[0]["proposed"]
    # 스마트스토어 실계정 저장으로 확인한 태그(div·p·h2·h3·img)와 기존 영역 표시만 쓴다.
    assert _tags(value) <= {"section", "h2", "h3", "p"}
    assert "<p>원재료: 수박씨 100% (출처: maker.example.com)</p>" in value
    assert "<p>A. 서늘한 곳</p>" in value


def test_json_ld_matches_visible_facts_and_cannot_close_script():
    import json
    import re

    facts = [fact("material", '면 </script><img src=x onerror="alert(1)"> & 폴리')]
    changes, *_ = draft(
        "cafe24", {}, facts, ["description"], [], [], [], editor_conversion=False, json_ld=True
    )
    value = changes[0]["proposed"]
    scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', value, re.S)
    assert len(scripts) == 1 and "<" not in scripts[0] and "&" not in scripts[0]
    data = json.loads(scripts[0])
    assert data["name"] == "티셔츠 A / 검정 M"
    assert data["additionalProperty"] == [
        {"@type": "PropertyValue", "name": "소재", "value": facts[0]["value"]}
    ]
    naver, *_ = draft(
        "smartstore", {}, facts, ["description"], [], [], [], editor_conversion=True, json_ld=True
    )
    assert "<script" not in naver[0]["proposed"]


def test_short_fields_follow_length_rules_and_keep_existing_values():
    fields = ["seo.meta_title", "seo.meta_description", "seo.meta_keywords", "simple_description"]
    changes, *_ = draft(
        "cafe24", {}, FOOD, fields, [], [], [], editor_conversion=False, product_name="수박씨 분말 300g"
    )
    by_field = {c["field"]: c["proposed"] for c in changes}
    assert by_field["seo.meta_title"] == "수박씨 분말 300g | 수박씨 100% | 300g | 서늘한 곳"
    assert len(by_field["seo.meta_title"]) <= 60
    assert by_field["seo.meta_description"].startswith("수박씨 분말 300g. 원재료 수박씨 100%")
    assert len(by_field["seo.meta_description"]) <= 155
    assert by_field["seo.meta_keywords"] == "수박씨 분말 300g,수박씨 100%,300g,서늘한 곳"
    assert by_field["simple_description"] == by_field["seo.meta_description"]
    kept, *_ = draft(
        "cafe24",
        {"seo.meta_title": "기존 제목"},
        FOOD,
        ["seo.meta_title"],
        [],
        [],
        [],
        editor_conversion=False,
    )
    assert kept == []
    # 상품명을 받지 못하면 identity의 `상품명 | 모델명`에서 상품명만 쓴다.
    model_facts = [{**f, "identity": "보온병 | B750"} for f in FOOD]
    titled, *_ = draft("cafe24", {}, model_facts, ["seo.meta_title"], [], [], [], editor_conversion=False)
    assert titled[0]["proposed"].startswith("보온병 | 수박씨 100%")


def test_default_scope_and_existing_source_links():
    from seelo.domain.commerce import description_links, recommended_fields

    automatic = ["description", "seo.meta_description", "seo.meta_title", "summary_description"]
    current = {"description": "<p>원본</p>", "summary_description": "기존 요약", "seo.meta_description": ""}
    assert recommended_fields(automatic, current) == ["description", "seo.meta_description"]
    assert recommended_fields(["description"], {}) == ["description"]
    html = (
        '<a href="https://maker.example.com/a">제조사</a><a href="http://plain.example.com">x</a>'
        '<a href="https://127.0.0.1/x">x</a><a href="https://maker.example.com/a">중복</a>'
    )
    assert description_links(html) == ["https://maker.example.com/a"]
