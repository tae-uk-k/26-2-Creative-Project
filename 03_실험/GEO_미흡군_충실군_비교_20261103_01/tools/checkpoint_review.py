"""Append-only archive of observed map details; never manufactures a cohort."""
import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


def csv_new(path, data, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        writer.writerows(data)


def json_new(path, data):
    with path.open('x', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    parser.add_argument('frame_version')
    args = parser.parse_args()
    dest = ROOT / 'analysis' / args.version
    dest.mkdir(exist_ok=False)
    for name in ['detail_records', 'menu_photos']:
        (dest/name).mkdir()
    observations = [json.loads(line) for line in (ROOT/'evidence/browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    registry = ROOT/'evidence/사진확인_registry_20261103_재복구.json'
    if not registry.exists():
        registry = ROOT/'evidence/사진확인_registry_20261103_후속검수.json'
    if not registry.exists():
        registry = ROOT/'evidence/사진확인_registry_20261103_복구후.json'
    if not registry.exists():
        registry = ROOT/'evidence/사진확인_registry_20261103.json'
    visual = json.loads(registry.read_text(encoding='utf-8'))
    reviewed = set(visual['visually_read_asset_ids'])
    details, photos, latest = [], {}, {}
    for index, obs in enumerate(observations, 1):
        if obs.get('kind') != 'detail':
            continue
        sid, platform, section = (obs[key] for key in ['store_id', 'platform', 'section'])
        path = dest/'detail_records'/f'{index:03d}_{sid}_{platform}_{section}.json'
        json_new(path, obs)
        row = dict(observation_index=index, store_id=sid, platform=platform, section=section,
                   observed_at=obs['observed_at'], source_url=obs['url'],
                   evidence_file=str(path.relative_to(ROOT)), sha256=sha(path))
        details.append(row)
        latest[sid, platform, section] = row
        for asset in obs.get('bundle', {}).get('assets', []):
            identity = sid, asset['id']
            if identity in photos:
                continue
            source = Path(asset['path'])
            if not source.exists():
                saved = sorted((ROOT/'analysis').glob(f"상세검수_*/menu_photos/{sid}_{asset['id']}.*"))
                if not saved:
                    raise FileNotFoundError(f"Missing observed asset: {sid} {asset['id']}")
                source = saved[-1]
            extension = '.png' if asset['contentType']=='image/png' else '.jpg'
            target = dest/'menu_photos'/f"{sid}_{asset['id']}{extension}"
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            assert sha(source) == sha(target), 'Copied asset hash mismatch'
            photos[identity] = dict(store_id=sid, asset_id=asset['id'], source_url=asset['url'],
                evidence_file=str(target.relative_to(ROOT)), sha256=sha(target),
                visually_read=asset['id'] in reviewed,
                writer_verified=False,
                is_menu_asset=asset['id']!='f84b7858d06839be',
                branch_scope_uncertain=asset['id'] in ['d27f87933c6246ee','ea978665d4ae0d74'],
                scope='Profile asset excluded from menu count' if asset['id']=='f84b7858d06839be' else 'Observed menu-board category asset; archived is not visually read; uploader is not assumed owner; branch identity may require review')
    assert reviewed <= {asset_id for sid, asset_id in photos}, 'Review registry has unarchived asset'
    csv_new(dest/'상세_근거목록.csv', details, list(details[0]))
    csv_new(dest/'사진_근거목록.csv', list(photos.values()), list(next(iter(photos.values()))))
    frame = ROOT/'analysis'/args.frame_version
    cards = records(frame/'native_cards.csv')
    candidates = records(frame/'crossmap_candidates.csv')
    profiles = []
    for sid in sorted({row['store_id'] for row in details}):
        evidence = [row for row in details if row['store_id']==sid]
        assets = [row for row in photos.values() if row['store_id']==sid]
        profiles.append(dict(store_id=sid, kakao_detail=any(row['platform']=='kakao' for row in evidence),
            google_detail=any(row['platform']=='google' for row in evidence),
            official_detail=any(row['platform']=='official' for row in evidence),
            archived_assets=len(assets), archived_photos=sum(row['is_menu_asset'] for row in assets),
            visually_read_photos=sum(row['visually_read'] and row['is_menu_asset'] for row in assets),
            group='', pair_id='', final_selection=False,
            evidence_files=';'.join(row['evidence_file'] for row in evidence)))
    csv_new(dest/'후보_상세관측.csv', profiles, list(profiles[0]))
    attempts = []
    for manifest in sorted((ROOT/'readiness').glob('*.manifest.json')):
        meta = json.loads(manifest.read_text(encoding='utf-8'))
        raw = ROOT/meta['raw_path']
        assert sha(raw)==meta['raw_sha256'], 'Raw CLI response changed'
        events = [json.loads(line) for line in raw.read_text(encoding='utf-8').splitlines()]
        webs = [event['item'] for event in events if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='web_search']
        opens = [item for item in webs if item.get('action',{}).get('type')=='open_page']
        errors = [result for item in opens for result in item.get('results',[]) if result.get('title')=='Internal Error']
        finals = [event['item']['text'] for event in events if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='agent_message']
        attempts.append(dict(attempt_id=meta['attempt_id'], started_at=meta['started_at'], ended_at=meta['ended_at'],
            returncode=meta['returncode'], raw_file=meta['raw_path'], raw_sha_verified=True,
            open_events=len(opens), internal_error_results=len(errors),
            outcome='model_failure' if meta['returncode'] else 'map_access_failure' if errors else 'requires_manual_review',
            final_response=finals[-1] if finals else '', included_in_90=False))
    json_new(dest/'CLI_중립점검.json', attempts)
    previous = ROOT.parent/'GEO_두집단_지도비교_20261103'
    preserved = records(previous/'산출물_목록_해시.csv')
    assert all(sha(previous/row['path'])==row['sha256'] for row in preserved), 'Prior study changed'
    cohort = records(ROOT/'매장_집단_매칭표.csv')
    raw_attempts = list((ROOT/'raw').glob('*.manifest.json'))
    schedule = records(ROOT/'90셀_실행계획.csv')
    assert len(schedule)==90 and len({row['cell_id'] for row in schedule})==90
    status = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), observation_records=len(observations),
        native_search_cards=len(cards), unique_candidate_kakao_ids=len({row['store_id'] for row in candidates}),
        candidate_links=len(candidates), detail_records=len(details), detail_stores=len(profiles),
        stores_with_both_map_details=sum(row['kakao_detail'] and row['google_detail'] for row in profiles),
        archived_assets=len(photos), archived_photos=sum(row['is_menu_asset'] for row in photos.values()),
        rejected_nonmenu_assets=sum(not row['is_menu_asset'] for row in photos.values()),
        branch_uncertain_menu_assets=sum(row['branch_scope_uncertain'] for row in photos.values()),
        visually_read_photos=sum(row['visually_read'] and row['is_menu_asset'] for row in photos.values()),
        finalized_stores=len(cohort), finalized_pairs=len({row['pair_id'] for row in cohort}),
        target_pairs=12, target_stores=24, scheduled_cells=90, actual_restaurant_attempts=len(raw_attempts),
        neutral_probe_attempts=len(attempts), neutral_probe_outcomes=dict(Counter(row['outcome'] for row in attempts)),
        previous_study_files_unchanged=len(preserved),
        exposure_A_pct=None, exposure_B_pct=None, difference_B_minus_A_pp=None,
        study_complete=False, browser_access='both_maps_readable_after_user_recovery; stale_tab_metadata_navigation_error_uses_fresh_tab',
        note='Unstarted restaurant cells are neither failed calls nor nonappearance. No A/B rate can be estimated before cohort freeze and valid responses.')
    json_new(dest/'검수된_현재상태.json', status)
    inventory = [dict(path=str(path.relative_to(ROOT)), sha256=sha(path)) for path in sorted(dest.rglob('*')) if path.is_file()]
    csv_new(dest/'체크포인트_해시.csv', inventory, ['path','sha256'])
    print(json.dumps(status, ensure_ascii=False))


if __name__=='__main__':
    main()
