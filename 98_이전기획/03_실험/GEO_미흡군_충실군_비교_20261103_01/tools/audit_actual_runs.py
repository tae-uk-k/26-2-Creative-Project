"""Preserve auditable projections of CLI JSONL without accepting responses.

Run repeatedly during measurement. Existing per-attempt audit files are never
overwritten. Every recommendation row remains excluded pending adjudication.
No model-generated judgement is substituted for map detail access evidence.
"""
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'analysis' / '실측_검수자료_20261103_01'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def csv_new(path, data, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(data)


def is_map(url):
    p = urlparse(url)
    h = p.netloc.lower()
    if h in ['place.map.kakao.com', 'map.kakao.com', 'maps.kakao.com']:
        return 'kakao'
    if h in ['maps.google.com', 'maps.app.goo.gl', 'goo.gl'] or h.endswith('google.com') and p.path.startswith('/maps'):
        return 'google'
    return ''


def plain(value):
    value = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', value)
    return re.sub(r'[*_`]', '', value).strip()


def extract_recommendations(final):
    """Extract the first main recommendation table, otherwise numbered items.

    This is an extraction, not identity or fact validation. Source-link tables
    and prose recaps are not counted as additional restaurant appearances.
    """
    lines = final.splitlines()
    collected = []
    headers = None
    for line in lines:
        if not line.strip().startswith('|'):
            if collected:
                break
            continue
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        if all(re.fullmatch(r'[:\- ]+', x or ' ') for x in cells):
            continue
        if headers is None:
            if re.search(r'상호|음식점|식당|매장|가게|추천', ' '.join(cells)) and not all(re.search(r'지도|매장', x) for x in cells):
                headers = cells
            continue
        # A table listing map links is not the main recommendation table.
        if any('카카오' in x or '구글 지도' in x for x in headers) and not any('메뉴' in x or '추천 이유' in x for x in headers):
            headers = None
            continue
        first = cells[0]
        if re.fullmatch(r'\d+[.)]?', plain(first)) and len(cells) > 1:
            first = cells[1]
        bold = re.findall(r'\*\*([^*]+)\*\*', first)
        name = plain(bold[0] if bold else re.split(r'\s+[—–]\s+|<br\s*/?>', first)[0])
        if not name or re.search(r'상호|정확한|음식점·|식당명|가게명', name):
            continue
        collected.append(dict(rank=len(collected)+1, name=name, raw_row=line, source_urls=';'.join(re.findall(r'\]\((https?://[^\s)]+)\)', line))))
    if collected:
        return collected, 'first_recommendation_table'
    for line in lines:
        m = re.match(r'^\s*(?:#{1,4}\s*)?(\d+)[.)]\s*(.+)', line)
        if not m:
            continue
        value = m[2]
        bold = re.match(r'\*\*([^*]+)\*\*', value)
        name = plain(bold[1] if bold else re.split(r'\s+[—–:]\s*', value)[0])
        if name and len(name) < 75:
            collected.append(dict(rank=int(m[1]), name=name, raw_row=line, source_urls=';'.join(re.findall(r'\]\((https?://[^\s)]+)\)', line))))
    return collected, 'numbered_lines' if collected else 'unparsed_requires_review'


def audit(manifest):
    aid = manifest['attempt_id']
    output = DEST / (aid + '.audit.json')
    raw = ROOT / manifest['raw_path']
    assert sha(raw) == manifest['raw_sha256'], 'Original raw hash changed'
    if output.exists():
        saved = json.loads(output.read_text(encoding='utf-8'))
        assert saved['raw_sha256'] == sha(raw)
        return saved
    events, bad = [], []
    for n, line in enumerate(raw.read_text(encoding='utf-8').splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(n)
    messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'agent_message']
    final = messages[-1] if messages else ''
    searches = [e['item'] for e in events if e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'web_search']
    forbidden = [e['item'] for e in events if e.get('type') == 'item.completed' and e.get('item', {}).get('type') not in ['web_search', 'agent_message', 'reasoning', 'plan_update', None]]
    links, errors, actions = [], [], []
    for i in searches:
        action = i.get('action', {})
        request_url = action.get('url', '')
        actions.append(dict(event_id=i.get('id'), action=action, request_map=is_map(request_url)))
        for result in i.get('results', []):
            title, snippet = result.get('title', ''), result.get('snippet', '')
            r = dict(event_id=i.get('id'), action_type=action.get('type'), requested_url=request_url,
                     result_url=result.get('url', ''), ref_id=result.get('ref_id'), title=title, snippet=snippet,
                     result_map=is_map(result.get('url', '')), scope='search_snippet' if action.get('type') == 'search' else 'open_result_metadata')
            links.append(r)
            if re.search(r'Internal Error|Access Denied|Forbidden|robots\.txt|blocked', title+' '+snippet, re.I) and action.get('type') != 'search':
                errors.append(r)
    recs, method = extract_recommendations(final)
    result = dict(attempt_id=aid, cell_id=manifest['cell_id'], raw_sha256=sha(raw), process_status=manifest['process_status'], returncode=manifest['returncode'], started_at=manifest['started_at'], ended_at=manifest['ended_at'],
                  thread_ids=[e.get('thread_id') for e in events if e.get('type') == 'thread.started'], invalid_json_lines=bad,
                  provider_errors=[e for e in events if e.get('type') in ['error', 'turn.failed']], forbidden_tool_items=forbidden,
                  search_event_count=len(searches), tool_actions=actions, source_events=links, error_results=errors,
                  final_text=final, final_urls=re.findall(r'\]\((https?://[^\s)]+)\)', final),
                  self_report_failure_lines=[line for line in final.splitlines() if re.search(r'차단|읽지 못|못했|못했습|완료하지 못|교차 검증|직접 확인|JavaScript|자바스크립트', line)],
                  recommendation_rows=recs, extraction_method=method,
                  automatic_valid=False, body_access_judgement='requires_manual_review',
                  note='도구 메타데이터와 검색 스니펫은 지도 상세 본문 검증으로 대체하지 않음. 대체 출처 추천은 유효 지도 비교 결과가 아님.')
    write_json(output, result)
    with (DEST / (aid + '.final.txt')).open('x', encoding='utf-8') as f:
        f.write(final)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', help='New snapshot name, never overwritten')
    args = parser.parse_args()
    DEST.mkdir(exist_ok=True)
    manifests = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'raw').glob('*.manifest.json'))]
    records = [audit(m) for m in manifests]
    if args.snapshot:
        dest = DEST / args.snapshot
        dest.mkdir(exist_ok=False)
        summaries = []
        mentions = []
        source_events = []
        for r in records:
            summaries.append(dict(attempt_id=r['attempt_id'], cell_id=r['cell_id'], process_status=r['process_status'], started_at=r['started_at'], ended_at=r['ended_at'], thread_id=';'.join(r['thread_ids']), search_event_count=r['search_event_count'], tool_error_results=len(r['error_results']), forbidden_tool_count=len(r['forbidden_tool_items']), extracted_rows=len(r['recommendation_rows']), failure_self_report=' | '.join(r['self_report_failure_lines']), audit_file=str((DEST/(r['attempt_id']+'.audit.json')).relative_to(ROOT))))
            for row in r['recommendation_rows']:
                mentions.append(dict(attempt_id=r['attempt_id'], cell_id=r['cell_id'], **row, identity_status='requires_review', fact_validation='not_validated', included_in_rate=False))
            for row in r['source_events']:
                source_events.append(dict(attempt_id=r['attempt_id'], cell_id=r['cell_id'], **row))
        if summaries:
            csv_new(dest / '실행별_검수요약.csv', summaries, list(summaries[0]))
        csv_new(dest / '추천_자동추출_검수대기.csv', mentions, list(mentions[0]) if mentions else ['attempt_id','cell_id','rank','name','raw_row','source_urls','identity_status','fact_validation','included_in_rate'])
        csv_new(dest / '출처_도구이벤트.csv', source_events, list(source_events[0]) if source_events else ['attempt_id','cell_id','event_id'])
        write_json(dest / '스냅샷상태.json', dict(observed_at_utc=datetime.now(timezone.utc).isoformat(), completed_attempts=len(records), parsed_recommendation_rows=len(mentions), all_rows_require_identity_and_fact_review=True, valid_status_assigned=False))
    print(json.dumps(dict(completed_attempts=len(records), parsed_rows=sum(len(r['recommendation_rows']) for r in records), explicit_tool_errors=sum(bool(r['error_results']) for r in records), provider_failure_attempts=sum(bool(r['provider_errors']) for r in records), final_texts_saved=len(records)), ensure_ascii=False))


if __name__ == '__main__':
    main()
