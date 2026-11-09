"""Audit-led matched-store rates. No automatic conversion of model claims to valid.

Input ledgers must contain manual source/identity adjudication. Internal
synthetic checks test arithmetic only and never write fictional study rows.
"""
import argparse
import csv
import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def readcsv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def writecsv(path,data,fields):
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(data)


def raw_review(path):
    events=[];invalid_lines=[]
    for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        try:events.append(json.loads(line))
        except json.JSONDecodeError:invalid_lines.append(n)
    forbidden=[];searches=[];messages=[];failed=[];threads=[]
    for event in events:
        if event.get('type')=='thread.started':threads.append(event.get('thread_id'))
        if event.get('type') in ['turn.failed','error']:failed.append(event)
        item=event.get('item',{})
        if event.get('type')=='item.completed':
            kind=item.get('type')
            if kind=='agent_message':messages.append(item.get('text',''))
            elif kind=='web_search':searches.append(item)
            elif kind not in [None,'reasoning','plan_update']:
                forbidden.append(item)
    return dict(thread_ids=threads,invalid_json_lines=invalid_lines,provider_errors=failed,
        forbidden_tool_items=forbidden,search_events=searches,agent_messages=messages,
        final_message=messages[-1] if messages else '',
        automatic_valid=False,note='검색 이벤트·URL·모델 자기보고만으로 지도 본문 접근 성공을 판정하지 않음.')


def aggregate(stores,schedule,attempts,adjudications,mentions):
    cells={r['cell_id']:r for r in schedule}
    sid={s['store_id']:s for s in stores}
    attempts_by_id={a['attempt_id']:a for a in attempts}
    adjudicated={r['attempt_id']:r for r in adjudications}
    valid={}
    excluded=[]
    for attempt in sorted(attempts,key=lambda a:a['started_at']):
        aid,cell=attempt['attempt_id'],attempt['cell_id']
        judgement=adjudicated.get(aid)
        if not judgement or judgement['status']!='valid':
            excluded.append(dict(attempt_id=aid,reason=judgement['status'] if judgement else 'requires_manual_audit'))
            continue
        if cell not in cells or judgement['cell_id']!=cell:
            raise ValueError('Cell registry mismatch')
        if attempt['process_status']!='process_completed_requires_audit':
            raise ValueError('Failed process cannot be valid')
        if any(judgement[k]!='true' for k in ['map_access_kakao','map_access_google','source_body_verified']):
            raise ValueError('Valid response requires actual body/access evidence for both maps')
        if judgement['local_file_access']!='false' or not judgement.get('evidence') or not judgement.get('reviewed_by'):
            raise ValueError('Unverified isolation or missing audit evidence')
        sample=[m for m in mentions if m['attempt_id']==aid]
        if any(m['identity_status']=='ambiguous' for m in sample):
            raise ValueError('Resolve ambiguous branch before valid rate calculation')
        if cell in valid:
            excluded.append(dict(attempt_id=aid,reason='duplicate_valid_retry'))
        else:valid[cell]=aid
    appearances={}
    for m in mentions:
        aid,cell=m['attempt_id'],m['cell_id']
        if valid.get(cell)!=aid or m['identity_status']!='confirmed':continue
        store_id=m['matched_store_id']
        if store_id not in sid:raise ValueError('Confirmed mention has unknown study store ID')
        if cells[cell]['area_id']!=sid[store_id]['area_id']:
            raise ValueError('Cross-region mention is not eligible')
        key=store_id,cell
        rank=int(m['rank'])
        appearances[key]=min(appearances.get(key,rank),rank)
    store_rows=[]
    for store_id,s in sid.items():
        for q in ['Q1','Q2','Q3','ALL']:
            eligible=[cell for cell in valid if cells[cell]['area_id']==s['area_id'] and (q=='ALL' or cells[cell]['question_id']==q)]
            ranks=[appearances[store_id,c] for c in eligible if (store_id,c) in appearances]
            store_rows.append(dict(store_id=store_id,pair_id=s['pair_id'],area_id=s['area_id'],group=s['group'],
                question_id=q,appearances=len(ranks),valid_denominator=len(eligible),
                appearance_pct=100*len(ranks)/len(eligible) if eligible else None,
                mean_rank_when_present=statistics.mean(ranks) if ranks else None))
    group_rows=[]
    for area in ['MD','SS','MW','ALL']:
        for q in ['Q1','Q2','Q3','ALL']:
            for group in ['A','B']:
                rs=[r for r in store_rows if r['group']==group and r['question_id']==q and (area=='ALL' or r['area_id']==area)]
                vals=[r['appearance_pct'] for r in rs]
                estimable=bool(vals) and all(v is not None for v in vals)
                group_rows.append(dict(area_id=area,question_id=q,group=group,store_count=len(rs),
                    mean_appearance_pct=statistics.mean(vals) if estimable else None,
                    median_appearance_pct=statistics.median(vals) if estimable else None))
    contrasts=[]
    for pair in sorted({s['pair_id'] for s in stores}):
        for q in ['Q1','Q2','Q3','ALL']:
            rs=[r for r in store_rows if r['pair_id']==pair and r['question_id']==q]
            if len(rs)!=2 or {r['group'] for r in rs}!={'A','B'}:raise ValueError('Invalid pair')
            a,b=sorted(rs,key=lambda r:r['group'])
            if a['valid_denominator']!=b['valid_denominator']:raise ValueError('Unequal paired denominator')
            av,bv=a['appearance_pct'],b['appearance_pct']
            contrasts.append(dict(pair_id=pair,area_id=a['area_id'],question_id=q,valid_denominator=a['valid_denominator'],
                A_pct=av,B_pct=bv,B_minus_A_pp=bv-av if av is not None and bv is not None else None))
    return dict(valid_cell_count=len(valid),valid_cells=valid,excluded_attempts=excluded,
        stores=store_rows,groups=group_rows,pair_contrasts=contrasts)


