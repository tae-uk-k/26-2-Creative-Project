"""가짜 웹사이트·가짜 LLM(17 1장, 11 3장). 가짜 모드와 테스트가 같은 클래스를 쓴다.

- 웹사이트: 진짜 HttpWebsiteFetcher에 가짜 서버(httpx.MockTransport)와 가짜 DNS를 붙인다.
  robots·리디렉션·크기 제한 같은 규칙은 진짜 코드가 그대로 돈다.
- LLM: 스키마 이름별 결과를 돌려주고, 받은 프롬프트를 calls에 남긴다(네이버 값이 들어갔는지 테스트가 본다).
"""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel

from seelo.domain.annotate import annotate_openai
from seelo.domain.extraction import ANSWER_END, ANSWER_START
from seelo.integrations import LlmResult, StructuredResult
from seelo.integrations.http import ExternalApiError
from seelo.integrations.llm import LlmError
from seelo.integrations.website import HttpWebsiteFetcher
from seelo.schemas.llm import (
    DayHoursOut,
    EvidenceSiteOut,
    ExtractedRecOut,
    ExtractionOut,
    GeneratedQuestionOut,
    GeneratedQuestionsOut,
    IntervalOut,
    MenuItemOut,
    MenuTextOut,
    PlanTextsOut,
    SentenceRefOut,
    WebEvidenceExtractOut,
    WebsiteExtractOut,
    WeeklyHoursOut,
)

PUBLIC_IP = "93.184.216.34"  # 가짜 DNS가 모든 이름을 이 공인 주소로 풀어 준다

# --- 가짜 웹 서버 ---------------------------------------------------------------------


@dataclass
class FakeWebServer:
    """url → (상태, 헤더, 본문). robots.txt도 같은 표에 넣는다. 없는 주소는 404. 받은 요청을 기록한다."""

    pages: dict[str, tuple[int, dict[str, str], bytes]] = field(default_factory=dict)
    delays: dict[str, float] = field(default_factory=dict)
    seen: list[tuple[str, str]] = field(default_factory=list)

    def html(self, url: str, body: str, status: int = 200, **headers: str) -> None:
        self.pages[url] = (status, {"content-type": "text/html; charset=utf-8", **headers}, body.encode())

    def robots(self, origin: str, body: str | None = None, status: int = 200) -> None:
        self.pages[f"{origin}/robots.txt"] = (status, {"content-type": "text/plain"}, (body or "").encode())

    def redirect(self, url: str, to: str, status: int = 302) -> None:
        self.pages[url] = (status, {"location": to}, b"")

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.seen.append((request.method, url))
        if url in self.delays:
            await asyncio.sleep(self.delays[url])
        status, headers, body = self.pages.get(url, (404, {}, b""))
        return httpx.Response(status, headers=headers, content=body)

    def body_requests(self) -> list[str]:
        return [u for _, u in self.seen if not u.endswith("/robots.txt")]


async def _public_dns(host: str) -> list[str]:
    if host in ("localhost",) or host.endswith(".internal"):
        return ["127.0.0.1"]
    return [PUBLIC_IP]


def fake_website(server: FakeWebServer) -> HttpWebsiteFetcher:
    return HttpWebsiteFetcher(transport=httpx.MockTransport(server), resolver=_public_dns)


# --- 가짜 LLM ---------------------------------------------------------------------------

DEMO_SITE = "https://demo-restaurant.example"
DEMO_HOME = """<!doctype html><html lang="ko"><head><title>데모식당</title></head><body>
<script>var tracking = 1;</script>
<h1>데모식당</h1><p>명동에서 40년 된 칼국수집입니다.</p>
<p>영업시간: 매일 11:00~21:00 (브레이크 15:00~17:00)</p><p>전화 02-776-0000 · 서울 중구 명동10길 29</p>
<a href="/menu">메뉴 보기</a> <a href="/en/">English</a>
<a href="https://www.instagram.com/demo_restaurant/">Instagram</a>
</body></html>"""
DEMO_MENU = """<!doctype html><html lang="ko"><body><h2>메뉴</h2>
<ul><li>칼국수 11,000원</li><li>만두 10,000원</li></ul></body></html>"""


def demo_web_server() -> FakeWebServer:
    s = FakeWebServer()
    s.robots(DEMO_SITE, "User-agent: *\nAllow: /\n")
    s.html(f"{DEMO_SITE}/", DEMO_HOME)
    s.html(f"{DEMO_SITE}/menu", DEMO_MENU)
    return s


