"""상품 사실·정비 규칙. 금액·재고·옵션·판매 상태는 수정 대상에서 제외한다."""

import hashlib
import html
import ipaddress
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from seelo.errors import AppError
from seelo.schemas.commerce import FactInput

LABELS = {
    "purpose": "용도",
    "model": "모델",
    "material": "소재",
    "size": "크기",
    "weight": "무게",
    "components": "구성품",
    "power": "전원 조건",
    "compatibility": "호환 조건",
    "care": "사용·관리",
    "ingredients": "원재료",
    "nutrition": "영양성분·함량",
    "serving": "섭취 방법·1회 섭취량",
    "allergens": "알레르기 유발 성분",
    "origin": "원산지",
    "storage": "보관 방법",
    "manufacturer": "제조·판매원",
}
# 숫자와 단위가 함께 있어야 하는 사실. 단위 없는 함량은 저장하지 않는다.
QUANTITATIVE = {"nutrition", "serving"}
UNIT = r"(?:kcal|kJ|mg|mcg|μg|㎍|µg|g|kg|mL|ml|L|IU|%|정|포|캡슐|스쿱)"
QUANTITY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + UNIT + r")(?![A-Za-z])")


def quantities(value: str) -> list[dict]:
    return [{"amount": a, "unit": u} for a, u in QUANTITY.findall(value)]


def check_quantity(key: str, value: str, quote: str | None) -> list[dict]:
    """함량·섭취량은 숫자+단위가 있어야 하고, 출처 인용문에도 같은 숫자+단위가 있어야 한다."""
    if key not in QUANTITATIVE:
        return []
    found = quantities(value)
    if not found:
        raise AppError("COMMERCE_INVALID", {"reason": "quantity_unit_required", "field": key})
    if quote is not None:
        quoted = {(q["amount"], q["unit"]) for q in quantities(quote)}
        if any((q["amount"], q["unit"]) not in quoted for q in found):
            raise AppError("COMMERCE_INVALID", {"reason": "quantity_not_in_quote", "field": key})
    return found


def recommended_fields(automatic: list[str], current: dict[str, str]) -> list[str]:
    """판매자가 고르지 않아도 되는 기본 범위. 본문은 항상, 짧은 설명은 비어 있을 때만 채운다."""
    fields = [f for f in ("description",) if f in automatic]
    for field in ("summary_description", "simple_description", "seo.meta_description"):
        if field in automatic and not (current.get(field) or "").strip():
            fields.append(field)
    return fields


def description_links(value: str, limit: int = 3) -> list[str]:
    """기존 본문에 들어 있는 공개 HTTPS 자료 주소. 본문 링크만 쓰고 주소를 만들지 않는다."""
    from selectolax.lexbor import LexborHTMLParser

    links = []
    for node in LexborHTMLParser(value or "").css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        try:
            public_url(href)
        except AppError:
            continue
        if href not in links:
            links.append(href)
        if len(links) >= limit:
            break
    return links


CAFE_FIELDS = {"description", "mobile_description", "summary_description", "simple_description"}
SEO_FIELDS = {"seo.meta_title", "seo.meta_description", "seo.meta_keywords"}
FIELDS = {"cafe24": CAFE_FIELDS | SEO_FIELDS, "smartstore": {"description", "attributes"}}
# 관리자가 화면에서 직접 고치는 필드. 자동 저장·재조회 대상이 아니다.
MANUAL_FIELDS = {"cafe24": set(), "smartstore": {"attributes"}}


def field_support(platform: str, mode: str, browser_fields: set[str] | None = None) -> dict:
    """현재 편집 모드에서 자동 저장·수동 처리·미지원 필드를 나눈다.

    브라우저 모드는 실제 화면 설정에 입력 칸이 있는 필드만 자동 저장한다. 원본을 읽지 못하는 필드는
    수정 전 값을 알 수 없으므로 수동 경로로도 제공하지 않는다.
    """
    manual = MANUAL_FIELDS[platform]
    if mode == "browser":
        automatic = (browser_fields or set()) & (FIELDS[platform] - manual)
        reason = "browser_field_not_configured"
    else:
        automatic = FIELDS[platform] - manual
        reason = "api_field_not_supported"
    unavailable = FIELDS[platform] - automatic - manual
    conditions = {}
    if mode == "api" and platform == "smartstore":
        # API 본문 저장은 편집기 형식 전환을 승인한 경우에만 자동 경로다. 아니면 수동 정비안으로 만든다.
        conditions["description"] = "editor_conversion_approval"
    return {
        "mode": mode,
        "automatic": sorted(automatic),
        "manual": sorted(manual),
        "unavailable": [{"field": f, "reason": reason} for f in sorted(unavailable)],
        "conditions": conditions,
    }


