"""Uniform public Diningcode snapshot; no exposure labels are read here."""
import csv
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
sys.path.insert(0, str(BASE))
from probe_sources import fetch


def load_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def extract(page, selection, original):
    text = page.get('text', '')
    road = selection['expected_road']
    compact = re.sub(r'\s+', '', text.split('의 사진', 1)[0])
    count = re.search(r'\(([\d,]+)명의 평가\)', text)
    top = re.search(r'([\d.]+)\s*\(([\d,]+)명의 평가\)', text)
    body = re.search(r'방문자 리뷰\s*([\d.]+)\s*([\d,]+)건\s*의 리뷰', text)
    row = {
        'entity_id': selection['entity_id'], 'name_ko': original['name_ko'],
        'area': original['area'], 'profile_url': page.get('url', ''),
        'profile_title': page.get('title', ''),
        'retrieved_at_utc': page.get('checked_at_utc', ''),
        'access_status': page.get('access_status', 'not_found'),
        'http_status': page.get('http_status', ''),
        'expected_road': road,
        'road_match': int(bool(road) and re.sub(r'\s+', '', road) in compact),
        'name_review_note': selection['name_review_note'],
        'diningcode_review_count': int(count[1].replace(',', '')) if count else '',
        'diningcode_rating': float(top[1]) if top else '',
        'review_aggregate_crosscheck': int(bool(top and body) and float(top[1]) == float(body[1]) and top[2].replace(',', '') == body[2].replace(',', '')),
        'display_photo_count': '', 'profile_menu_items': '',
        'google_review_count': '', 'google_rating': '', 'recent_review_age_days': '',
        'actual_same_day_business_verified': 0,
        'page_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
    }
    if '의 사진' in text:
        photo = text.split('의 사진', 1)[1].split('사진 더보기', 1)[0]
        counts = re.findall(r'(음식|실내|실외|메뉴ㆍ정보|메뉴·정보|메뉴정보)\s*\((\d+)\)', photo)
        if counts:
            row['display_photo_count'] = sum(int(n) for _, n in counts)
            row['photo_count_components'] = '|'.join(f'{k}:{v}' for k, v in counts)
    menus = []
    if '메뉴정보' in text and '방문자 리뷰' in text:
        menu = text.split('메뉴정보', 1)[1].split('방문자 리뷰', 1)[0]
        # Parse only the structured menu section; never use embedded blog text.
        lines = menu.splitlines()
        for index, line in enumerate(lines):
            if re.fullmatch(r'[\d,]+', line) and index + 1 < len(lines) and lines[index + 1] == '원':
                if index and 500 <= int(line.replace(',', '')) <= 500000:
                    menus.append({'entity_id': selection['entity_id'], 'menu_name': lines[index - 1],
                                  'price_krw': int(line.replace(',', '')), 'source_url': page['url']})
            elif re.fullmatch(r'[\d,]+\s*원', line) and index:
                menus.append({'entity_id': selection['entity_id'], 'menu_name': lines[index - 1],
                              'price_krw': int(re.sub(r'\D', '', line)), 'source_url': page['url']})
        row['profile_menu_items'] = len(menus)
    return row, menus


def main():
    originals = {r['restaurant_id']: r for r in load_csv(BASE.parent.parent / 'restaurants.csv')}
    selections = load_csv(OUT / 'profile_selection.csv')
    assert len(selections) == 30 and set(originals) == {r['entity_id'] for r in selections}
    urls = ['https://www.diningcode.com/profile.php?rid=' + r['profile_rid'] for r in selections if r['profile_rid']]
    cache = OUT / 'profile_pages_live_2026-10-14.jsonl'
    if cache.exists():
        pages = [json.loads(line) for line in cache.read_text(encoding='utf-8').splitlines()]
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = list(pool.map(fetch, urls))
        cache.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in pages), encoding='utf-8')
    lookup = {r['url']: r for r in pages}
    missing = [url for url in urls if url not in lookup]
    if missing:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages.extend(pool.map(fetch, missing))
        cache.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in pages), encoding='utf-8')
        lookup = {r['url']: r for r in pages}
    output, menus = [], []
    for selection in selections:
        url = 'https://www.diningcode.com/profile.php?rid=' + selection['profile_rid'] if selection['profile_rid'] else ''
        page = lookup.get(url, {'access_status': 'profile_not_found_after_search'})
        row, items = extract(page, selection, originals[selection['entity_id']])
        output.append(row)
        menus.extend(items)
    write_csv('profile_snapshot.csv', output)
    write_csv('menu_prices_raw.csv', menus)
    print(json.dumps({'stores_attempted': len(output), 'profiles_found': len(urls),
                     'reviews_collected': sum(r['diningcode_review_count'] != '' for r in output),
                     'roads_matched': sum(r['road_match'] for r in output),
                     'structured_price_items': len(menus)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
