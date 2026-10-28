"""Read a uniform source protocol from the original registry, not AI citations."""
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
sys.path.insert(0, str(BASE))
from probe_sources import fetch


def main():
    rows = list(csv.DictReader((BASE.parent.parent / 'restaurants.csv').open(encoding='utf-8-sig')))
    selected = []
    for row in rows:
        urls = row['verification_urls'].split('|')
        tourism = next((u for u in urls if any(d in urlsplit(u).hostname for d in ['visitseoul.net', 'visitkorea.or.kr'])), '')
        selected.append({'entity_id': row['restaurant_id'], 'source_type': 'official_tourism_registry', 'url': tourism})
        if row['own_website'] == 'yes':
            own = next((u for u in urls if not any(d in urlsplit(u).hostname for d in ['visitseoul.net', 'visitkorea.or.kr', 'guide.michelin.com', 'seoul.go.kr', 'world.nol.com', 'polle.com', 'diningcode.com', 'tripadvisor.com', 'google.com', 'koreaplate.com'])), '')
            selected.append({'entity_id': row['restaurant_id'], 'source_type': 'own_website_registry', 'url': own})
    selected += [
        {'entity_id': 'MD-R01', 'source_type': 'official_guide', 'url': 'https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/myeongdong-kyoja'},
        {'entity_id': 'MD-R02', 'source_type': 'official_guide', 'url': 'https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/hadongkwan'},
        {'entity_id': 'SS-R07', 'source_type': 'official_tourism_registry', 'url': 'https://korean.visitseoul.net/area/yournakedcheese/KOP04d1r9'},
        {'entity_id': 'MD-R10', 'source_type': 'official_tourism_registry', 'url': 'https://stage-kr.visitseoul.net/restaurants/SeongwonJeonjuKongnamulGukbap/KOPwmqzyh'},
    ]
    cache = OUT / 'reference_pages_2026-10-14.jsonl'
    pages = [json.loads(l) for l in cache.read_text(encoding='utf-8').splitlines()] if cache.exists() else []
    for page in pages:
        if 'Web firewall security policies' in page.get('text', ''):
            page['access_status'] = 'blocked_waf'
    if pages:
        cache.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in pages), encoding='utf-8')
    known = {r['url'] for r in pages}
    missing = sorted({r['url'] for r in selected if r['url']} - known)
    if missing:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for page in pool.map(fetch, missing):
                if 'Web firewall security policies' in page.get('text', ''):
                    page['access_status'] = 'blocked_waf'
                pages.append(page)
                with cache.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(page, ensure_ascii=False) + '\n')
                print(json.dumps({'reference': page['title'], 'status': page['access_status']}, ensure_ascii=False), flush=True)
    (OUT / 'reference_selection.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'selected_urls': len({r['url'] for r in selected if r['url']}), 'attempted_stores': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