def selfcheck():
    stores=[dict(store_id='TEST-A',group='A',pair_id='TEST-P',area_id='MD'),dict(store_id='TEST-B',group='B',pair_id='TEST-P',area_id='MD')]
    cells=[dict(cell_id='TEST-C1',area_id='MD',question_id='Q1'),dict(cell_id='TEST-C2',area_id='MD',question_id='Q1')]
    empty=aggregate(stores,cells,[],[],[])
    assert all(r['appearance_pct'] is None for r in empty['stores'])
    attempts=[dict(attempt_id='T1',cell_id='TEST-C1',started_at='1',process_status='process_completed_requires_audit'),
              dict(attempt_id='T2',cell_id='TEST-C1',started_at='2',process_status='process_completed_requires_audit'),
              dict(attempt_id='T3',cell_id='TEST-C2',started_at='3',process_status='timeout')]
    judgements=[dict(attempt_id=aid,cell_id='TEST-C1',status='valid',map_access_kakao='true',map_access_google='true',
        source_body_verified='true',local_file_access='false',evidence='TEST ONLY',reviewed_by='TEST') for aid in ['T1','T2']]
    mentions=[dict(attempt_id='T1',cell_id='TEST-C1',matched_store_id='TEST-B',identity_status='confirmed',rank=str(n)) for n in [2,4]]
    result=aggregate(stores,cells,attempts,judgements,mentions)
    assert result['valid_cell_count']==1
    a,b=[next(r for r in result['stores'] if r['store_id']==sid and r['question_id']=='Q1') for sid in ['TEST-A','TEST-B']]
    assert a['valid_denominator']==b['valid_denominator']==1
    assert a['appearance_pct']==0 and b['appearance_pct']==100 and b['appearances']==1 and b['mean_rank_when_present']==2
    assert any(e['reason']=='duplicate_valid_retry' for e in result['excluded_attempts'])
    bad=[dict(judgements[0],map_access_kakao='false')]
    try:aggregate(stores,cells,attempts,bad,mentions)
    except ValueError:pass
    else:raise AssertionError('Map access failure was counted valid')
    print('PASS: arithmetic-only in-memory checks; no synthetic study files created')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--selfcheck',action='store_true')
    args=parser.parse_args()
    if args.selfcheck:selfcheck();return
    if not args.output:parser.error('--output new directory required')
    dest=args.output.resolve()
    if not dest.is_relative_to(ROOT):raise ValueError('Analysis output outside study')
    dest.mkdir(exist_ok=False)
    stores=readcsv(ROOT/'매장_집단_매칭표.csv')
    schedule=readcsv(ROOT/'90셀_실행계획.csv')
    attempts=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'raw').glob('*.manifest.json')]
    for attempt in attempts:
        raw=ROOT/attempt['raw_path']
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=attempt['raw_sha256']:
            raise ValueError('Raw response changed')
        audit=raw_review(raw)
        (dest/(attempt['attempt_id']+'.tool_audit.json')).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        (dest/(attempt['attempt_id']+'.final.txt')).write_text(audit['final_message'],encoding='utf-8')
        if audit['forbidden_tool_items'] or audit['provider_errors'] or audit['invalid_json_lines']:
            if any(r['attempt_id']==attempt['attempt_id'] and r['status']=='valid' for r in readcsv(ROOT/'검수_시도판정.csv')):
                raise ValueError('Tool/provider failure incorrectly adjudicated valid')
    result=aggregate(stores,schedule,attempts,readcsv(ROOT/'검수_시도판정.csv'),readcsv(ROOT/'추천_추출표.csv'))
    for key,name,fields in [
        ('stores','매장별_결과.csv',['store_id','pair_id','area_id','group','question_id','appearances','valid_denominator','appearance_pct','mean_rank_when_present']),
        ('groups','집단별_결과.csv',['area_id','question_id','group','store_count','mean_appearance_pct','median_appearance_pct']),
        ('pair_contrasts','매장쌍별_차이.csv',['pair_id','area_id','question_id','valid_denominator','A_pct','B_pct','B_minus_A_pp'])]:
        writecsv(dest/name,result[key],fields)
    summary=dict(target_pairs=12,actual_pairs=len({s['pair_id'] for s in stores}),target_stores=24,actual_stores=len(stores),
        target_initial_cells=90,actual_attempts=len(attempts),valid_cells=result['valid_cell_count'],
        unstarted_cells=90-len({a['cell_id'] for a in attempts}),
        failed_attempts=sum(r['status']=='failure' for r in readcsv(ROOT/'검수_시도판정.csv')),
        unresolved_attempts=sum(a['attempt_id'] not in {r['attempt_id'] for r in readcsv(ROOT/'검수_시도판정.csv')} for a in attempts),
        exposure_A_pct=next(r['mean_appearance_pct'] for r in result['groups'] if r['area_id']=='ALL' and r['question_id']=='ALL' and r['group']=='A'),
        exposure_B_pct=next(r['mean_appearance_pct'] for r in result['groups'] if r['area_id']=='ALL' and r['question_id']=='ALL' and r['group']=='B'),
        pair_confidence_interval=None,ci_note='미산출. 반복 응답을 매장 표본으로 세지 않음.',
        excluded_attempts=result['excluded_attempts'])
    with (dest/'분석상태.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
