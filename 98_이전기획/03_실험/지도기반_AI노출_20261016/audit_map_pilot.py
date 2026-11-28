"""Derive audit tables without changing any recorded CLI attempt.

Tool completion, a map URL, and a model's own access claim are not body-access proof.
This audit deliberately leaves direct access unverified pending content-level review.
"""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent


def write_csv(name, rows, fields):
    with (ROOT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def normalize_url(url):
    try:
        p = urlsplit(url or '')
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), p.query, ''))
    except ValueError:
        return ''


def map_origin(url):
    try:
        p = urlsplit(url or '')
        host, path = (p.hostname or '').lower(), p.path.lower()
    except ValueError:
        return ''
    if host in {'map.naver.com', 'm.map.naver.com', 'm.place.naver.com', 'pcmap.place.naver.com', 'naver.me'}:
        return 'naver'
    if host in {'map.kakao.com', 'm.map.kakao.com', 'place.map.kakao.com', 'kko.to'}:
        return 'kakao'
    if (host in {'google.com', 'www.google.com', 'maps.google.com', 'google.co.kr', 'www.google.co.kr'}
            and (path.startswith('/maps') or host == 'maps.google.com')) or host in {'maps.app.goo.gl', 'goo.gl'}:
        return 'google'
    return ''


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_strings(v)


