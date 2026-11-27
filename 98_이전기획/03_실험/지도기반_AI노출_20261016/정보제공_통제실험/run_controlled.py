"""Pre-frozen 2x2 provided-map-information experiment; separate from natural search."""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from run_map_pilot import extract_response

EMPTY = Path(r'C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\cli_map_provided_20261016')
MODELS = {'codex':'gpt-6.1-sol', 'agy':'Gemini 3.8 Flash (Low)'}
AREA = {'MD':'서울 명동과 주변', 'SS':'서울 성수동과 서울숲 주변', 'MW':'서울 망원동 주변'}
LOCK = Lock()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_csv(name, rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)


def freeze_json(name, value):
    text=json.dumps(value,ensure_ascii=False,indent=2)
    path=ROOT/name
    if path.exists():
        assert path.read_text(encoding='utf-8')==text, f'Frozen input changed: {name}'
    else:
        path.write_text(text,encoding='utf-8')


def prepare():
    selected=json.loads((ROOT/'selected_profiles.json').read_text(encoding='utf-8'))['profiles']
    menus={x['restaurant_id']:x for x in json.loads((ROOT/'captured_menu_facts.json').read_text(encoding='utf-8'))['profiles']}
    assert len(selected)==12 and set(menus)=={x['restaurant_id'] for x in selected}
    corpus=[{**p,**menus[p['restaurant_id']], 'author_type':'unknown', 'identity_check':'name_and_address_browser_matched'} for p in selected]
    assert all(len(p['menus'])==2 for p in corpus)
    freeze_json('corpus.json',corpus)
    prompts=[];assignments=[]
    # GF(4) multiply by x. Orthogonal Latin squares for condition and position.
    times_two=[0,2,3,1]
    for area_index,area in enumerate(AREA):
        for repeat in [1,2]:
            rng=random.Random(20261016+100*area_index+repeat)
            stores=[p for p in corpus if p['area_id']==area]
            rng.shuffle(stores)
            aliases=list('가나다라');rng.shuffle(aliases)
            condition_labels=list(range(4));rng.shuffle(condition_labels)
            for rotation in range(4):
                prompt_id=f'CP-{area}-R{repeat}-L{rotation}'
                cards=[]
                for i,p in enumerate(stores):
                    condition=condition_labels[i ^ rotation]
                    rich=condition & 1; repeated=(condition >> 1) & 1
                    position=(i ^ times_two[rotation])+1
                    base=[f'지역: {AREA[area]}',f'업종: {p["category"]}',f'주소: {p["address"]}']
                    facts=base+[f'메뉴: {m["name"]} / 표시 가격: {m["price_display"]}' for m in p['menus']] if rich else base
                    if repeated:
                        facts += [f'지역: {AREA[area]} / 업종: {p["category"]}']*3
                    card='\n'.join(facts)
                    cards.append((position,aliases[i],card))
                    assignments.append({'prompt_id':prompt_id,'area_id':area,'repeat':repeat,'rotation':rotation,
                                        'restaurant_id':p['restaurant_id'],'alias':aliases[i], 'position':position,
                                        'condition':condition,'menu_price_detail':rich,'keyword_repetition':repeated,
                                        'card_text':card,'card_sha256':sha(card.encode('utf-8'))})
                cards.sort()
                prompt=(f'{AREA[area]}에서 한 끼 식사할 식당 2곳을 아래 후보 중에서 추천해줘. 특정 음식 취향이나 예산 제한은 없어.\n'
                        '아래는 공개 지도에서 수집한 식당 정보이며 상호는 가명으로 표시했다. 제공된 정보만으로 판단해줘. '
                        '알 수 없는 메뉴·가격·평점·영업 조건을 추측하지 마. 표시 가격은 메뉴 항목의 가격이며, 표시되지 않은 최소 주문이나 1인 식사 총액은 알 수 없어.\n'
                        '웹 검색, URL 열기, 터미널, 로컬 파일, 과거 대화, 다른 에이전트는 사용하지 마.\n\n'
                        +'\n\n'.join(f'후보 {alias}\n{card}' for _,alias,card in cards)
                        +'\n\n최종 답변은 코드 블록 없이 JSON만 써줘. 서로 다른 후보 2곳을 순서대로 선택하고, evidence에는 그 후보 정보에서 짧은 문자열을 그대로 복사해줘. '
                        '형식: {"selected":[{"rank":1,"code":"가","reason":"선정 이유","evidence":"제공된 정보 그대로"},{"rank":2,"code":"나","reason":"선정 이유","evidence":"제공된 정보 그대로"}]}')
                prompts.append({'prompt_id':prompt_id,'area_id':area,'repeat':repeat,'rotation':rotation,
                                'prompt':prompt,'prompt_sha256':sha(prompt.encode('utf-8'))})
    freeze_json('prompts.json',prompts)
    freeze_json('assignments.json',assignments)
    manifest=[{'run_id':f'{p["prompt_id"]}-{backend.upper()}','backend':backend,'requested_model':model,
               'prompt_id':p['prompt_id'],'area_id':p['area_id'],'repeat':p['repeat'],'rotation':p['rotation']}
              for backend,model in MODELS.items() for p in prompts]
    random.Random(20261016).shuffle(manifest)
    write_csv('run_manifest.csv',manifest)
    frozen={'study_id':'provided-map-information-2x2-v1','frozen_before_model_responses':True,
            'corpus_sha256':sha((ROOT/'corpus.json').read_bytes()),'prompts_sha256':sha((ROOT/'prompts.json').read_bytes()),
            'assignments_sha256':sha((ROOT/'assignments.json').read_bytes()),'planned_runs':48,'independent_stores':12,
            'unique_prompts':24,'selected_per_response':2,'map_source':'kakao','natural_search_experiment':False,
            'model_requested':MODELS,'agy_version_observed':'1.4.0','empty_working_directory':str(EMPTY),
            'randomization_unit':'area_repeat_block; four rotations; condition labels randomly permuted; identical prompts across backends'}
    freeze_json('design_freeze.json',frozen)
    EMPTY.mkdir(parents=True,exist_ok=True)
    return prompts,manifest,assignments


