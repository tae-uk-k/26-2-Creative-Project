"""Independent checks against saved public evidence and planned/actual ledgers."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'최종_검수자료'

def read(name):
    with (DEST/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def main():
    findings=[]
    def check(label,condition,detail):
        findings.append(dict(check=label,passed=bool(condition),detail=detail))
    with (ROOT/'search_cards.csv').open(encoding='utf-8-sig',newline='') as f:
        cards=list(csv.DictReader(f))
    natural=[c for c in cards if c['sponsored']=='False']
    counts=Counter((c['platform'],c['area_id']) for c in natural)
    check('정식 지도 검색 틀',len(natural)==360 and len(counts)==6 and set(counts.values())=={60},str(dict(counts)))
    check('장소 ID 중복',len({(c['platform'],c['area_id'],c['place_id']) for c in natural})==360,'광고 별도, 지역·지도 내 장소 ID 중복 없음')
    for key in counts:
        ranks=sorted(int(c['rank']) for c in natural if (c['platform'],c['area_id'])==key)
        check('자연 검색 순위 '+str(key),ranks==list(range(1,61)),'1~60 표시 순위 유지')
    sources=[json.loads(l) for l in (ROOT/'browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    stores=read('매장_후보_집단_검수표.csv')
    byid={s['candidate_id']:s for s in stores}
    for s in sources:
        if s['platform']=='kakao_detail' and s['candidate_id'] in byid:
            cid=s['candidate_id']
            check('카카오 상세 지점 헤더 '+cid+' '+s['section'],
                '장소명\n'+byid[cid]['kakao_name']+'\n' in s['body'],s['url'])
    scores=read('GEO_항목별_점수_근거.csv')
    check('후보·점수 셀 수',len(stores)==36 and len(scores)==108,'36후보 × 3항목')
    for s in scores:
        if s['score']!='':
            source=sources[int(s['raw_capture_line'])-1]
            check('점수 근거 '+s['candidate_id']+'-'+s['item'],
                s['source_url']==source['url'] and s['candidate_id'] in source.get('candidate_ids', [source.get('candidate_id')]) and bool(s['quote']),
                '실제 상세 원문 행과 URL·후보 ID 연결')
    check('미확인을 0으로 대체하지 않음',all(s['score']=='' for s in scores if s['score_state']=='unknown'),str(Counter(s['score_state'] for s in scores)))
    pairs=read('매칭_가능성_전수검수.csv')
    check('21개 후보 쌍 제외 근거',len(pairs)==21 and all(p['decision']=='exclude' and p['reason'] and p['menu_quote_1'] and p['menu_quote_2'] for p in pairs),'가까운 3쌍 수동 검수, 나머지 실제 메뉴 음식군 검수')
    check('확정 집단 부재를 명시',not read('확정_매장쌍.csv') and all(s['group']=='' for s in stores),'집단 A/B 모두 0개, 임의 배정 없음')
    schedule=read('전체_실행목록_90셀.csv')
    check('90셀 중복·배정',len(schedule)==90 and len({s['cell_id'] for s in schedule})==90
          and set(Counter((s['area_id'],s['question_id']) for s in schedule).values())=={10},'지역3 × 질문3 × 반복10')
    check('미실행과 실패 구분',all(s['status']=='not_started_cohort_unavailable' and s['attempt_count']=='0' for s in schedule)
          and not read('실제_추천_시도_기록.csv'),'추천 시도0, 미실행90; 준비성 점검은 별도')
    check('노출 0% 조작 방지',all(g['exposure_pct']=='' for g in read('집단별_노출결과.csv')),'분모0을 노출0%로 변환하지 않음')
    lock=json.loads((DEST/'사전등록_해시_잠금상태.json').read_text(encoding='utf-8'))
    check('원문·판정 해시',all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in lock['sha256'].items()),'현재 근거와 잠금 해시 일치; cohort_ready=false')
    result=dict(passed=all(x['passed'] for x in findings),check_count=len(findings),findings=findings,
        methodological_limits='저장 자료 정합성 검수다. Google 메뉴 사진 전체 판독, 조사자 간 일치도, 현장 영업 또는 실제 추천 측정 완료를 증명하지 않음.')
    with (DEST/'근거_정합성_검수결과.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='findings'},ensure_ascii=False))
    if not result['passed']:
        for finding in findings:
            if not finding['passed']:print(json.dumps(finding,ensure_ascii=False))
        raise SystemExit(1)

if __name__=='__main__':main()
