"""Read public source pages. Automated checks are screening, not claim verification.

Citation-derived availability counts must not enter the prediction feature list.
The original cohort uses its prior-source URLs; discovery source selection is biased.
"""
from __future__ import annotations
import csv
import hashlib
import ipaddress
import json
import re
import socket
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from prepare import ROOT, baseline, freeze_registry, alias_index, match, normalize, save_csv


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.in_title = False
        self.parts = []
        self.title_parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False
    def handle_data(self, data):
        if not self.hidden:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.parts.append(value)
                if self.in_title:
                    self.title_parts.append(value)


def safe_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return ""
    if parsed.hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        return ""
    try:
        if ipaddress.ip_address(parsed.hostname).is_private:
            return ""
    except ValueError:
        pass
    if parsed.netloc.endswith(".local") or parsed.netloc.endswith(".internal"):
        return ""
    if not parsed.path.strip("/") or "grounding-api-redirect" in parsed.path or parsed.path.startswith("/maps/"):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%:@+~!$&'()*;,="), quote(parsed.query, safe="=&%+/:?@~"), ""))


def fetch(url):
    tick = time.monotonic()
    out = {"url": url, "checked_at_utc": datetime.now(timezone.utc).isoformat(), "http_status": "", "access_status": "error", "title": "", "text": "", "error": ""}
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; RestaurantResearch/1.0)", "Accept": "text/html"})
        with urlopen(request, timeout=15) as response:
            out["http_status"] = response.status
            out["final_url"] = response.url
            mime = response.headers.get_content_type()
            if mime != "text/html":
                out["access_status"] = "non_html_skipped"
            else:
                body = response.read(750000)
                encoding = response.headers.get_content_charset() or "utf-8"
                try:
                    html = body.decode(encoding, errors="replace")
                except LookupError:
                    html = body.decode("utf-8", errors="replace")
                parser = PageText()
                parser.feed(html)
                out["title"] = " ".join(parser.title_parts)
                out["text"] = "\n".join(parser.parts)[:160000]
                out["access_status"] = "accessible" if len(out["text"]) > 100 else "empty_or_js_only"
    except HTTPError as exc:
        out["http_status"], out["error"] = exc.code, str(exc)
    except Exception as exc:
        out["error"] = type(exc).__name__ + ": " + str(exc)
    out["elapsed_seconds"] = round(time.monotonic() - tick, 2)
    return out


def main():
    registry = freeze_registry()
    index = alias_index(registry)
    associations = defaultdict(dict)
    for row in registry:
        for url in row["source_urls"].split("|"):
            value = safe_url(url)
            if value:
                associations[row["entity_id"]][value] = "original_prior_listing" if row["sampling_cohort"] == "original30_preselected" else "baseline_model_citation"
    for run in baseline():
        for rec in run["recommendations"]:
            rid = match(rec, run["area"], registry, index)
            if not rid or rid.startswith(("MD-", "SS-", "MW-")):
                continue
            for url in rec.get("sources") or []:
                value = safe_url(url)
                if value and len(associations[rid]) < 3:
                    associations[rid].setdefault(value, "baseline_model_citation")
    links = [{"entity_id": rid, "url": url, "selection_origin": origin} for rid, urls in associations.items() for url, origin in list(urls.items())[:3]]
    save_csv("source_probe_manifest.csv", links)
    cache_path = ROOT / "source_pages.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cache[row["url"]] = row
    pending = sorted({row["url"] for row in links} - set(cache))
    with cache_path.open("a", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, url): url for url in pending}
        for i, future in enumerate(as_completed(futures), 1):
            row = future.result()
            cache[row["url"]] = row
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            if i % 25 == 0 or i == len(pending):
                print(json.dumps({"pages_checked": i, "pending_total": len(pending)}, ensure_ascii=False), flush=True)
    screening, identity = [], []
    for restaurant in registry:
        checked = []
        name_variants = [restaurant["name_ko"]] + restaurant["aliases"].split("|")
        name_variants = [n for n in name_variants if len(normalize(n)) >= 2 and re.search(r"[가-힣]", n)]
        for link in [link for link in links if link["entity_id"] == restaurant["entity_id"]]:
            page = cache[link["url"]]
            normalized_page, title = normalize(page["text"]), normalize(page["title"])
            name_present = any(normalize(n) in normalized_page for n in name_variants)
            name_in_title = any(normalize(n) in title for n in name_variants)
            address_signature = restaurant["address_signature_ko"]
            address_present = bool(address_signature and address_signature in normalized_page)
            text = page["text"]
            prices = re.findall(r"(?:₩\s*|KRW\s*)?([0-9]{1,3}(?:,[0-9]{3})+)\s*(?:원|won|KRW)", text, re.I)
            price_match = re.search(r".{0,70}[0-9]{1,3}(?:,[0-9]{3})+\s*(?:원|won|KRW).{0,70}", text, re.I)
            solo_match = re.search(r".{0,70}(?:혼밥|1인석|solo diner|single diner).{0,70}", text, re.I)
            row = {"entity_id": restaurant["entity_id"], "name_ko": restaurant["name_ko"], "url": page["url"], "selection_origin": link["selection_origin"], "access_status": page["access_status"], "http_status": page["http_status"], "page_title": page["title"], "name_present_anywhere": int(name_present), "name_in_title": int(name_in_title), "legacy_address_present": int(address_present), "price_text_suggested": int(bool(prices)), "price_evidence_suggested": price_match.group(0) if price_match else "", "solo_evidence_suggested": solo_match.group(0) if solo_match else "", "usable_predictor_without_review": 0, "reason": "automatic_screening_only; page may include other restaurants; source selection may depend on baseline output"}
            screening.append(row)
            checked.append(row)
        strong = [row for row in checked if row["access_status"] == "accessible" and row["name_in_title"]]
        identity.append({"entity_id": restaurant["entity_id"], "name_ko": restaurant["name_ko"], "checked_urls": len(checked), "accessible_urls": sum(row["access_status"] == "accessible" for row in checked), "name_title_matching_urls": len(strong), "identity_screening": "external_title_match_needs_branch_review" if strong else "unverified_or_unavailable", "human_verified": 0})
    save_csv("source_screening.csv", screening)
    save_csv("identity_review.csv", identity)
    print(json.dumps({"unique_urls": len(cache), "registry_candidates": len(registry), "title_matched_candidates": sum(r["name_title_matching_urls"] > 0 for r in identity)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
