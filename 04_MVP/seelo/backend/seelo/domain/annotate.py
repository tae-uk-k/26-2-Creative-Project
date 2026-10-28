"""답변 원문에 출처 번호 넣기(08 3.1·2.3, 14 2.5). IO 없음.

- 인용 위치 바로 뒤에 [n]을 넣는다. 뒤에서부터 넣어 앞 위치가 밀리지 않게 한다.
- 같은 URL은 처음 나온 번호 하나로 묶는다. 저장 형식: [{"n", "url", "title", "domain"}].
"""

from typing import Any

from seelo.domain.normalize import domain_of


def _insert(text: str, marks: list[tuple[int, int]]) -> str:
    """marks = [(위치, 번호)]. 같은 위치는 번호 순서대로 [1][2]."""
    out = text
    by_pos: dict[int, list[int]] = {}
    for pos, n in marks:
        if 0 <= pos <= len(text) and n not in by_pos.setdefault(pos, []):
            by_pos[pos].append(n)
    for pos in sorted(by_pos, reverse=True):
        out = out[:pos] + "".join(f"[{n}]" for n in sorted(by_pos[pos])) + out[pos:]
    return out


def annotate_openai(text: str, cites: list[tuple[str, str, int, int]]) -> tuple[str, list[dict[str, Any]]]:
    """cites = [(url, title, start_index, end_index)](url_citation 주석)."""
    sources: list[dict[str, Any]] = []
    number: dict[str, int] = {}
    marks: list[tuple[int, int]] = []
    for url, title, _start, end in cites:
        if url not in number:
            number[url] = len(sources) + 1
            sources.append({"n": number[url], "url": url, "title": title, "domain": domain_of(url)})
        marks.append((end, number[url]))
    return (_insert(text, marks) if marks else text), sources


def gemini_domain(chunk: dict[str, Any]) -> str:
    """Gemini 출처 uri는 리디렉션 주소다. 원래 사이트는 domain(있으면) → title. 공백이 있거나 비면 unknown."""
    for value in (chunk.get("domain"), chunk.get("title")):
        if value and " " not in value.strip():
            return domain_of("https://" + value.strip())
    return "unknown"


def annotate_gemini(
    text: str, chunks: list[dict[str, Any]], supports: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """chunks = [{"uri","title","domain"}], supports = [{"start_index","end_index","text","chunk_indices"}].

    위치는 segment.text를 원문에서 찾아 정한다. 못 찾으면 end_index가 원문 길이 이하일 때만 쓰고,
    아니면 위치 없이 출처 목록에만 넣는다(08 2.3).
    """
    sources: list[dict[str, Any]] = []
    number_by_url: dict[str, int] = {}
    chunk_n: dict[int, int] = {}
    for i, c in enumerate(chunks):
        url = c.get("uri") or ""
        if not url:
            continue
        if url not in number_by_url:
            number_by_url[url] = len(sources) + 1
            sources.append(
                {"n": number_by_url[url], "url": url, "title": c.get("title"), "domain": gemini_domain(c)}
            )
        chunk_n[i] = number_by_url[url]
    marks: list[tuple[int, int]] = []
    for s in supports:
        seg = s.get("text") or ""
        pos = text.find(seg) if seg else -1
        if pos >= 0:
            end = pos + len(seg)
        elif s.get("end_index") is not None and s["end_index"] <= len(text):
            end = s["end_index"]
        else:
            continue
        marks.extend((end, chunk_n[i]) for i in s.get("chunk_indices") or [] if i in chunk_n)
    return (_insert(text, marks) if marks else text), sources
