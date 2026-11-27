"""Archive real observations and the access blocker, without inventing a cohort.

Run after export_observed.py. Exclusive output paths preserve earlier checkpoints.
"""
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'analysis' / '재접근_상세검수_20261103_01'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_csv(path, data, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(data)

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def main():
    DEST.mkdir(exist_ok=False)
    observations = [json.loads(s) for s in (ROOT/'evidence'/'browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    detail_dir = DEST / 'detail_records'
    photo_dir = DEST / 'menu_photos'
    detail_dir.mkdir(); photo_dir.mkdir()
    detail_records, photo_records, latest = [], [], {}
    # Only these assets have actually been visually read in this chat.
    visually_read = {
        'a71bfefb4a4c26b4','c8f9aff99305e6aa','702380e81e8a37df','edcb1ee653eee9ab','7a900e9b4444ddb7',
        'e28cfb8a3ded5927','868b233f8c2cf9a3','3cc52f2f4162903f','52f601fdaad08b0e','2e35d631ede907c4',
        '7d8ef53c3b266b43','9fb52e91ec2b4982','dbae473ab8052ba6',
    }
    for index, obs in enumerate(observations, 1):
        if obs.get('kind') != 'detail':
            continue
        sid, platform, section = obs['store_id'], obs['platform'], obs['section']
        path = detail_dir / f'{index:03d}_{sid}_{platform}_{section}.json'
        with path.open('x', encoding='utf-8') as f:
            json.dump(obs, f, ensure_ascii=False, indent=2)
        row = dict(store_id=sid, platform=platform, section=section,
                   observed_at=obs['observed_at'], source_url=obs['url'],
                   evidence_file=str(path.relative_to(ROOT)), sha256=digest(path))
        detail_records.append(row)
        latest[sid, platform, section] = (obs, row)
        for asset in obs.get('bundle', {}).get('assets', []):
            source = Path(asset['path'])
            suffix = '.png' if asset['contentType']=='image/png' else '.jpg'
            target = photo_dir / f"{sid}_{asset['id']}{suffix}"
            if not target.exists():
                with source.open('rb') as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
            if digest(source) != digest(target):
                raise ValueError('Photo copy hash mismatch')
            photo_records.append(dict(store_id=sid, asset_id=asset['id'], source_url=asset['url'],
                evidence_file=str(target.relative_to(ROOT)), sha256=digest(target),
                visually_read=asset['id'] in visually_read,
                scope='map menu-board image; archived is not equivalent to visually reviewed'))
    write_csv(DEST/'상세_근거목록.csv',detail_records,['store_id','platform','section','observed_at','source_url','evidence_file','sha256'])
    write_csv(DEST/'사진_근거목록.csv',photo_records,['store_id','asset_id','source_url','evidence_file','sha256','visually_read','scope'])

    native_dir=ROOT/'analysis'/'음식별확대_v3_사전범위적용'
    cards=read_csv(native_dir/'native_cards.csv')
    candidates=read_csv(native_dir/'crossmap_candidates.csv')
    candidate_rows=[]
    for c in candidates:
        sid=c['store_id']
        k_home=latest.get((sid,'kakao','home_hours'))
        g_home=latest.get((sid,'google','overview_hours'))
        links=[r['evidence_file'] for r in detail_records if r['store_id']==sid]
        candidate_rows.append(dict(candidate_id=sid,area_id=c['area_id'],name=c['name'],
            address=c['kakao_address'],kakao_id=c['kakao_id'],kakao_url=c['kakao_url'],
            google_id=c['google_id'],google_url=c['google_url'],search_query=c['query'],
            kakao_rank=c['kakao_rank'],google_rank=c['google_rank'],google_name=c['google_name'],
            google_rating=c['google_rating'],google_reviews=c['google_reviews'],
            detail_status='both_details_observed_identity_review_pending' if k_home and g_home else 'partial_detail' if links else 'search_cards_only',
            identity_verified=False,group='',pair_id='',source_evidence=';'.join(links),
            exclusion_reason='Not selected: essential source, score, geography and matching checks unfinished'))
    write_csv(DEST/'후보_조사표_미확정.csv',candidate_rows,list(candidate_rows[0]))

    profiles=[]
    for sid in sorted({r['store_id'] for r in detail_records}):
        home=latest.get((sid,'kakao','home_hours'))
        if not home: continue
        body=home[0].get('body','')
        def take(pattern):
            m=re.search(pattern,body)
            return m[1] if m else ''
        profiles.append(dict(store_id=sid,name=take(r'장소명\n([^\n]+)'),
            address=take(r'주소\n([^\n]+)'),phone=take(r'전화\n([^\n]+)'),
            official_link_on_kakao=take(r'URL\n([^\n]+)'),
            kakao_detail=True,google_detail=(sid,'google','overview_hours') in latest,
            official_detail=any(k[0]==sid and k[1]=='official' for k in latest),
            text_menu_observed=(sid,'kakao','menu') in latest,
            photo_board_archived_count=sum(p['store_id']==sid for p in photo_records),
            photo_board_visually_read_count=sum(p['store_id']==sid and p['visually_read'] for p in photo_records),
            group_finalized=False,pair_finalized=False,evidence_file=home[1]['evidence_file']))
    write_csv(DEST/'후보_상세관측표.csv',profiles,list(profiles[0]))

    # Audit actual CLI tool events, not only the model's own final claim.
    probes=[]
    for manifest in sorted((ROOT/'readiness').glob('*.manifest.json')):
        m=json.loads(manifest.read_text(encoding='utf-8'))
        raw=ROOT/m['raw_path']
        if digest(raw)!=m['raw_sha256']: raise ValueError('Raw response hash changed')
        ev=[json.loads(s) for s in raw.read_text(encoding='utf-8').splitlines()]
        web=[e['item'] for e in ev if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='web_search']
        opens=[w for w in web if w.get('action',{}).get('type')=='open_page']
        errors=[r for w in opens for r in w.get('results',[]) if r.get('title')=='Internal Error']
        successful_open_results=[r for w in opens for r in w.get('results',[]) if r.get('title') and r.get('title')!='Internal Error']
        final=[e['item']['text'] for e in ev if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
        probes.append(dict(attempt_id=m['attempt_id'],cell_id=m['cell_id'],started_at=m['started_at'],
            ended_at=m['ended_at'],returncode=m['returncode'],raw_file=m['raw_path'],
            raw_sha_verified=True,open_events=len(opens),internal_error_results=len(errors),
            successful_open_results=len(successful_open_results),
            outcome='model_failure' if m['returncode'] else 'map_access_failure' if errors else 'requires_manual_review',
            final_response=final[-1] if final else '',included_in_90=False))
    with (DEST/'CLI_중립점검_원시이벤트검수.json').open('x',encoding='utf-8') as f:
        json.dump(probes,f,ensure_ascii=False,indent=2)
    write_csv(DEST/'CLI_중립점검_시도목록.csv',probes,list(probes[0]))

    old=ROOT.parent/'GEO_두집단_지도비교_20261103'
    preserved,changed=0,[]
    for r in read_csv(old/'산출물_목록_해시.csv'):
        p=old/r['path']
        if p.is_file() and digest(p)==r['sha256']: preserved+=1
        else: changed.append(r['path'])
    if changed: raise ValueError('Previous study files changed: '+repr(changed))
    schedule=read_csv(ROOT/'90셀_실행계획.csv')
    if len(schedule)!=90 or len({r['cell_id'] for r in schedule})!=90:
        raise ValueError('Schedule invariant failed')
    if list((ROOT/'raw').iterdir()): raise ValueError('Unexpected restaurant measurement raw data')
    status=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
        browser_access='both_maps_readable',cli_search_access='both_map_details_failed',
        research_completed=False,target_pairs=12,target_stores=24,finalized_pairs=0,finalized_stores=0,
        collected_restaurant_search_cards=len(read_csv(ROOT/'analysis'/'음식별확대_v2'/'native_cards.csv')),preregistered_search_window_cards=len(cards),
        possible_crossmap_kakao_ids=len({r['candidate_id'] for r in candidate_rows}),
        possible_crossmap_links=len(candidate_rows),
        detail_store_count=len(profiles),detail_record_count=len(detail_records),
        archived_photo_count=len(photo_records),visually_read_photo_count=sum(p['visually_read'] for p in photo_records),
        scheduled_cells=len(schedule),actual_restaurant_attempts=0,valid_restaurant_responses=0,
        restaurant_measurement_failures=0,unstarted_cells=90,
        neutral_probe_attempts=len(probes),neutral_probe_failures=sum(p['outcome']!='requires_manual_review' for p in probes),
        exposure_A_pct=None,exposure_B_pct=None,difference_B_minus_A_pp=None,
        previous_study_files_unchanged=preserved,
        stage3_expansion_completed=False,station_expansion_completed=False,
        conclusion='No validated A/B recommendation comparison exists. CLI access diagnostics are not the 90 restaurant attempts.')
    with (DEST/'검수된_현재상태.json').open('x',encoding='utf-8') as f:
        json.dump(status,f,ensure_ascii=False,indent=2)
    write_csv(DEST/'집단별_결과_산출불가.csv',[
        dict(group=g,target_stores=12,finalized_stores=0,valid_denominator=0,exposure_pct='',status='not_estimable') for g in ['A','B']
    ],['group','target_stores','finalized_stores','valid_denominator','exposure_pct','status'])
    print(json.dumps(status,ensure_ascii=False))

if __name__=='__main__': main()
