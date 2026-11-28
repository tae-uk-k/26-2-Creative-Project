"""GEO 기법 저장 유지 시험 판정.

사용: python -I 판정.py <저장 후 HTML 파일> [<출력 JSON>]
시험본문.html의 T01~T19 표시가 원래 태그·속성 안에 남았는지 확인한다.
"""

import json
import sys
from html.parser import HTMLParser

# 표시 ID: (기법, 표시를 감싸야 하는 태그, 그 태그에 있어야 하는 속성 이름·값 일부)
TEXT_CHECKS = {
    "T01": ("D2 h2", "h2", None),
    "T02": ("D2 h3", "h3", None),
    "T03": ("D1 문단 p", "p", None),
    "T04": ("D2 dt", "dt", None),
    "T05": ("D2 dd", "dd", None),
    "T06": ("목록 li", "li", None),
    "T07": ("D6 summary", "summary", None),
    "T08": ("D6 details", "details", None),
    "T10": ("E2 figcaption", "figcaption", None),
    "T11": ("D3 cite", "cite", None),
    "T12": ("D3 time datetime", "time", ("datetime", "2026-11-28")),
    "T13": ("B5 itemprop", "span", ("itemprop", "name")),
    "T16": ("table th", "th", None),
    "T17": ("table td", "td", None),
    "T18": ("B2 JSON-LD script", "script", ("type", "application/ld+json")),
    "T19": ("B2 additionalProperty", "script", ("type", "application/ld+json")),
}
# 표시가 속성 값에 들어 있는 항목: (기법, 태그, 속성 이름)
ATTR_CHECKS = {
    "T09": ("E1 img alt", "img", "alt"),
    "T14": ("aria-label", "p", "aria-label"),
    "T15": ("data- 속성", "p", "data-seelo-id"),
}
# 표시 없이 존재만 보는 속성: (기법, 태그, 속성 이름, 값 일부)
PRESENCE_CHECKS = {
    "class": ("class 속성", "p", "class", "seelo-geo-test"),
    "itemscope": ("B5 itemscope·itemtype", "div", "itemtype", "schema.org/Product"),
    "section": ("section data-seelo", "section", "data-seelo", "geo-test"),
}
VOID = {"img", "br", "hr", "meta", "link", "input", "source"}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.texts: list[tuple[list[tuple[str, dict]], str]] = []
        self.elements: list[tuple[str, dict]] = []
        self.comments: list[str] = []

    def _attrs(self, attrs):
        return {k: v or "" for k, v in attrs}

    def handle_starttag(self, tag, attrs):
        item = (tag, self._attrs(attrs))
        self.elements.append(item)
        if tag not in VOID:
            self.stack.append(item)

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, self._attrs(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data.strip():
            self.texts.append((list(self.stack), data))

    def handle_comment(self, data):
        self.comments.append(data.strip())


def judge(html: str) -> dict:
    c = Collector()
    c.feed(html)
    result: dict = {}
    for marker, (technique, tag, attr) in TEXT_CHECKS.items():
        kept = any(
            marker in data
            and any(t == tag and (attr is None or attr[1] in a.get(attr[0], "")) for t, a in stack)
            for stack, data in c.texts
        )
        result[marker] = {"기법": technique, "상태": "유지" if kept else ("변형" if marker in html else "삭제")}
    for marker, (technique, tag, name) in ATTR_CHECKS.items():
        kept = any(t == tag and marker in a.get(name, "") for t, a in c.elements)
        result[marker] = {"기법": technique, "상태": "유지" if kept else ("변형" if marker in html else "삭제")}
    for key, (technique, tag, name, value) in PRESENCE_CHECKS.items():
        kept = any(t == tag and value in a.get(name, "") for t, a in c.elements)
        result[key] = {"기법": technique, "상태": "유지" if kept else "삭제"}
    result["필터_주석"] = [x for x in c.comments if "Filtered" in x]
    return result


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("사용: python -I 판정.py <저장 후 HTML> [<출력 JSON>]")
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        result = judge(f.read())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