def demo_website_extract() -> WebsiteExtractOut:
    every_day = [
        DayHoursOut(
            day=d,  # type: ignore[arg-type]
            closed=False,
            intervals=[IntervalOut(open="11:00", close="21:00")],
            breaks=[IntervalOut(open="15:00", close="17:00")],
        )
        for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    ]
    return WebsiteExtractOut(
        hours_text="매일 11:00~21:00 (브레이크 15:00~17:00)",
        hours=WeeklyHoursOut(days=every_day, notes=None),
        menu=[
            MenuItemOut(name="칼국수", price=11000, description=None),
            MenuItemOut(name="만두", price=10000, description=None),
        ],
        intro="명동에서 40년 된 칼국수집입니다.",
        phone="02-776-0000",
        address="서울 중구 명동10길 29",
    )


def demo_questions(prompt: str) -> GeneratedQuestionsOut:
    """질문 생성 프롬프트(08 1.2)를 읽어 규칙을 지키는 질문 3개를 만든다(가짜 모드·테스트 기본값)."""
    q1 = re.search(r"Q1: English\. Ask for good (.+?) near (.+?)\.\n", prompt)
    q2 = re.search(r'The condition "(.+?)" must appear', prompt)
    q3 = re.search(r"Q3: Korean\. Ask for good (.+?) near (.+?), casual", prompt)
    if not (q1 and q2 and q3):
        raise LlmError("openai", "parse_failed")
    cuisine_en, area = q1.group(1), q1.group(2)
    cuisine_ko, region_ko = q3.group(1), q3.group(2)
    region_en = region_ko if area.startswith("<") else area  # 가짜: 영어 이름을 모르면 한글 그대로
    return GeneratedQuestionsOut(
        questions=[
            GeneratedQuestionOut(
                lang="en",
                intent_type="basic",
                text=f"Any good {cuisine_en} near {region_en}?",
                text_ko=f"{region_ko} 근처 괜찮은 {cuisine_ko} 있어?",
            ),
            GeneratedQuestionOut(
                lang="en",
                intent_type="conditional",
                text=f"Can you recommend {q2.group(1)} {cuisine_en} near {region_en}?",
                text_ko=f"{region_ko} 근처 조건에 맞는 {cuisine_ko} 추천해 줄래?",
            ),
            GeneratedQuestionOut(
                lang="ko", intent_type="basic", text=f"{region_ko} 근처 {cuisine_ko} 추천해줘", text_ko=None
            ),
        ],
        region_en=region_en,
    )


def demo_extraction(prompt: str) -> ExtractionOut:
    """추출 프롬프트(08 3.2)의 답변에서 "1. 이름 - ...[n]" 줄을 추천으로 읽는다(가짜 모드·테스트 기본값)."""
    start = prompt.find(ANSWER_START)
    answer = prompt[start + len(ANSWER_START) : prompt.rfind(ANSWER_END)] if start >= 0 else ""
    recs = []
    for line in answer.splitlines():
        m = re.match(r"\s*(\d+)\.\s+(.+?)\s+-\s", line)
        if m:
            recs.append(
                ExtractedRecOut(
                    name=m.group(2),
                    order=int(m.group(1)),
                    source_numbers=[int(n) for n in re.findall(r"\[(\d+)\]", line)],
                    mentioned_attributes=["takeout"] if "takeout" in line else [],
                )
            )
    return ExtractionOut(recommendations=recs, target_claims=[])


# AI 웹 검색(07 6.4) 가짜: 1단계 답변은 "SITE url | 사이트 | 이름 | 주소 | 전화 | 영업시간 | 인스타그램" 줄,
# 2단계 정리는 그 줄을 읽는다. 세 번째 사이트는 다른 가게라 거르기에서 빠진다.
# 인스타그램 주소는 넣지 않는다(데모 웹사이트 링크에 이미 있음). 인스타그램 경로 테스트는 결과를 직접 정한다.
AI_WEB_HEAD = "Find publicly available information about this place."


def _prompt_line(prompt: str, key: str) -> str:
    m = re.search(rf"^{key}: (.*)$", prompt, re.M)
    return m.group(1) if m else ""