def selectable_fields(support: dict) -> set[str]:
    return set(support["automatic"]) | set(support["manual"])


def check_supported(support: dict, fields: list[str]) -> None:
    unsupported = [f for f in dict.fromkeys(fields) if f not in selectable_fields(support)]
    if unsupported:
        raise AppError(
            "COMMERCE_INVALID",
            {"reason": "field_not_supported", "fields": unsupported, "mode": support["mode"]},
        )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalize_cafe24_browser_html(value: str) -> str:
    """실계정 Froala에서 확인한 바깥·문단 사이 줄바꿈 차이만 비교에서 제외한다."""
    value = value.strip("\r\n")
    if re.search(
        r"<(?:pre|textarea|script|style|code)(?:\s|>)|white-space\s*:\s*(?:pre|break-spaces)",
        value,
        re.I,
    ):
        return value
    return re.sub(r"</p>\r?\n+(?=<p(?:\s|>))", "</p>\n", value)


def public_url(value: str) -> str:
    try:
        p = urlsplit(value)
        host, port = p.hostname or "", p.port
    except ValueError as error:
        raise AppError("COMMERCE_INVALID", {"reason": "public_https_url_required"}) from error
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AppError("COMMERCE_INVALID", {"reason": "public_domain_required"})
    if (
        p.scheme != "https"
        or p.username
        or p.password
        or port not in (None, 443)
        or "." not in host
        or host in {"localhost", "metadata.google.internal"}
        or re.fullmatch(r"[0-9.:]+", host)
        or host.endswith((".local", ".internal", ".test"))
    ):
        raise AppError("COMMERCE_INVALID", {"reason": "public_https_url_required"})
    return value


SMARTSTORE_HOSTS = {"smartstore.naver.com", "m.smartstore.naver.com"}
SMARTSTORE_RESERVED = {"main", "inflow", "search", "category", "products", "sell"}
CAFE24_SUFFIXES = (".cafe24.com", ".cafe24shop.com", ".cafe24api.com")
CAFE24_RESERVED = {"www", "m", "eclogin", "user", "developers", "apidocs", "img", "echosting", "api", "help"}
SHOP_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,49}")


def _invalid_url(reason: str) -> AppError:
    return AppError("COMMERCE_INVALID", {"reason": reason})


def parse_store_url(value: str) -> dict:
    """공개 스토어·관리 주소에서 플랫폼·스토어 ID·쇼핑몰 번호를 고정 규칙으로 판별한다.

    추정하지 않는다. 연결 도메인처럼 주소만으로 몰 ID를 알 수 없으면 직접 입력을 요구한다.
    """
    raw = value.strip()
    if not raw or len(raw) > 2048 or any(ch.isspace() for ch in raw):
        raise _invalid_url("store_url_invalid")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host, port = (parts.hostname or "").lower().rstrip("."), parts.port
    except ValueError as error:
        raise _invalid_url("store_url_invalid") from error
    if parts.scheme not in {"https", "http"} or parts.username or parts.password:
        raise _invalid_url("store_url_invalid")
    if port not in (None, 80, 443):
        raise _invalid_url("store_url_invalid")
    segments = [s for s in parts.path.split("/") if s]
    query = parse_qs(parts.query)
    if host in SMARTSTORE_HOSTS:
        slug = segments[0].lower() if segments else ""
        if not SHOP_ID.fullmatch(slug) or slug in SMARTSTORE_RESERVED:
            raise _invalid_url("smartstore_store_url_required")
        return {
            "platform": "smartstore",
            "external_id": slug,
            "shop_no": 1,
            "shop_no_source": "not_applicable",
        }
    if host == "sell.smartstore.naver.com":
        # 판매자센터 주소에는 스토어 고유 주소가 없다. 공개 스토어 주소를 받는다.
        raise _invalid_url("smartstore_store_url_required")
    if host.endswith(CAFE24_SUFFIXES):
        labels = host.split(".")
        mall = labels[1] if labels[0] == "m" and len(labels) == 4 else labels[0]
        if len(labels) not in (3, 4) or mall in CAFE24_RESERVED or not SHOP_ID.fullmatch(mall):
            raise _invalid_url("cafe24_mall_url_required")
        shop_no, source = 1, "default"
        match = re.search(r"(?:^|/)shop([1-9][0-9]{0,3})(?:/|$)", parts.path)
        if match:
            shop_no, source = int(match.group(1)), "url_path"
        elif query.get("shop_no"):
            candidate = query["shop_no"][0]
            if not re.fullmatch(r"[1-9][0-9]{0,3}", candidate):
                raise _invalid_url("cafe24_shop_no_invalid")
            shop_no, source = int(candidate), "url_query"
        if shop_no > 1000:
            raise _invalid_url("cafe24_shop_no_invalid")
        return {"platform": "cafe24", "external_id": mall, "shop_no": shop_no, "shop_no_source": source}
    raise _invalid_url("custom_domain_requires_mall_id")


