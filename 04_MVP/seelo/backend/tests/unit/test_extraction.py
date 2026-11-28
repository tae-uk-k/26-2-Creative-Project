"""추천 추출 후처리·스키마(08 3.2·3.3, W-05-1), AI 웹 검색 스키마·거르기(07 6.4, W-03-4)."""

import logging
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from seelo.domain.extraction import ANSWER_END, ANSWER_START, extraction_prompt, postprocess
from seelo.domain.matching import evidence_matches
from seelo.logging import setup_logging
from seelo.schemas.llm import ExtractedRecOut, ExtractionOut, WebEvidenceExtractOut

SOURCES = [
    {"n": 1, "url": "https://www.tripadvisor.com/x", "title": "T", "domain": "tripadvisor.com"},
    {"n": 2, "url": "https://blog.example.com/y", "title": "B", "domain": "blog.example.com"},
]


def _rec(
    name: str, order: int, nums: list[int] | None = None, attrs: list[str] | None = None
) -> ExtractedRecOut:
    return ExtractedRecOut(
        name=name,
        order=order,
        source_numbers=nums or [],
        mentioned_attributes=attrs or [],  # type: ignore[arg-type]
    )


def test_postprocess_rerank_dedupe_and_sources() -> None:
    out = ExtractionOut(
        recommendations=[
            _rec("을지면옥", 3, [2, 9]),  # 9번 출처는 없음 → 버림
            _rec("  ", 1),  # 빈 이름 삭제
            _rec("명동교자 본점", 2, [1, 1], ["takeout", "takeout", "budget"]),
            _rec("명동교자", 4, [2]),  # 같은 정규화 이름 → 첫 번째만
            _rec("!!!", 5),  # 정규화하면 빈 이름
        ],
        target_claims=[],
    )
    rows = postprocess(out, SOURCES)
    assert [(r.name, r.normalized_name, r.rank) for r in rows] == [
        ("명동교자 본점", "명동교자", 1),
        ("을지면옥", "을지면옥", 2),
    ]
    assert rows[0].source_urls == [{"url": "https://www.tripadvisor.com/x", "domain": "tripadvisor.com"}]
    assert rows[0].mentioned_attributes == ["takeout", "budget"]
    assert rows[1].source_urls == [{"url": "https://blog.example.com/y", "domain": "blog.example.com"}]


def test_postprocess_same_order_keeps_answer_order() -> None:
    out = ExtractionOut(recommendations=[_rec("B", 1), _rec("A", 1)], target_claims=[])
    assert [r.name for r in postprocess(out, [])] == ["B", "A"]


def test_prompt_has_targets_reasons_sources_and_answer() -> None:
    prompt = extraction_prompt("Try A.[1]", SOURCES, ["명동교자", "Myeongdong Kyoja", "명동교자"])
    assert "target places: 명동교자, Myeongdong Kyoja," in prompt  # 중복 없이
    assert "takeout (with takeout)" in prompt and "budget (affordable)" in prompt
    assert "[1] tripadvisor.com\n[2] blog.example.com" in prompt
    assert prompt.endswith(f"{ANSWER_START}Try A.[1]{ANSWER_END}")


def _strict(schema: type[BaseModel]) -> None:
    """OpenAI 엄격 모드(08 0.4): 모든 필드 required, 기본값 없음."""
    js = schema.model_json_schema()
    for name, sub in [(schema.__name__, js), *js.get("$defs", {}).items()]:
        if sub.get("type") == "object":
            assert set(sub.get("required", [])) == set(sub["properties"]), name
            assert all("default" not in p for p in sub["properties"].values()), name


@pytest.mark.parametrize("schema", [ExtractionOut, WebEvidenceExtractOut])
def test_schema_is_strict_compatible(schema: type[BaseModel]) -> None:
    _strict(schema)


REC = {"name": "A", "order": 1, "source_numbers": []}


@pytest.mark.parametrize(
    "bad",
    [
        {"recommendations": [REC | {"mentioned_attributes": ["wifi"]}], "target_claims": []},  # 없는 조건 키
        {"recommendations": [REC], "target_claims": []},  # mentioned_attributes 빠짐
        {"recommendations": [], "target_claims": [{"field": "rating", "value": "4.5"}]},
        {"recommendations": []},
    ],
)
def test_extraction_schema_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ExtractionOut.model_validate(bad)


def test_web_evidence_schema_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        WebEvidenceExtractOut.model_validate({"sites": [{"url": "https://x.com", "name": "A"}]})


@pytest.mark.parametrize(
    ("name", "address", "keep"),
    [
        ("명동교자 본점", None, True),  # 이름이 같음(지점명)
        ("Myeongdong Kyoja", "다른 주소", True),  # 영문 이름 후보
        ("다른식당", "서울 중구 명동10길 29 2층", True),  # 주소(도로명·건물번호)가 같음
        ("다른식당", "서울 중구 명동10길 30", False),
        (None, None, False),  # 둘 다 판단할 수 없음 → 버림
        (None, "중구 명동2가 25-2", False),  # 지번 주소는 비교하지 않음
    ],
)
def test_evidence_matches(name: str | None, address: str | None, keep: bool) -> None:
    got = evidence_matches(
        name,
        address,
        names=["명동교자", "Myeongdong Kyoja"],
        our_address="대한민국 서울특별시 중구 명동10길 29",
        threshold=85,
    )
    assert got is keep


def test_httpx_request_lines_not_logged_at_info() -> None:
    """Graph API 토큰이 주소에 실리므로 httpx의 요청 줄(INFO)을 남기지 않는다."""
    setup_logging("INFO", cache=False)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