def parse_answer(response):
    try:
        answer=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',response.strip()))
    except ValueError:
        m=re.search(r'\{[\s\S]*\}',response)
        try:answer=json.loads(m[0]) if m else None
        except ValueError:return None
    if not isinstance(answer,dict) or not isinstance(answer.get('selected'),list):return None
    return answer


def run_one(item,prompt,assignments,timeout):
    backend=item['backend'];raw=ROOT/'raw'/backend;raw.mkdir(parents=True,exist_ok=True)
    stem=item['run_id'];attempt=1
    while (raw/(stem+'.jsonl')).exists():
        attempt+=1;stem=item['run_id']+f'-A{attempt}'
    stdout_path=raw/(stem+'.jsonl');stderr_path=raw/(stem+'.stderr.txt')
    if backend=='codex':
        cmd=[shutil.which('codex'),'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
             '--sandbox','read-only','--model',MODELS[backend],'-c','web_search="disabled"',
             '-c','model_reasoning_effort="low"','-c','project_doc_max_bytes=0','--json',prompt['prompt']]
    else:
        cmd=[shutil.which('agy'),'--model',MODELS[backend],'--mode','plan','--disable-slash-commands',
             '--output-format','stream-json','-p',prompt['prompt']]
    tick=time.monotonic();started=utc();timed_out=False;helper_stopped=False
    with stdout_path.open('w',encoding='utf-8') as out,stderr_path.open('w',encoding='utf-8') as err:
        proc=subprocess.Popen(cmd,cwd=EMPTY,stdout=out,stderr=err,env={**os.environ,'NO_COLOR':'1'})
        while proc.poll() is None:
            text=stdout_path.read_text(encoding='utf-8',errors='replace')
            terminal=False
            for line in text.splitlines()[-5:]:
                try:e=json.loads(line)
                except ValueError:continue
                terminal |= e.get('type') in ['turn.completed','turn.failed'] or e.get('event')=='result'
            if terminal:
                try:proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    helper_stopped=True;subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
                break
            if time.monotonic()-tick>timeout:
                timed_out=True;subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10);break
            time.sleep(.3)
        proc.wait(timeout=15)
    response,events,searched,models=extract_response(stdout_path.read_text(encoding='utf-8',errors='replace'),backend)
    answer=parse_answer(response)
    completion=any(e.get('type')=='turn.completed' for e in events) if backend=='codex' else any(e.get('event')=='result' and e.get('result',{}).get('status')=='SUCCESS' for e in events)
    tools=[]
    for e in events:
        step=e.get('step_update',{});it=e.get('item',{})
        if step.get('tool_name'):tools.append(step['tool_name'])
        if it.get('type') in ['command_execution','web_search','mcp_tool_call','file_change']:tools.append(it['type'])
    selected=answer.get('selected',[]) if answer else []
    cards={x['alias']:x['card_text'] for x in assignments if x['prompt_id']==item['prompt_id']}
    codes=[s.get('code') for s in selected if isinstance(s,dict)]
    shape_valid=len(selected)==2 and len(codes)==2 and len(set(codes))==2 and all(c in cards for c in codes)
    evidence_ok=shape_valid and all(isinstance(s.get('evidence'),str) and s['evidence'].strip() and s['evidence'] in cards[s['code']] for s in selected)
    status='completed' if completion and shape_valid else 'format_error' if completion else 'timeout' if timed_out else 'technical_failure'
    if tools:status='protocol_violation_external_tool'
    result={**item,'attempt':attempt,'started_at_utc':started,'finished_at_utc':utc(),'elapsed_seconds':round(time.monotonic()-tick,1),
            'status':status,'provider_completed':completion,'return_code':proc.returncode,'reported_models':models,
            'prompt_sha256':prompt['prompt_sha256'],'parsed_answer':answer,'response':response,
            'external_tools_observed':sorted(set(tools)),'evidence_exact_match':bool(evidence_ok),
            'raw_path':str(stdout_path),'stderr_path':str(stderr_path),'helper_stopped_after_result':helper_stopped,
            'natural_search_experiment':False}
    (raw/(stem+'.md')).write_text(response,encoding='utf-8')
    with LOCK:
        with (ROOT/'attempts.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ['run_id','status','elapsed_seconds','evidence_exact_match']},ensure_ascii=False),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--initialize-only',action='store_true')
    parser.add_argument('--workers',type=int,default=2);parser.add_argument('--limit',type=int,default=48)
    parser.add_argument('--timeout',type=int,default=150);args=parser.parse_args()
    prompts,manifest,assignments=prepare()
    if args.initialize_only:
        print(json.dumps({'planned_runs':len(manifest),'frozen':True}));return
    prior=[json.loads(l) for l in (ROOT/'attempts.jsonl').read_text(encoding='utf-8').splitlines()] if (ROOT/'attempts.jsonl').exists() else []
    done={r['run_id'] for r in prior}  # Do not automatically retry a failed response.
    tasks=[r for r in manifest if r['run_id'] not in done][:args.limit]
    lookup={p['prompt_id']:p for p in prompts}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs=[pool.submit(run_one,r,lookup[r['prompt_id']],assignments,args.timeout) for r in tasks]
        for job in as_completed(jobs):job.result()


if __name__=='__main__':main()