def parse_cafe24_product_url(value: str) -> dict:
    """카페24 상품 주소의 몰 ID·쇼핑몰 번호·상품번호. 공개 주소와 관리 화면의 상품번호는 같다."""
    shop = parse_store_url(value)
    if shop["platform"] != "cafe24":
        raise _invalid_url("smartstore_origin_product_no_required")
    parts = urlsplit(value.strip() if "://" in value else "https://" + value.strip())
    numbers = parse_qs(parts.query).get("product_no") or []
    match = re.search(r"/product/[^/]+/([1-9][0-9]{0,18})(?:/|$)", parts.path)
    candidates = set(numbers) | ({match.group(1)} if match else set())
    if len(candidates) != 1 or not re.fullmatch(r"[1-9][0-9]{0,18}", next(iter(candidates))):
        raise _invalid_url("product_no_not_found")
    return {**shop, "product_no": candidates.pop()}


def check_fields(platform: str, values: dict | list) -> None:
    if not values or not set(values).issubset(FIELDS[platform]):
        raise AppError("COMMERCE_INVALID", {"reason": "unsupported_field"})
    if isinstance(values, dict) and any(not isinstance(v, str) or len(v) > 200000 for v in values.values()):
        raise AppError("COMMERCE_INVALID", {"reason": "invalid_field_value"})


def verified_facts(facts: list[FactInput], identity: str) -> list[dict]:
    result = {}
    for fact in facts:
        if fact.identity.strip() != identity.strip() or fact.value not in fact.quote:
            raise AppError("COMMERCE_INVALID", {"reason": "product_or_quote_mismatch"})
        public_url(fact.source_url)
        check_quantity(fact.key, fact.value, fact.quote)
        if fact.key in result and result[fact.key]["value"] != fact.value:
            raise AppError("COMMERCE_INVALID", {"reason": "conflicting_fact", "field": fact.key})
        result[fact.key] = {**fact.model_dump(mode="json"), "source": "seller_supplied_quote"}
    return list(result.values())


def source_text(value: str) -> str:
    from selectolax.lexbor import LexborHTMLParser

    tree = LexborHTMLParser(value)
    for node in tree.css("script, style, noscript, iframe"):
        node.decompose()
    return (tree.body.text(separator=" ", strip=True) if tree.body else tree.text(separator=" ", strip=True))[
        :80000
    ]


# 사용·보관·주의 소제목에 모으는 사실. 나머지는 상품 사양에 둔다.
USE_KEYS = {"serving", "care", "storage", "allergens"}
# 상품 자체 원본(기존 본문)에서 읽은 사실. 관리 화면·API 주소는 공개 출처로 표시하지 않는다.
OWN_SOURCES = {"api", "browser"}
QUOTE_LIMIT = 300
# 실계정 저장·재조회로 확인한 태그만 쓰는 플랫폼. 스마트스토어는 div·p·h2·h3·img만 확인했다.
PLAIN_PLATFORMS = {"smartstore"}