def demo_evidence_answer(prompt: str) -> tuple[str, list[tuple[str, str, int, int]]]:
    name, address = _prompt_line(prompt, "Name"), _prompt_line(prompt, "Address")
    sites = [
        (FAKE_SOURCES[0][0], "Tripadvisor", name, address, "02-776-0000", "매일 11:00~21:00", ""),
        (FAKE_SOURCES[1][0], "대한민국 구석구석", name, address, "02-776-0000", "", ""),
        (
            "https://blog.example.com/other",
            "어느 블로그",
            "다른식당",
            "서울 중구 다른길 1",
            "02-000-0000",
            "",
            "",
        ),
    ]
    text, cites = "", []
    for url, site, *rest in sites:
        line = "SITE " + " | ".join([url, site, *rest])
        cites.append((url, site, len(text), len(text) + len(line)))
        text += line + "\n"
    return text.strip(), cites


def demo_web_evidence(prompt: str) -> WebEvidenceExtractOut:
    sites = []
    for line in prompt.splitlines():
        if not line.startswith("SITE "):
            continue
        parts = [p.strip() for p in re.sub(r"\[\d+\]", "", line[5:]).split("|")]
        url, site, name, address, phone, hours, insta = (parts + [""] * 7)[:7]
        sites.append(
            EvidenceSiteOut(
                url=url,
                site_name=site or None,
                name=name or None,
                address=address or None,
                phone=phone or None,
                hours_text=hours or None,
                menu=[MenuItemOut(name="칼국수", price=11000, description=None)] if hours else [],
                instagram_url=insta or None,
            )
        )
    return WebEvidenceExtractOut(sites=sites)


def demo_plan_texts(prompt: str) -> PlanTextsOut:
    """정비안 글 프롬프트(09 6.5)의 사실 줄("f3 [region] 명동")만 써서 사실 검사를 통과하는 글을 만든다."""
    facts = re.findall(r"^(f\d+) \[(\w+)\] (.+)$", prompt, re.M)
    first = {kind: (fid, text) for fid, kind, text in reversed(facts)}
    region = first.get("region", ("", "Seoul"))
    cuisine = first.get("cuisine", ("", "식당"))
    refs = [fid for fid in (region[0], cuisine[0]) if fid]
    want = prompt.split("Write:")[-1]
    return PlanTextsOut(
        google_description=[
            SentenceRefOut(text=f"A neighborhood {cuisine[1]} spot near {region[1]}.", fact_ids=refs),
            SentenceRefOut(text=f"{region[1]}에 있는 {cuisine[1]}이에요.", fact_ids=refs),
        ]
        if "google_description" in want
        else None,
        kakao_intro=f"{region[1]} {cuisine[1]}" if "kakao_intro" in want else None,
        menu_texts=[
            MenuTextOut(fact_id=fid, name_en=f"House dish {chr(64 + i)}", description_en="A house specialty.")
            for i, fid in enumerate((fid for fid, kind, _ in facts if kind == "menu_item"), 1)
        ]
        if "menu_texts" in want
        else [],
        kakao_tags=[f"{region[1]}맛집", cuisine[1]] if "kakao_tags" in want else [],
    )


DEFAULT_STRUCTURED: dict[str, Callable[[str], BaseModel]] = {
    "WebsiteExtractOut": lambda prompt: demo_website_extract(),
    "GeneratedQuestionsOut": demo_questions,
    "ExtractionOut": demo_extraction,
    "WebEvidenceExtractOut": demo_web_evidence,
    "PlanTextsOut": demo_plan_texts,
}

# 가짜 웹 검색 답변(17 1장): 질문마다 정해진 답변을 돌려 쓴다. 10번 중 3번은 데모식당이 2위
NEIGHBORS = ["명동칼국수", "을지면옥", "남산돈까스", "명동할머니국수", "광장빈대떡"]
FAKE_SOURCES = [
    ("https://www.tripadvisor.com/Restaurant_Review-demo", "Tripadvisor"),
    ("https://korean.visitkorea.or.kr/detail/demo", "대한민국 구석구석"),
    ("https://www.google.com/maps/place/demo", "Google Maps"),
]
DEMO_NAME = "데모식당"


