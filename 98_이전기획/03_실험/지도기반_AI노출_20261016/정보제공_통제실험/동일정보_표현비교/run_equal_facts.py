"""Follow-up: hold all map facts constant, vary layout and repetition only."""
import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import run_controlled as base
base.ROOT=ROOT
base.EMPTY=base.EMPTY.parent/'cli_map_equal_facts_20261016'


def prepare():
    corpus=json.loads((ROOT.parent/'corpus.json').read_text(encoding='utf-8'))
    base.freeze_json('corpus.json',corpus)
    prompts=[];assignments=[]
    for area_index,area in enumerate(base.AREA):
        for repeat in [1,2]:
            rng=random.Random(20262016+100*area_index+repeat)
            stores=[p for p in corpus if p['area_id']==area];rng.shuffle(stores)
            aliases=list('가나다라');rng.shuffle(aliases)
            labels=list(range(4));rng.shuffle(labels)
            for rotation in range(4):
                pid=f'EF-{area}-R{repeat}-L{rotation}';cards=[]
                for i,p in enumerate(stores):
                    condition=labels[i ^ rotation];structured=condition&1;repeated=(condition>>1)&1
                    position=(i ^ [0,2,3,1][rotation])+1
                    facts=[f'지역: {base.AREA[area]}',f'업종: {p["category"]}',f'주소: {p["address"]}']
                    facts += [f'메뉴: {m["name"]} / 표시 가격: {m["price_display"]}' for m in p['menus']]
                    if repeated:facts += [f'지역: {base.AREA[area]} / 업종: {p["category"]}']*3
                    card='\n'.join('- '+f for f in facts) if structured else ' '.join(facts)
                    cards.append((position,aliases[i],card))
                    assignments.append({'prompt_id':pid,'area_id':area,'repeat':repeat,'rotation':rotation,
                                        'restaurant_id':p['restaurant_id'],'alias':aliases[i],'position':position,
                                        'condition':condition,'structured_layout':structured,'keyword_repetition':repeated,
                                        'card_text':card,'card_sha256':base.sha(card.encode('utf-8'))})
                cards.sort()
                prompt=(f'{base.AREA[area]}에서 한 끼 식사할 식당 2곳을 아래 후보 중에서 추천해줘. 특정 음식 취향이나 예산 제한은 없어.\n'
                        '아래는 공개 지도에서 수집한 식당 정보이며 상호는 가명으로 표시했다. 제공된 정보만으로 판단해줘. '
                        '알 수 없는 메뉴·가격·평점·영업 조건을 추측하지 마. 표시 가격은 메뉴 항목의 가격이며, 표시되지 않은 최소 주문이나 1인 식사 총액은 알 수 없어.\n'
                        '웹 검색, URL 열기, 터미널, 로컬 파일, 과거 대화, 다른 에이전트는 사용하지 마.\n\n'
                        +'\n\n'.join(f'후보 {a}\n{card}' for _,a,card in cards)
                        +'\n\n최종 답변은 코드 블록 없이 JSON만 써줘. 서로 다른 후보 2곳을 순서대로 선택하고, evidence에는 그 후보 정보에서 짧은 문자열을 그대로 복사해줘. '
                        '형식: {"selected":[{"rank":1,"code":"가","reason":"선정 이유","evidence":"제공된 정보 그대로"},{"rank":2,"code":"나","reason":"선정 이유","evidence":"제공된 정보 그대로"}]}')
                prompts.append({'prompt_id':pid,'area_id':area,'repeat':repeat,'rotation':rotation,
                                'prompt':prompt,'prompt_sha256':base.sha(prompt.encode('utf-8'))})
    base.freeze_json('prompts.json',prompts);base.freeze_json('assignments.json',assignments)
    manifest=[{'run_id':f'{p["prompt_id"]}-{b.upper()}','backend':b,'requested_model':m,
               'prompt_id':p['prompt_id'],'area_id':p['area_id'],'repeat':p['repeat'],'rotation':p['rotation']}
              for b,m in base.MODELS.items() for p in prompts]
    random.Random(20262016).shuffle(manifest);base.write_csv('run_manifest.csv',manifest)
    base.freeze_json('design_freeze.json',{'study_id':'equal-map-facts-layout-repetition-v1',
        'created_at_utc':'2026-10-16T07:39:08Z','status':'Exploratory follow-up designed after information-availability arm, before this arm responses.',
        'corpus_sha256':base.sha((ROOT/'corpus.json').read_bytes()),'prompts_sha256':base.sha((ROOT/'prompts.json').read_bytes()),
        'assignments_sha256':base.sha((ROOT/'assignments.json').read_bytes()),'planned_runs':48,'independent_stores':12,
        'factors':['structured_layout','keyword_repetition'],'menu_facts_identical_in_every_condition':True,
        'primary_analysis':'Model-specific selection counts and within-store differences; no confirmatory p-value or held-out generalization claim.',
        'natural_map_exposure_measured':False,'empty_working_directory':str(base.EMPTY)})
    base.EMPTY.mkdir(parents=True,exist_ok=True)
    return prompts,manifest,assignments


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--initialize-only',action='store_true');args=parser.parse_args()
    prompts,manifest,assignments=prepare()
    if args.initialize_only:print('Frozen 48 equal-facts runs');return
    prior=[json.loads(l) for l in (ROOT/'attempts.jsonl').read_text(encoding='utf-8').splitlines()] if (ROOT/'attempts.jsonl').exists() else []
    done={r['run_id'] for r in prior};lookup={p['prompt_id']:p for p in prompts}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(base.run_one,r,lookup[r['prompt_id']],assignments,150) for r in manifest if r['run_id'] not in done]
        for job in as_completed(jobs):job.result()


if __name__=='__main__':main()
