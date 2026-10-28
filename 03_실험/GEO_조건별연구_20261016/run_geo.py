"""Fresh Korean CLI recommendations by dining intent; never modifies earlier studies."""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / '지도기반_AI노출_20261016'
sys.path.insert(0, str(PRIOR))
from run_map_pilot import build_command, extract_response, MODELS

EMPTY = Path(r'C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\cli_geo_intents_20261016')
AREAS = {'MD': '서울 명동과 주변', 'SS': '서울 성수동과 서울숲 주변', 'MW': '서울 망원동과 망원시장 주변'}
INTENTS = {
 'general': '추가 조건은 없어.',
 'solo': '혼자 방문하며, 1인 주문과 혼자 앉아 식사하기 편한 곳을 원해.',
 'budget': '추가 필수 주문을 포함해 1명이 한 끼를 1만 원 이하로 먹을 수 있는 곳을 원해.',
 'group': '성인 6명이 한 테이블에서 함께 식사할 수 있는 곳을 원해.',
 'child': '만 5세 아이와 함께 방문하며, 아이가 먹을 수 있는 덜 매운 메뉴와 동반 식사가 가능한 곳을 원해.',
 'parking': '승용차로 방문하며, 식당 전용 주차 또는 식당이 안내하는 제휴 주차가 가능한 곳을 원해.',
 'reservation': '방문 전에 식사 좌석을 예약할 수 있는 곳을 원해.',
 'vegan': '육류·생선·해산물·달걀·유제품과 동물성 육수 없이 먹을 수 있는 비건 식사가 가능한 곳을 원해.'
}
SUFFIX = '''
최신 공개 웹을 실제로 검색해서 현재 운영 정보를 확인해줘. 네이버 지도·카카오맵·구글 지도 정보를 우선 확인하되, 접근할 수 없으면 다른 공개 출처를 이용하고 그 출처를 명시해줘. URL 열기가 권한상 불가능하면 검색 결과에 보이는 정보로 판단하고 snippet으로 표시해줘. 추가 승인을 요청하거나 승인을 우회하지 마.
디저트만 파는 카페는 제외하고 한 끼 식사할 식당을 최대 5곳 추천해줘. 조건을 확인한 곳이 부족하면 적게 추천하거나 0곳으로 답해도 돼. 모르는 조건을 충족한다고 단정하지 마. 이름만 넣은 지도 검색 URL을 읽은 상세 페이지처럼 제시하지 마.
검색 질의는 최대 3개, 공개 페이지 열람은 최대 6개로 제한해줘. 로컬 파일·과거 대화·다른 에이전트는 사용하지 마. 파일이나 계정 설정을 변경하지 마.
최종 출력은 코드 블록 없이 아래 JSON만 써줘. evidence_level은 body/snippet/inference/unknown 중 하나이며 네가 보고한 수준이라는 뜻이야. condition_status는 confirmed/partial/unknown 중 하나야. general 질문은 조건 판정 대신 not_applicable을 써줘. source_type은 map/official/tourism/guide/aggregator/blog/social/other 중 선택해줘. 근거는 짧게 요약하고 원문 인용은 하지 마.
{"access_note":"접근 제한","restaurants":[{"rank":1,"name":"상호","branch":null,"address":null,"cuisine":"음식 종류","reason":"추천 이유","condition_status":"unknown","condition_evidence":"조건 충족 근거 또는 알 수 없는 부분","evidence_level":"unknown","sources":[{"url":"실제 사용한 URL","source_type":"other"}]}]}
'''
LOCK = Lock()

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def freeze(name, data):
    path = ROOT / name
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if path.exists():
        assert path.read_text(encoding='utf-8') == payload, name
    else:
        path.write_text(payload, encoding='utf-8')

def prepare():
    EMPTY.mkdir(parents=True, exist_ok=True)
    prompts = []
    for area,label in AREAS.items():
        for intent,condition in INTENTS.items():
            prompts.append({'prompt_id': f'{area}-{intent}', 'area_id': area, 'intent': intent,
                            'prompt': f'{label}에서 식당을 찾고 있어. {condition}' + SUFFIX})
    manifest = [{**{k:p[k] for k in ['prompt_id','area_id','intent']}, 'run_id': f'GEO26-{b}-{p["prompt_id"]}-R{r}',
                 'backend': b, 'repeat': r, 'requested_model': model}
                for r in [1,2] for b,model in MODELS.items() for p in prompts]
    random.Random(2026101602).shuffle(manifest)
    freeze('prompts.json', prompts)
    freeze('manifest.json', manifest)
    protected = [PRIOR/'attempts.jsonl', PRIOR/'정보제공_통제실험'/'attempts.jsonl',
                 PRIOR/'정보제공_통제실험'/'동일정보_표현비교'/'attempts.jsonl',
                 ROOT.parent/'ai-visibility-experiment'/'cli_한국어_탐색'/'results_codex.jsonl',
                 ROOT.parent/'ai-visibility-experiment'/'cli_한국어_탐색'/'results_agy.jsonl']
    design = {'version':'geo-intent-cli-v1', 'date':'2026-10-16', 'cells':96, 'areas':AREAS, 'intents':INTENTS,
              'models_requested':MODELS, 'repeats':2, 'candidate_names_provided':False,
              'source_policy':'prefer three maps; accessible public fallback allowed and labeled; differs from map-only access pilot',
              'endpoints':['recommendation inclusion by intent and model','rank','self-reported constraint confirmation',
                           'cited domains','retrieval query and citation consistency'],
              'primary_analysis':'descriptive within-area intent differences; per-model estimates; repeated runs are not independent stores',
              'missing':'technical errors excluded, unknown facts retained, unverified identity not merged',
              'causality':'natural answers show conditional association; reasons and generated condition labels are not independent restaurant features',
              'prompts_sha256':sha(ROOT/'prompts.json'), 'manifest_sha256':sha(ROOT/'manifest.json'),
              'protected_sha256':{str(p):sha(p) for p in protected}}
    freeze('design_freeze.json', design)
    return prompts, manifest