def demo_answer(prompt: str, n: int) -> tuple[str, list[tuple[str, str, int, int]]]:
    """n번째 호출의 답변 원문과 인용 위치. n % 10이 0·3·6이면 데모식당이 2위."""
    names = list(NEIGHBORS)
    if n % 10 in (0, 3, 6):
        names = [names[0], DEMO_NAME, *names[1:4]]
    text = "Here are some places you might like:\n"
    cites: list[tuple[str, str, int, int]] = []
    for i, name in enumerate(names, 1):
        line = f"{i}. {name} - popular with visitors."
        start = len(text)
        text += line + "\n"
        url, title = FAKE_SOURCES[(i - 1) % len(FAKE_SOURCES)]
        cites.append((url, title, start, start + len(line)))
    return text.strip(), cites


@dataclass
class FakeLlm:
    """structured: 스키마 이름별 결과. web_answer: answers(prompt, n) 또는 데모 답변.

    fail_next로 오류를 흉내 낸다. "hang"은 응답 없이 멈춘다(부르는 쪽 제한 시간이 끊는다).
    only를 주면 그 호출(스키마 이름 또는 "web_answer")에서만 실패한다. 수집처럼 여러 호출이 섞일 때 쓴다.
    """

    provider: str = "openai"
    results: dict[str, BaseModel | Callable[[str], BaseModel]] = field(default_factory=dict)
    answers: Callable[[str, int], str] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    failures: list[tuple[str | None, str]] = field(default_factory=list)  # (only, 사유)
    _answered: dict[str, int] = field(default_factory=dict)

    def fail_next(self, n: int = 1, reason: str = "api_error", *, only: str | None = None) -> None:
        self.failures.extend([(only, reason)] * n)

    def _failure(self, kind: str) -> str | None:
        for i, (only, reason) in enumerate(self.failures):
            if only is None or only == kind:
                del self.failures[i]
                return reason
        return None

    async def structured(self, prompt: str, schema: type[BaseModel], *, model: str) -> StructuredResult:
        self.calls.append({"kind": "structured", "schema": schema.__name__, "prompt": prompt, "model": model})
        if (reason := self._failure(schema.__name__)) is not None:
            if reason == "hang":
                await asyncio.sleep(3600)
            raise LlmError(self.provider, reason)
        made = self.results.get(schema.__name__) or DEFAULT_STRUCTURED.get(schema.__name__)
        if made is None:
            raise LlmError(self.provider, "parse_failed")
        parsed = made(prompt) if callable(made) and not isinstance(made, BaseModel) else made
        return StructuredResult(
            parsed=schema.model_validate(parsed.model_dump()),
            model_id=model or "fake-cheap",
            input_tokens=len(prompt) // 4,
            output_tokens=50,
            latency_ms=1,
        )

    async def web_answer(self, prompt: str, *, model: str) -> LlmResult:
        self.calls.append({"kind": "web_answer", "prompt": prompt, "model": model})
        if (reason := self._failure("web_answer")) is not None:
            if reason == "hang":
                await asyncio.sleep(3600)
            raise LlmError(self.provider, reason)
        n = self._answered.get(prompt, 0)
        self._answered[prompt] = n + 1
        if self.answers is not None:
            text, cites = self.answers(prompt, n), []
        elif prompt.startswith(AI_WEB_HEAD):
            text, cites = demo_evidence_answer(prompt)
        else:
            text, cites = demo_answer(prompt, n)
        if not text.strip():
            raise LlmError(self.provider, "empty_answer")
        annotated, sources = annotate_openai(text, cites)
        return LlmResult(
            text=text,
            sources=sources,
            raw={"fake": True, "provider": self.provider, "output_text": text},
            model_id=model or f"fake-{self.provider}",
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            search_calls=1,
            latency_ms=1,
            annotated_text=annotated,
        )


# --- 가짜 인스타그램 Business Discovery(07 6.5) -------------------------------------------------

DEMO_INSTAGRAM = {
    "username": "demo_restaurant",
    "biography": "명동 40년 칼국수 · 매일 11:00~21:00",
    "website": DEMO_SITE,
    "followers_count": 1200,
    "media_count": 85,
    "media": {"data": []},
}


@dataclass
class FakeInstagram:
    """profiles[사용자 이름] → BD 결과. 없는 이름은 Graph 오류(개인 계정·없음)처럼 실패. calls에 이름."""

    profiles: dict[str, dict[str, Any]] = field(default_factory=lambda: {"demo_restaurant": DEMO_INSTAGRAM})
    calls: list[str] = field(default_factory=list)

    async def business_discovery(self, username: str) -> dict[str, Any] | None:
        self.calls.append(username)
        if username not in self.profiles:
            raise ExternalApiError("instagram", "graph_110", 400)
        return self.profiles[username]