def _josa(word: str, pair: tuple[str, str] = ("은", "는")) -> str:
    """마지막 글자에 받침이 있으면 앞 조사, 없으면 뒤 조사."""
    last = word.rstrip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return pair[0] if (ord(last) - 0xAC00) % 28 else pair[1]
    return pair[0]


def _source_label(fact: dict) -> str:
    if fact.get("source") == "owner_answer":
        return "판매자 확인"
    if fact.get("source") in OWN_SOURCES or not fact.get("source_url"):
        return "판매자 상품 정보"
    try:
        public_url(fact["source_url"])
    except AppError:
        return "판매자 상품 정보"
    return (urlsplit(fact["source_url"]).hostname or "").removeprefix("www.")


def _clip(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def summary_line(identity: str, keys: list[str], by_key: dict) -> str:
    """요약 문단. 새 문구를 만들지 않고 상품명과 구매 판단 순서 앞쪽 사실 3개를 잇는다."""
    head = " · ".join(f"{LABELS[k]} {by_key[k]['value']}" for k in keys[:3])
    return ". ".join(part for part in (identity.strip(), head) if part)


def facts_section(platform: str, identity: str, keys: list[str], by_key: dict, *, json_ld: bool) -> str:
    """상세 설명 끝에 붙이는 seelo 영역. 화면에 보이는 사실과 같은 값만 기계용 형식으로 넣는다."""
    plain = platform in PLAIN_PLATFORMS
    e = html.escape
    spec = [k for k in keys if k not in USE_KEYS]
    use = [k for k in keys if k in USE_KEYS]

    def rows(group: list[str]) -> str:
        if plain:
            return "".join(
                f"<p>{e(LABELS[k])}: {e(by_key[k]['value'])} (출처: {e(_source_label(by_key[k]))})</p>"
                for k in group
            )
        items = "".join(
            f"<dt>{e(LABELS[k])}</dt><dd>{e(by_key[k]['value'])} "
            f"(출처: <cite>{e(_source_label(by_key[k]))}</cite>)</dd>"
            for k in group
        )
        return f"<dl>{items}</dl>"

    out = ['<section data-seelo="product-facts"><h2>상품 정보</h2>']
    out.append(f"<p>{e(summary_line(identity, keys, by_key))}</p>")
    if spec:
        out.append(f"<h3>상품 사양</h3>{rows(spec)}")
    if use:
        out.append(f"<h3>사용·보관·주의</h3>{rows(use)}")
    answered = [k for k in keys if by_key[k].get("source") == "owner_answer"]
    if answered:
        out.append("<h3>자주 묻는 질문</h3>")
        for k in answered:
            label = LABELS[k]
            out.append(f"<p>Q. {e(label)}{_josa(label)} 어떻게 되나요?</p><p>A. {e(by_key[k]['value'])}</p>")
    if not plain:
        # 외부 자료의 원문 인용만 접어 둔다. 기존 본문에서 읽은 문장은 이미 화면에 있으므로 넣지 않는다.
        quotes = []
        for k in keys:
            fact = by_key[k]
            if fact.get("source") in OWN_SOURCES | {"owner_answer"}:
                continue
            item = (_source_label(fact), _clip(fact.get("quote") or "", QUOTE_LIMIT))
            if item[1] and item not in quotes:
                quotes.append(item)
        if quotes:
            body = "".join(f"<p><cite>{e(src)}</cite>: “{e(text)}”</p>" for src, text in quotes)
            out.append(f"<details><summary>자료 원문 보기</summary>{body}</details>")
        if json_ld:
            data = {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": identity.strip(),
                "additionalProperty": [
                    {"@type": "PropertyValue", "name": LABELS[k], "value": by_key[k]["value"]} for k in keys
                ],
            }
            # 판매자 값이 스크립트 경계를 닫지 못하게 <, >, &를 유니코드 이스케이프로 바꾼다.
            text = json.dumps(data, ensure_ascii=False)
            text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            out.append(f'<script type="application/ld+json">{text}</script>')
    out.append("</section>")
    return "".join(out)


def short_value(field: str, identity: str, keys: list[str], by_key: dict) -> str:
    """짧은 칸의 값. 사실 값만 쓰고 칸마다 길이 한도를 지킨다."""
    lines = [f"{LABELS[k]}: {by_key[k]['value']}" for k in keys]
    if field == "seo.meta_title":
        # 상품명 | 핵심 사양 값. 60자를 넘는 값은 건너뛰고 다음 값을 본다.
        limit = 60
        parts = [identity.strip()[:limit]] if identity.strip() else []
        for k in keys:
            if len(" | ".join([*parts, by_key[k]["value"].strip()])) <= limit:
                parts.append(by_key[k]["value"].strip())
        return " | ".join(parts)
    if field in {"seo.meta_description", "simple_description"}:
        limit = 155 if field == "seo.meta_description" else 255
        return _clip(summary_line(identity, keys, by_key), limit)
    if field == "seo.meta_keywords":
        words = [identity.strip()] if identity.strip() else []
        for k in keys:
            value = by_key[k]["value"].strip()
            if len(value) <= 30 and value not in words:
                words.append(value)
        selected: list[str] = []
        for word in words:
            if len(",".join([*selected, word])) <= 255:
                selected.append(word)
        return ",".join(selected)
    limit = 50 if field == "summary_description" else 255
    selected = []
    for line in lines:
        if len(" · ".join([*selected, line])) <= limit:
            selected.append(line)
    return " · ".join(selected)


def draft(
    platform: str,
    current: dict[str, str],
    facts: list[dict],
    fields: list[str],
    required: list[str],
    asked: list[str],
    order: list[str],
    *,
    editor_conversion: bool,
    question_limit: int | None = None,
    product_name: str | None = None,
    json_ld: bool = False,
) -> tuple[list[dict], list[dict], list[str], list[str]]:
    check_fields(platform, fields)
    by_key = {f["key"]: f for f in facts}
    keys = [k for k in dict.fromkeys([*order, *by_key]) if k in by_key]
    # 화면·검색 문구에는 상품명을 쓴다. identity의 `상품명 | 모델명` 중 모델명은 사양 칸에서 다룬다.
    fallback = next((f["identity"] for f in facts if f.get("identity")), "")
    name = (product_name or fallback.split(" | ")[0]).strip()
    lines = [f"{LABELS[k]}: {by_key[k]['value']}" for k in keys]
    evidence = [by_key[k] for k in keys if k in by_key]
    missing = list(dict.fromkeys(k for k in required if k not in by_key))
    # 한 번에 미해결 사실 최대 두 개만 묻는다. 누적 상한은 별도 운영 결정으로만 설정한다.
    outstanding = [k for k in asked if k in missing]
    capacity = max(0, 2 - len(outstanding))
    if question_limit is not None:
        capacity = min(capacity, max(0, question_limit - len(asked)))
    candidates = [k for k in missing if k not in asked]
    asked = list(dict.fromkeys([*asked, *candidates[:capacity]]))
    questions = [
        {"field": k, "text": f"이 상품의 {LABELS[k]} 정보를 알려 주세요."} for k in asked if k in missing
    ]
    deferred = [f"fact:{k}" for k in missing]
    changes = []
    for field in dict.fromkeys(fields):
        before = current.get(field, "")
        if not lines:
            deferred.append(field)
            continue
        if field in {"description", "mobile_description"}:
            section = facts_section(platform, name, keys, by_key, json_ld=json_ld)
            # 기존 이미지·링크·편집기 HTML을 지우거나 재구성하지 않는다.
            pattern = r'<section data-seelo="product-facts">.*?</section>'
            proposed = (
                re.sub(pattern, lambda _, replacement=section: replacement, before, flags=re.DOTALL)
                if re.search(pattern, before, re.DOTALL)
                else before + "\n" + section
            )
        elif field == "attributes":
            proposed = json.dumps({k: by_key[k]["value"] for k in keys if k in by_key}, ensure_ascii=False)
        else:
            # 원래 있는 요약·SEO를 짧은 새 문장으로 덮어쓰지 않는다.
            proposed = before or short_value(field, name, keys, by_key)
        if not proposed or proposed == before:
            continue
        manual = field == "attributes" or (platform == "smartstore" and not editor_conversion)
        changes.append(
            {
                "field": field,
                "before": before,
                "proposed": proposed,
                "evidence": evidence,
                "method": "manual" if manual else "api",
                "reason": "editor_conversion_requires_approval"
                if manual and field == "description"
                else None,
            }
        )
    return changes, questions, deferred, asked