def parse(text):
    try:
        start = text.index('{')
        value = json.JSONDecoder().raw_decode(text[start:])[0]
        return value if isinstance(value,dict) and isinstance(value.get('restaurants'),list) else None
    except (ValueError, TypeError):
        return None

def run_one(item, prompt, timeout):
    directory = ROOT/'raw'/item['backend']
    directory.mkdir(parents=True, exist_ok=True)
    attempt=1
    stem=item['run_id']
    while (directory/(stem+'.jsonl')).exists():
        attempt+=1
        stem=item['run_id']+f'-A{attempt}'
    outpath=directory/(stem+'.jsonl')
    errpath=directory/(stem+'.stderr.txt')
    start=utc(); tick=time.monotonic(); timed_out=False; terminated_after_terminal=False
    with outpath.open('w',encoding='utf-8') as out, errpath.open('w',encoding='utf-8') as err:
        proc=subprocess.Popen(build_command(item['backend'],prompt),cwd=EMPTY,stdout=out,stderr=err,
                              env={**os.environ,'NO_COLOR':'1'})
        while proc.poll() is None:
            terminal=False
            for line in outpath.read_text(encoding='utf-8',errors='replace').splitlines()[-5:]:
                try: event=json.loads(line)
                except ValueError: continue
                terminal |= event.get('type') in ['turn.completed','turn.failed'] or event.get('event')=='result'
            if terminal or time.monotonic()-tick > timeout:
                timed_out=not terminal
                try: proc.wait(timeout=5 if terminal else .1)
                except subprocess.TimeoutExpired:
                    terminated_after_terminal=terminal
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=15)
                break
            time.sleep(.5)
        proc.wait(timeout=20)
    stdout=outpath.read_text(encoding='utf-8',errors='replace')
    answer,events,searched,models=extract_response(stdout,item['backend'])
    parsed=parse(answer)
    complete=any(e.get('type')=='turn.completed' for e in events) if item['backend']=='codex' else any(
        e.get('event')=='result' and e.get('result',{}).get('status')=='SUCCESS' for e in events)
    denied=[a for e in events if isinstance(e.get('result'),dict) for a in e['result'].get('denied_actions',[])]
    status='completed' if complete and parsed is not None else 'tool_permission_denied' if denied else 'timeout' if timed_out else 'format_error' if complete else 'technical_failure'
    record={**item,'attempt':attempt,'version':'geo-intent-cli-v1','status':status,'parsed_answer':parsed,
            'started_at_utc':start,'finished_at_utc':utc(),'elapsed_seconds':round(time.monotonic()-tick,1),
            'return_code':proc.returncode,'web_search_observed':searched,'reported_models':models,
            'denied_actions':denied,'raw_path':str(outpath),'stderr_path':str(errpath),'response':answer,
            'helper_terminated_after_terminal':terminated_after_terminal,'consumer_result':False,
            'map_body_access_verified':False,'source_and_condition_labels_are_model_self_report':True}
    (directory/(stem+'.md')).write_text(answer,encoding='utf-8')
    with LOCK:
        with (ROOT/'attempts.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
    print(json.dumps({'run_id':item['run_id'],'status':status,'n':len(parsed['restaurants']) if parsed else 0,
                      'search':searched,'seconds':record['elapsed_seconds']},ensure_ascii=False),flush=True)
    return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--workers',type=int,default=4)
    p.add_argument('--limit',type=int,default=96);p.add_argument('--timeout',type=int,default=210)
    p.add_argument('--backend',choices=['codex','agy','both'],default='both');p.add_argument('--retry-failed',action='store_true')
    args=p.parse_args();prompts,manifest=prepare()
    if args.prepare:
        print(json.dumps({'prepared':len(manifest),'prompts_sha256':sha(ROOT/'prompts.json')}));return
    records=[json.loads(x) for x in (ROOT/'attempts.jsonl').read_text(encoding='utf-8').splitlines()] if (ROOT/'attempts.jsonl').exists() else []
    done={r['run_id'] for r in records if r['status']=='completed' or not args.retry_failed}
    todo=[r for r in manifest if r['run_id'] not in done and (args.backend=='both' or r['backend']==args.backend)][:args.limit]
    lookup={p['prompt_id']:p['prompt'] for p in prompts}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run_one,r,lookup[r['prompt_id']],args.timeout) for r in todo]
        for f in as_completed(futures): f.result()

if __name__=='__main__': main()
