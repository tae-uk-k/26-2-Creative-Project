"""Independent CLI runs with a strict pre-measurement cohort gate.

Only the natural recommendation question is passed to the CLI. Scored store
data is used by the launcher for admission and never included in its prompt.
All research writes stay in this new study directory. Existing files are not
overwritten. Neutral readiness checks are never restaurant measurements.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6.1-sol'
SEED = 2026110301
EMPTY_BASE = Path(os.environ.get('LOCALAPPDATA', str(ROOT)))/'seelo'/'geo_cli_empty_20261103_01'
AREAS = {'MD': '명동', 'SS': '성수', 'MW': '망원'}
COMMON = '카카오맵과 구글 지도의 공개 정보를 확인하고, 정확한 지점명, 추천 이유, 대표 메뉴·가격, 실제로 확인한 출처 링크를 제시해줘. 확인되지 않은 사실은 추측하지 마.'


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def csv_new(path, data, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(data)


def json_new(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def prompts():
    result = []
    for area_id, area in AREAS.items():
        texts = [f'{area}에서 한 끼 식사하기 좋은 음식점 5곳을 추천해줘.',
                 f'{area}{"를" if area=="성수" else "을"} 처음 방문하는 사람에게 추천할 음식점 5곳을 알려줘.',
                 f'{area}에서 대표 메뉴를 먹어볼 만한 식당 5곳을 추천해줘.']
        for i, question in enumerate(texts, 1):
            result.append(dict(area_id=area_id, question_id=f'Q{i}', prompt=question+'\n'+COMMON))
    return result


def settings():
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI not found')
    version = subprocess.check_output([executable, '--version'], text=True, encoding='utf-8').strip()
    return dict(study='GEO 정보 미흡군과 충실군의 CLI 추천 등장률 비교', model_requested=MODEL,
        resolved_model_snapshot=None, cli_executable=executable, cli_version=version,
        search_tool='Codex builtin web_search', web_search='live', reasoning_effort='low',
        sandbox='read-only', ephemeral=True, ignore_user_config=True, project_doc_max_bytes=0,
        child_workdir_parent=str(EMPTY_BASE), timeout_seconds=240, workers=3,
        random_seed=SEED, max_retries_per_cell=1, question_only_prompt=True,
        group_A_total_range=[0,3], group_B_total_range=[5,6], excluded_total=[4],
        note='요청 모델명은 고정. 내부 모델 스냅샷 ID는 CLI가 반환하지 않으면 미확인으로 유지.',
        created_at_utc=utcnow(), prompts=prompts())


def initialize():
    config = settings()
    json_new(ROOT/'고정_실행설정.json', config)
    cells = [dict(p, repeat=r, cell_id=f"{p['area_id']}-{p['question_id']}-R{r:02d}")
             for p in config['prompts'] for r in range(1,11)]
    random.Random(SEED).shuffle(cells)
    for order, cell in enumerate(cells, 1):
        cell.update(execution_order=order, status='not_started_requires_cohort')
    csv_new(ROOT/'90셀_실행계획.csv', cells, ['execution_order','cell_id','area_id','question_id','repeat','prompt','status'])
    csv_new(ROOT/'매장_집단_매칭표.csv', [], ['store_id','pair_id','area_id','group','name','branch','address',
        'kakao_id','kakao_url','google_id','google_url','food_group','representative_menu','price_krw','sale_unit',
        'hours','conditions','search_query','kakao_rank','google_rank','google_rating','google_reviews',
        'basic_fact_count','text_present','photo_present','score_1','score_2','score_3','score_total',
        'identity_verified','operation_verified','meal_eligible','source_evidence','observed_at','residual_difference'])
    csv_new(ROOT/'GEO_항목별점수.csv', [],
        ['store_id','item','score','status','quote','source_url','observed_at','evidence_file','reason','writer_status'])
    csv_new(ROOT/'후보_조사표.csv', [], ['candidate_id','area_id','name','address','kakao_id','kakao_url',
        'google_id','google_url','search_query','kakao_rank','google_rank','detail_status','source_evidence','exclusion_reason'])
    csv_new(ROOT/'실제_시도목록.csv', [], ['attempt_id','cell_id','started_at','ended_at','process_status','returncode','raw_path','stderr_path'])
    csv_new(ROOT/'검수_시도판정.csv', [], ['attempt_id','cell_id','status','reason','map_access_kakao','map_access_google',
        'source_body_verified','local_file_access','reviewed_by','evidence'])
    csv_new(ROOT/'추천_추출표.csv', [], ['attempt_id','cell_id','rank','name','branch','address','matched_store_id',
        'identity_status','reason','menu','price','unit','conditions','source_urls','source_support','fact_errors','condition_omissions'])
    csv_new(ROOT/'매장별_결과.csv', [], ['store_id','pair_id','area_id','group','question_id','appearances','valid_denominator','appearance_pct','mean_rank_when_present'])
    csv_new(ROOT/'집단별_결과.csv', [], ['area_id','question_id','group','store_count','mean_appearance_pct','median_appearance_pct'])
    print(json.dumps(dict(initialized=True, cells=len(cells), actual_restaurant_attempts=0), ensure_ascii=False))


def check_cohort(require_lock=True):
    stores = rows(ROOT/'매장_집단_매칭표.csv')
    if not stores:
        raise ValueError('확정 매장 집단 없음. 추천 측정 시작 금지.')
    ids, pairs = set(), {}
    scores = rows(ROOT/'GEO_항목별점수.csv')
    for s in stores:
        if s['store_id'] in ids:
            raise ValueError('Store reused')
        ids.add(s['store_id'])
        if s['area_id'] not in AREAS or s['group'] not in ['A','B']:
            raise ValueError('Invalid group or area')
        values = [int(s['score_'+str(i)]) for i in [1,2,3]]
        if any(v not in [0,1,2] for v in values):
            raise ValueError('Unknown/invalid score included')
        total = sum(values)
        if total != int(s['score_total']) or (s['group']=='A' and total>3) or (s['group']=='B' and total<5):
            raise ValueError('Group threshold mismatch')
        evidence = [r for r in scores if r['store_id']==s['store_id']]
        if len(evidence)!=3 or {int(r['item']) for r in evidence}!={1,2,3}:
            raise ValueError('Three scored evidence items required')
        for r in evidence:
            if r['status']!='confirmed' or not all(r[k] for k in ['quote','source_url','observed_at','evidence_file','reason']):
                raise ValueError('Score evidence missing')
            if int(r['score'])!=values[int(r['item'])-1]:
                raise ValueError('Item/store score mismatch')
            evidence_path = ROOT/r['evidence_file']
            if not evidence_path.resolve().is_relative_to(ROOT.resolve()) or not evidence_path.is_file():
                raise ValueError('Evidence must be saved inside this study')
        for key in ['identity_verified','operation_verified','meal_eligible']:
            if s[key]!='true':
                raise ValueError('Eligibility not confirmed: '+key)
        if not all(s[k] for k in ['name','address','kakao_id','kakao_url','google_id','google_url',
                'food_group','representative_menu','price_krw','sale_unit','hours','search_query','source_evidence','observed_at']):
            raise ValueError('Required store fact missing')
        if int(s['basic_fact_count'])<6:
            raise ValueError('Insufficient basic facts')
        pairs.setdefault(s['pair_id'], []).append(s)
    by_area = {a:0 for a in AREAS}
    for pid, pair in pairs.items():
        if len(pair)!=2 or {s['group'] for s in pair}!={'A','B'}:
            raise ValueError('Pair must contain exactly one A and one B')
        a,b = sorted(pair, key=lambda s:s['group'])
        if a['area_id']!=b['area_id'] or a['food_group']!=b['food_group'] or a['search_query']!=b['search_query']:
            raise ValueError('Area/food/query mismatch')
        if a.get('search_condition_id','default')!=b.get('search_condition_id','default'):
            raise ValueError('Native search interpretation differs within pair')
        if a['sale_unit']!=b['sale_unit']:
            raise ValueError('Meal prices must use the same verified sales unit')
        by_area[a['area_id']]+=1
        if max(float(a['price_krw']),float(b['price_krw']))/min(float(a['price_krw']),float(b['price_krw']))>1.75:
            raise ValueError('Price ratio over caliper')
        for key in ['kakao_rank','google_rank']:
            va,vb=int(a[key]),int(b[key])
            if min(va,vb)<1 or max(va,vb)>60 or abs(va-vb)>20:
                raise ValueError('Rank caliper failed')
        if abs(float(a['google_rating'])-float(b['google_rating']))>.60000001:
            raise ValueError('Rating caliper failed')
        ca,cb=int(a['google_reviews']),int(b['google_reviews'])
        if min(ca,cb)<=0 or max(ca,cb)/min(ca,cb)>8:
            raise ValueError('Review caliper failed')
        if abs(int(a['basic_fact_count'])-int(b['basic_fact_count']))>1:
            raise ValueError('Basic fact caliper failed')
    if any(c>4 for c in by_area.values()):
        raise ValueError('Over four pairs in a region')
    if require_lock:
        lock=json.loads((ROOT/'cohort_lock.json').read_text(encoding='utf-8'))
        if not lock['cohort_ready']:
            raise ValueError('Cohort not frozen')
        for name,digest in lock['sha256'].items():
            if sha(ROOT/name)!=digest:
                raise ValueError('Frozen file modified: '+name)
    return dict(stores=len(stores), pairs=len(pairs), by_area=by_area)


def freeze():
    counts = check_cohort(require_lock=False)
    if any((ROOT/'raw').glob('*.jsonl')):
        raise ValueError('Recommendation raws exist before freeze')
    names=['사전규약.md','매장_집단_매칭표.csv','GEO_항목별점수.csv','고정_실행설정.json','90셀_실행계획.csv',
           '후보확대_지역앵커_추가.md','후보확대_지역해석교정_추가.md','채점범위_사용자확정_20261103.md','메뉴_0점_1점_사용자확정_20261103.md']
    evidence={r['evidence_file'] for r in rows(ROOT/'GEO_항목별점수.csv')}
    names+=sorted(evidence)
    json_new(ROOT/'cohort_lock.json',dict(cohort_ready=True, frozen_at_utc=utcnow(),
        restaurant_attempts_before_freeze=0, **counts, sha256={name:sha(ROOT/name) for name in names}))
    print(json.dumps(counts, ensure_ascii=False))


def command(config, prompt):
    return [config['cli_executable'],'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
        '--sandbox','read-only','--model',config['model_requested'],'-c','web_search="live"',
        '-c','model_reasoning_effort="low"','-c','project_doc_max_bytes=0','--json',prompt]


def run_one(config, cell, readiness=False, retry=0):
    stem = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+cell['cell_id']+f'-T{retry+1}'
    folder=ROOT/('readiness' if readiness else 'raw')
    outpath,errpath=folder/(stem+'.jsonl'),folder/(stem+'.stderr.txt')
    workdir=EMPTY_BASE/stem
    workdir.mkdir(parents=True,exist_ok=False)
    env={k:v for k,v in os.environ.items() if k not in ['CODEX_THREAD_ID','CODEX_TURN_ID','CODEX_CONVERSATION_ID']}
    env['NO_COLOR']='1'
    started=utcnow()
    rc=None
    status='unknown'
    with outpath.open('x',encoding='utf-8') as out,errpath.open('x',encoding='utf-8') as err:
        try:
            proc=subprocess.run(command(config, cell['prompt']),cwd=workdir,env=env,
                stdout=out,stderr=err,timeout=config['timeout_seconds'],encoding='utf-8')
            rc=proc.returncode
            status='process_completed_requires_audit' if rc==0 else 'model_or_process_failure'
        except subprocess.TimeoutExpired:
            status='timeout'
        except OSError as exc:
            status='launcher_failure'
            err.write(str(exc))
    record=dict(attempt_id=stem,cell_id=cell['cell_id'],started_at=started,ended_at=utcnow(),
        process_status=status,returncode=rc,raw_path=str(outpath.relative_to(ROOT)),stderr_path=str(errpath.relative_to(ROOT)))
    json_new(folder/(stem+'.manifest.json'),dict(**record, model_requested=config['model_requested'],
        cli_version=config['cli_version'],search_tool=config['search_tool'],prompt=cell['prompt'],
        working_directory=str(workdir),readiness_only=readiness,raw_sha256=sha(outpath),stderr_sha256=sha(errpath)))
    return record


def readiness():
    config=json.loads((ROOT/'고정_실행설정.json').read_text(encoding='utf-8'))
    cell=dict(cell_id='NEUTRAL-MAP-ACCESS',prompt='카카오맵과 구글 지도에서 서울특별시청의 공개 상세 정보를 각각 열어 주소와 실제로 확인한 출처 링크를 알려줘. 열지 못한 지도는 접근 실패라고 명시하고 사실을 추측하지 마.')
    record=run_one(config,cell,readiness=True)
    print(json.dumps(record,ensure_ascii=False),flush=True)


def measure(retry=False):
    counts=check_cohort()
    config=json.loads((ROOT/'고정_실행설정.json').read_text(encoding='utf-8'))
    cells=rows(ROOT/'90셀_실행계획.csv')
    manifests=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'raw').glob('*.manifest.json')]
    if retry:
        adjudicated=rows(ROOT/'검수_시도판정.csv')
        done={m['cell_id'] for m in manifests}
        valid={r['cell_id'] for r in adjudicated if r['status']=='valid'}
        failure={r['cell_id'] for r in adjudicated if r['status']=='failure'}
        cells=[c for c in cells if c['cell_id'] in failure-valid and sum(m['cell_id']==c['cell_id'] for m in manifests)==1]
    else:
        if manifests:
            raise ValueError('Initial batch already started. Preserve attempts; do not duplicate cells.')
    ledger=ROOT/('실제_재시도목록.csv' if retry else '실제_기본90회_시도목록.csv')
    with ledger.open('x',encoding='utf-8-sig',newline='') as f:
        fields=['attempt_id','cell_id','started_at','ended_at','process_status','returncode','raw_path','stderr_path']
        writer=csv.DictWriter(f,fields);writer.writeheader();f.flush()
        with ThreadPoolExecutor(max_workers=config['workers']) as pool:
            pending=[pool.submit(run_one,config,c,False,int(retry)) for c in cells]
            for future in as_completed(pending):
                record=future.result();writer.writerow(record);f.flush()
                print(json.dumps(record,ensure_ascii=False),flush=True)
    print(json.dumps(dict(completed_cells=len(cells),cohort=counts),ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['init','readiness','check','freeze','measure','retry'])
    args=parser.parse_args()
    if args.action=='init':initialize()
    elif args.action=='readiness':readiness()
    elif args.action=='freeze':freeze()
    elif args.action=='check':print(json.dumps(check_cohort(),ensure_ascii=False))
    else:measure(retry=args.action=='retry')


if __name__=='__main__':
    main()
