"""Verify final denominators and distinguish progress messages from completed answers.

Preserves the first report and writes a new verified report and metadata.
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def main():
    old=ROOT/'analysis/실제90회_최종검수_20261103_01'
    dest=ROOT/'analysis/실제90회_최종검수_20261103_03'
    dest.mkdir(exist_ok=False)
    audits=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'analysis/실측_검수자료_20261103_01').glob('*.audit.json')]
    completed=[r for r in audits if not r['provider_errors'] and r['process_status']=='process_completed_requires_audit' and len(r['recommendation_rows'])==5]
    failed=[r for r in audits if r['provider_errors']]
    commentary=[r for r in failed if r['final_text']]
    assert len(audits)==90 and len(completed)==15 and len(failed)==75 and len(commentary)==2
    assert len({r['thread_ids'][0] for r in audits})==90
    state=json.loads((old/'검수된_실제결과.json').read_text(encoding='utf-8'))
    state['search_only_logs_among_generated']=sum(all(a['action'].get('type')=='search' for a in r['tool_actions']) for r in completed)
    state['usage_limit_failures_with_progress_message_only']=len(commentary)
    state['generation_definition']='오류 없이 끝나고 추천5행이 있는 응답. 중간 진행 메시지를 쓴 뒤 한도 오류로 끝난2회는75회 실패에만 포함.'
    state['verified_revision']=2
    state['verified_report']='최종보고서_실제90회_20261103_검수본.md'
    schedule={r['cell_id']:r for r in rows(ROOT/'90셀_실행계획.csv')}
    table=[]
    for area in ['MD','SS','MW']:
        for q in ['Q1','Q2','Q3','ALL']:
            eligible=lambda r:schedule[r['cell_id']]['area_id']==area and (q=='ALL' or schedule[r['cell_id']]['question_id']==q)
            rs=[r for r in audits if eligible(r)];gs=[r for r in completed if eligible(r)];fs=[r for r in failed if eligible(r)]
            assert len(rs)==len(gs)+len(fs)
            table.append(dict(area_id=area,question_id=q,attempts=len(rs),generated_responses=len(gs),usage_limit_failures=len(fs),map_requirement_failures=len(gs),valid_responses=0,appearance_pct=None))
    with (dest/'지역_질문별_실행결과.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(table[0]));w.writeheader();w.writerows(table)
    with (dest/'검수된_실제결과.json').open('x',encoding='utf-8') as f:json.dump(state,f,ensure_ascii=False,indent=2)
    text=(ROOT/'최종보고서_실제90회_20261103.md').read_text(encoding='utf-8')
    for r in table:
        if r['question_id']!='ALL':continue
        area={'MD':'명동','SS':'성수','MW':'망원'}[r['area_id']]
        lines=text.splitlines()
        oldline=next(x for x in lines if x.startswith('| '+area+' |') and x.count('|')==7)
        text=text.replace(oldline,f"| {area} | 30 | {r['generated_responses']} | {r['usage_limit_failures']} | {r['map_requirement_failures']} | 0 |")
    text=text.replace('5회는 로그에 검색 이벤트만 있어',f"{state['search_only_logs_among_generated']}회는 로그에 검색 이벤트만 있어")
    text+='\n완료 응답 수 검수: 한도 오류75회 중2회에는 중간 진행 문구가 있지만 추천 완료 응답으로 세지 않았다. 지역·질문별 합계15+75=90을 재확인했다. 최신 실행 요약은 analysis/실제90회_최종검수_20261103_03에 있다.\n'
    with (ROOT/state['verified_report']).open('x',encoding='utf-8') as f:f.write(text)
    original_manifests=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'raw').glob('*.manifest.json')]
    assert all(hashlib.sha256((ROOT/m['raw_path']).read_bytes()).hexdigest()==m['raw_sha256'] for m in original_manifests)
    assert len(rows(ROOT/'검수_시도판정.csv'))==90
    assert Counter(r['status'] for r in rows(ROOT/'검수_시도판정.csv'))=={'failure':90}
    assert len(rows(ROOT/'추천_추출표.csv'))==75
    assert all(r['valid_denominator']=='0' and r['appearance_pct']=='' for r in rows(ROOT/'매장별_결과.csv'))
    assert all(r['mean_appearance_pct']=='' for r in rows(ROOT/'집단별_결과.csv'))
    lock=json.loads((ROOT/'cohort_lock.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in lock['sha256'].items())
    with (dest/'정합성검수.json').open('x',encoding='utf-8') as f:
        json.dump(dict(passed=True,attempts=90,completed_recommendations=15,usage_limit_failures=75,map_verification_failures=15,valid=0,raw_hashes_unchanged=True,cohort_hashes_unchanged=True,rates_null=True,repeated_response_not_store_sample=True),f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(report=state['verified_report'],attempts=90,generated=15,usage_failure=75,map_requirement_failure=15,valid=0,search_only_completed=state['search_only_logs_among_generated'],regional_totals=[r for r in table if r['question_id']=='ALL'],checks_passed=True),ensure_ascii=False))


if __name__=='__main__':main()