def events_from(path):
    events = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def main():
    attempts_path = ROOT / 'attempts.jsonl'
    original_hash = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
    attempts = [json.loads(l) for l in attempts_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    # Latest attempt is the analysis record; every attempt remains in the original journal.
    latest = {r['run_id']: r for r in sorted(attempts, key=lambda x: (x['run_id'], x['attempt']))}
    runs, recommendations, sources, trace = [], [], [], []
    for run_id, r in sorted(latest.items()):
        events = events_from(Path(r['raw_path']))
        denied = r.get('denied_actions', []) or [a for e in events for a in e.get('result', {}).get('denied_actions', [])]
        status = 'tool_permission_denied' if denied and not r.get('parsed_answer') else r['status']
        tool_urls, errors, returned_target = set(), [], []
        for event_index, e in enumerate(events):
            item = e.get('item', {})
            if e.get('type') == 'item.completed' and item.get('type') == 'web_search':
                for result_index, result in enumerate(item.get('results', [])):
                    url, title, snippet = result.get('url') or '', result.get('title') or '', result.get('snippet') or ''
                    origin = map_origin(url)
                    is_error = bool(re.search(r'Internal\s*Error|error|robots\.txt|blocked|not safe', title, re.I))
                    if url:
                        tool_urls.add(normalize_url(url))
                    if is_error:
                        errors.append(title)
                    if origin == r['map_id']:
                        returned_target.append(url)
                    trace.append({'run_id': run_id, 'event_index': event_index, 'result_index': result_index,
                                  'tool': 'web_search', 'event_state': 'item.completed',
                                  'action_type': item.get('action', {}).get('type', ''),
                                  'url': url, 'title': title, 'snippet': snippet,
                                  'map_origin': origin, 'is_requested_map': origin == r['map_id'],
                                  'error_title_observed': is_error, 'body_access_verified': False,
                                  'evidence_scope': 'returned_result_metadata_not_full_body'})
            step = e.get('step_update', {})
            if step.get('tool_name') and step.get('state') == 'DONE':
                params = step.get('tool_info', {}).get('parameters', {})
                urls = [s for s in walk_strings(params) if s.startswith(('https://', 'http://'))]
                trace.append({'run_id': run_id, 'event_index': event_index, 'result_index': '',
                              'tool': step['tool_name'], 'event_state': 'DONE', 'action_type': '',
                              'url': ' | '.join(urls), 'title': '', 'snippet': json.dumps(params, ensure_ascii=False),
                              'map_origin': ' | '.join(filter(None, (map_origin(u) for u in urls))),
                              'is_requested_map': any(map_origin(u) == r['map_id'] for u in urls),
                              'error_title_observed': '', 'body_access_verified': False,
                              'evidence_scope': 'tool_request_only_result_body_not_in_stream'})
        answer = r.get('parsed_answer') or {}
        restaurants = answer.get('restaurants', [])
        runs.append({'run_id': run_id, 'backend': r['backend'], 'map_id': r['map_id'], 'area_id': r['area_id'],
                     'requested_model': r['requested_model'], 'reported_models': ' | '.join(r.get('reported_models', [])),
                     'recorded_status': r['status'], 'audited_status': status,
                     'recommendation_count': len(restaurants), 'elapsed_seconds': r['elapsed_seconds'],
                     'web_search_observed': r['web_search_observed'], 'denied_action_count': len(denied),
                     'tool_error_titles': ' | '.join(sorted(set(errors))),
                     'target_map_result_urls': ' | '.join(sorted(set(returned_target))),
                     'map_body_access_verified': False,
                     'audit_access_class': 'technical_unavailable' if status != 'completed' else 'other_sources_no_verified_map_body',
                     'access_note_self_report': answer.get('access_note', ''), 'raw_path': r['raw_path']})
        for rec_index, rec in enumerate(restaurants, 1):
            row_id = f'{run_id}:N{rec_index}'
            fields = rec.get('map_fields_read') or []
            level = rec.get('source_level', 'unverified')
            recommendations.append({'recommendation_id': row_id, 'run_id': run_id, 'backend': r['backend'],
                                    'map_id': r['map_id'], 'area_id': r['area_id'], 'rank': rec.get('rank', rec_index),
                                    'name_as_returned': rec.get('name'), 'branch_as_returned': rec.get('branch'),
                                    'address_as_returned': rec.get('address'), 'reason': rec.get('reason'),
                                    'source_level_self_report': level, 'map_url': rec.get('map_url'),
                                    'map_fields_self_report': json.dumps(fields, ensure_ascii=False),
                                    'map_text_excerpt': rec.get('map_text_excerpt'),
                                    'field_attribution_conflict': bool(fields) and level == 'other_sources',
                                    'entity_verified': False, 'map_body_access_verified': False,
                                    'writing_effect_analysis_eligible': False})
            cited = [(u, 'source') for u in rec.get('sources', []) if u]
            if rec.get('map_url'):
                cited.append((rec['map_url'], 'map_url'))
            for url, role in cited:
                origin = map_origin(url)
                sources.append({'recommendation_id': row_id, 'run_id': run_id, 'role': role, 'url': url,
                                'map_origin': origin, 'is_requested_map': origin == r['map_id'],
                                'url_seen_in_returned_tool_metadata': normalize_url(url) in tool_urls if r['backend'] == 'codex' else '',
                                'verification_scope': 'url_metadata_only' if normalize_url(url) in tool_urls else 'reported_url_not_independently_verified',
                                'map_body_access_verified': False})
    write_csv('runs_audited.csv', runs, list(runs[0]))
    write_csv('recommendations.csv', recommendations, list(recommendations[0]))
    write_csv('source_audit.csv', sources, list(sources[0]))
    write_csv('tool_trace.csv', trace, list(trace[0]))
    summaries = []
    for map_id in ['naver', 'kakao', 'google']:
        for backend in ['codex', 'agy']:
            group = [r for r in runs if r['map_id'] == map_id and r['backend'] == backend]
            summaries.append({'map_id': map_id, 'backend': backend, 'attempted_cells': len(group),
                              'completed': sum(r['audited_status'] == 'completed' for r in group),
                              'technical_unavailable': sum(r['audited_status'] != 'completed' for r in group),
                              'recommendations': sum(r['recommendation_count'] for r in group),
                              'map_body_access_verified': sum(r['map_body_access_verified'] for r in group)})
    write_csv('pilot_summary.csv', summaries, list(summaries[0]))
    # Exact model-returned names only. No unverified alias or branch merging.
    appearances = []
    for area in ['MD', 'SS', 'MW']:
        denom = sum(r['area_id'] == area and r['audited_status'] == 'completed' for r in runs)
        names = {rec['name_as_returned'] for rec in recommendations if rec['area_id'] == area}
        for name in names:
            rows = [rec for rec in recommendations if rec['area_id'] == area and rec['name_as_returned'] == name]
            n = len({rec['run_id'] for rec in rows})
            appearances.append({'area_id': area, 'name_as_returned': name, 'responses_with_exact_name': n,
                                'completed_responses_in_area': denom, 'descriptive_share': round(n / denom, 4),
                                'branches_as_returned': ' | '.join(sorted({x['branch_as_returned'] or '' for x in rows})),
                                'map_criteria': ' | '.join(sorted({x['map_id'] for x in rows})),
                                'entity_verified': False, 'interpretation': 'other_source_pilot_unequal_model_mix_not_writing_effect'})
    appearances.sort(key=lambda x: (x['area_id'], -x['responses_with_exact_name'], x['name_as_returned']))
    write_csv('pilot_name_appearances.csv', appearances, list(appearances[0]))
    manifest = list(csv.DictReader((ROOT / 'run_manifest.csv').open(encoding='utf-8-sig')))
    prompts_path = ROOT / 'prompts.json'
    frozen = json.loads((ROOT / 'design_freeze.json').read_text(encoding='utf-8'))
    protected = {
        'consumer_results.csv': '149f1bb971981f3d5f5aec50a5f6ae466d44593c16af790058d1cc0ea9cfbdc3',
        'consumer_failures.csv': 'e2024bbd9096d269a455e38a170091aaefba7c998280c205d86b887411ecd80e',
    }
    protected_hash_checks = {
        name: hashlib.sha256((ROOT.parent / 'ai-visibility-experiment' / 'data' / name).read_bytes()).hexdigest() == expected
        for name, expected in protected.items()
    }
    validation = {
        'attempt_count': len(attempts), 'unique_cells': len(runs), 'planned_cells': len(manifest),
        'all_pilot_cells_attempted': {r['run_id'] for r in runs} == {r['run_id'] for r in manifest},
        'no_duplicate_pilot_attempts': len(attempts) == len(runs),
        'raw_journal_sha256': original_hash,
        'raw_journal_unchanged_by_audit': original_hash == hashlib.sha256(attempts_path.read_bytes()).hexdigest(),
        'prompt_hash_matches_freeze': hashlib.sha256(prompts_path.read_bytes()).hexdigest() == frozen['prompts_sha256'],
        'audited_status_counts': dict(Counter(r['audited_status'] for r in runs)),
        'recommendation_rows': len(recommendations),
        'recommendation_count_matches_runs': len(recommendations) == sum(r['recommendation_count'] for r in runs),
        'self_report_source_levels': dict(Counter(r['source_level_self_report'] for r in recommendations)),
        'verified_map_body_runs': sum(r['map_body_access_verified'] for r in runs),
        'field_attribution_conflict_rows': sum(r['field_attribution_conflict'] for r in recommendations),
        'direct_body_exposure_rate': None,
        'direct_body_exposure_rate_reason': 'No verified map-body trials; undefined, not zero restaurant exposure.',
        'predictive_model_fit': False, 'causal_claim': False, 'consumer_data_combined': False,
        'protected_consumer_hash_matches_prior_baseline': protected_hash_checks,
        'audit_rule': 'No source-body excerpts delivered in auditable target-map results; metadata, final claims, and browser-side reads cannot verify CLI body access.',
    }
    assert validation['all_pilot_cells_attempted'] and validation['recommendation_count_matches_runs']
    assert validation['prompt_hash_matches_freeze'] and validation['raw_journal_unchanged_by_audit']
    assert all(protected_hash_checks.values())
    (ROOT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
