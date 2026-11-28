"""Finalize manually reviewed failure outcomes; never turn failures into zero exposure."""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

from audit_actual_runs import is_map
from study import check_cohort

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'analysis/실측_검수자료_20261103_01'
DEST = ROOT / 'analysis/실제90회_최종검수_20261103_01'
ANALYSIS = ROOT / 'analysis/실제90회_집계_20261103_01'
REVIEWED_RESPONSE_CELLS = {
    'MW-Q2-R09','MD-Q3-R08','SS-Q2-R09','MD-Q2-R10','SS-Q1-R02',
    'MW-Q2-R04','SS-Q2-R06','MD-Q3-R09','MW-Q1-R02','SS-Q3-R09',
    'MD-Q2-R01','MD-Q3-R10','MD-Q2-R03','MD-Q3-R01','SS-Q2-R07',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def csv_new(path, data, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(data)


def json_new(path, data):
    with path.open('x',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2)


def install_from_empty(name, data, fields):
    original=ROOT/name
    assert rows(original)==[], 'Refuse to overwrite existing data: '+name
    original.rename(DEST/'기존_빈양식_보존'/name)
    csv_new(original,data,fields)


def kst(value):
    return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')


def main():
    DEST.mkdir(exist_ok=False);(DEST/'기존_빈양식_보존').mkdir()
    counts=check_cohort()
    schedule=rows(ROOT/'90셀_실행계획.csv');cells={x['cell_id']:x for x in schedule}
    manifests=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'raw').glob('*.manifest.json'))]
    assert len(manifests)==90 and {m['cell_id'] for m in manifests}==set(cells)
    assert len({m['cell_id'] for m in manifests})==90
    lock=json.loads((ROOT/'cohort_lock.json').read_text(encoding='utf-8'))
    assert lock['frozen_at_utc'] < min(m['started_at'] for m in manifests)
    decisions=[];mentions=[];runrows=[];audits=[];source_counts=Counter();thread_ids=[]
    for m in manifests:
        aid=m['attempt_id'];r=json.loads((AUDIT/(aid+'.audit.json')).read_text(encoding='utf-8'));audits.append(r)
        assert sha(ROOT/m['raw_path'])==m['raw_sha256']==r['raw_sha256']
        assert sha(ROOT/m['stderr_path'])==m['stderr_sha256']
        assert not r['invalid_json_lines'] and not r['forbidden_tool_items']
        thread_ids.extend(r['thread_ids'])
        if r['provider_errors']:
            assert all('hit your usage limit' in json.dumps(x,ensure_ascii=False) for x in r['provider_errors'])
            reason='usage_limit: CLI 원문에 사용량 한도 초과 error 및 turn.failed. 추천 응답 없음.'
            subtype='usage_limit'
        else:
            assert r['cell_id'] in REVIEWED_RESPONSE_CELLS
            assert r['self_report_failure_lines'] and len(r['recommendation_rows'])==5
            assert not any('파르코' in x['name'] or '미테이블' in x['name'] for x in r['recommendation_rows'])
            subtype='map_body_requirement_unmet'
            reason='두 지도 상세 본문 직접 확인 요건 미충족. 15개 응답의 미확인 안내·도구 이벤트를 검수함. 지도 검색 스니펫·대체 사이트·지도 링크를 지도 본문 확인으로 대체하지 않음.'
            if all(x['action'].get('type')=='search' for x in r['tool_actions']):
                reason+=' 로그에는 검색 이벤트만 있어 모델의 지도 열람 실패 자기보고를 실제 open 실패로 확정하지 않음.'
        decisions.append(dict(attempt_id=aid,cell_id=m['cell_id'],status='failure',reason=reason,
            map_access_kakao='not_verified',map_access_google='not_verified',source_body_verified='false',
            local_file_access='false',reviewed_by='assistant_manual_review_20261103',
            evidence=str((AUDIT/(aid+'.audit.json')).relative_to(ROOT))))
        runrows.append({k:m[k] for k in ['attempt_id','cell_id','started_at','ended_at','process_status','returncode','raw_path','stderr_path']})
        source_counts.update(set(urlparse(u).netloc for u in r['final_urls']))
        for rec in r['recommendation_rows']:
            mentions.append(dict(attempt_id=aid,cell_id=m['cell_id'],rank=rec['rank'],name=rec['name'],branch='',address='',matched_store_id='',
                identity_status='outside_cohort_not_branch_audited',reason=rec['raw_row'],menu='',price='',unit='',conditions='',source_urls=rec['source_urls'],
                source_support='not_validated_failed_response',fact_errors='not_assessed',condition_omissions='not_assessed'))
        json_new(DEST/(aid+'.decision.json'),dict(**decisions[-1],failure_subtype=subtype,reviewed_at_utc=datetime.now(timezone.utc).isoformat()))
    assert len(thread_ids)==len(set(thread_ids))==90
    assert sum(bool(r['provider_errors']) for r in audits)==75
    assert {r['cell_id'] for r in audits if not r['provider_errors']}==REVIEWED_RESPONSE_CELLS
    for name,data in [('실제_시도목록.csv',runrows),('검수_시도판정.csv',decisions),('추천_추출표.csv',mentions)]:
        install_from_empty(name,data,list(data[0]))
    cp=subprocess.run([sys.executable,str(ROOT/'tools/analyze.py'),'--output',str(ANALYSIS)],capture_output=True,text=True,encoding='utf-8')
    assert cp.returncode==0,cp.stderr
    analysis=json.loads((ANALYSIS/'분석상태.json').read_text(encoding='utf-8'))
    assert analysis['actual_attempts']==90 and analysis['valid_cells']==0 and analysis['failed_attempts']==90
    assert analysis['exposure_A_pct'] is None and analysis['exposure_B_pct'] is None
    for name in ['매장별_결과.csv','집단별_결과.csv']:
        assert rows(ROOT/name)==[]
        (ROOT/name).rename(DEST/'기존_빈양식_보존'/name)
        with (ANALYSIS/name).open('rb') as src,(ROOT/name).open('xb') as dst:shutil.copyfileobj(src,dst)
    with (ANALYSIS/'매장쌍별_차이.csv').open('rb') as src,(ROOT/'매장쌍별_차이.csv').open('xb') as dst:shutil.copyfileobj(src,dst)
    summary_rows=[]
    for area in ['MD','SS','MW']:
        for q in ['Q1','Q2','Q3','ALL']:
            rs=[r for r in audits if cells[r['cell_id']]['area_id']==area and (q=='ALL' or cells[r['cell_id']]['question_id']==q)]
            summary_rows.append(dict(area_id=area,question_id=q,attempts=len(rs),generated_responses=sum(bool(r['final_text']) for r in rs),usage_limit_failures=sum(bool(r['provider_errors']) for r in rs),map_requirement_failures=sum(not r['provider_errors'] for r in rs),valid_responses=0,appearance_pct=None))
    csv_new(DEST/'지역_질문별_실행결과.csv',summary_rows,list(summary_rows[0]))
    source_rows=[dict(domain=k,answer_count=v,meaning='답변에 링크가 등장한 응답 수; 근거 사실의 정확성·실제 지도 본문 확인 증거와 구분') for k,v in source_counts.most_common()]
    csv_new(DEST/'답변별_출처도메인.csv',source_rows,list(source_rows[0]))
    # Preserve the frozen profile and make the descriptive metadata correction
    # explicit. Scores, matching, and outcome denominators remain unchanged.
    csv_new(DEST/'정보량_보조변수_정정.csv',[
        dict(store_id='SS-465733251',kakao_text_menu_count=19,kakao_menu_photo_count=30,visually_read_menu_images=18,basic_fact_count=7,writer_verified=False),
        dict(store_id='SS-487665317',kakao_text_menu_count=2,kakao_menu_photo_count=19,visually_read_menu_images=18,basic_fact_count=7,writer_verified=False),
    ],['store_id','kakao_text_menu_count','kakao_menu_photo_count','visually_read_menu_images','basic_fact_count','writer_verified'])
    previous=ROOT.parent/'GEO_두집단_지도비교_20261103'
    old=rows(previous/'산출물_목록_해시.csv')
    assert all(sha(previous/x['path'])==x['sha256'] for x in old)
    generated=[r for r in audits if r['final_text']]
    map_link_counts={p:sum(any(is_map(u)==p for u in r['final_urls']) for r in generated) for p in ['kakao','google']}
    only_search=sum(all(a['action'].get('type')=='search' for a in r['tool_actions']) for r in generated)
    report_state=dict(target_pairs=12,actual_pairs=1,target_stores=24,actual_stores=2,cohort_counts=counts,
        actual_attempts=90,generated_recommendation_responses=15,usage_limit_failures=75,map_requirement_failures=15,valid_responses=0,
        exposure_A_pct=None,exposure_B_pct=None,difference_B_minus_A_pp=None,
        source_or_branch_review_completed_for_valid_responses=0,failed_answer_recommendation_rows=75,failed_answer_facts_fully_audited=False,
        response_map_link_counts=map_link_counts,search_only_logs_among_generated=only_search,
        neutral_probe_count=len(list((ROOT/'readiness').glob('*.manifest.json'))),neutral_included_in_90=False,
        preserved_previous_files=len(old),all_raw_hashes_unchanged=True,all_90_thread_ids_unique=True,local_file_tool_events=0,
        cohort_frozen_before_first_attempt=True,cohort_hashes_unchanged=True,
        execution_started_kst=kst(min(m['started_at'] for m in manifests)),execution_ended_kst=kst(max(m['ended_at'] for m in manifests)),
        sample_target_complete=False,initial_90_attempts_complete=True,comparative_study_complete=False,
        next_blockers=['CLI usage limit','two-map detail verification unavailable in generated CLI responses','11 target pairs not secured'],
        metadata_correction='동결 매장근거 JSON의 미테이블 menu_count_reported=19는 메뉴판 사진 수와 혼동한 기술 오류. 실제 카카오 텍스트 메뉴2/메뉴판사진19를 별도 정정표에 기록. 동결 파일·점수·표본을 변경하지 않음.')
    json_new(DEST/'검수된_실제결과.json',report_state)
    sections=[]
    for a in ['MD','SS','MW']:
        r=next(x for x in summary_rows if x['area_id']==a and x['question_id']=='ALL')
        sections.append(f"| {{'MD':'명동','SS':'성수','MW':'망원'}} |")
    area_table='\n'.join(f"| {dict(MD='명동',SS='성수',MW='망원')[r['area_id']]} | {r['attempts']} | {r['generated_responses']} | {r['usage_limit_failures']} | {r['map_requirement_failures']} | 0 |" for r in summary_rows if r['question_id']=='ALL')
    report=f'''# GEO 정보 미흡군과 충실군의 CLI 추천 등장률 비교 — 실제 실행 결과

2026-11-03 회차01. **90회 호출을 시도했지만 유효 응답은 0회여서 A/B 등장률을 계산할 수 없다.** 목표12쌍 중 확정 표본은 성수1쌍2매장이다. 전체 비교 연구는 미완료이며, 기존 결과·가상 수치를 합산하지 않았다.

실행 시간: {report_state['execution_started_kst']} ~ {report_state['execution_ended_kst']} KST. 모델 `gpt-6.1-sol`, Codex CLI `0.166.0-alpha.5.1`, 내장 live web_search, 새 세션90개, 동시3개. 질문9개×반복10회와 무작위 순서는 사전에 고정했다. 원문은 raw 폴더에 보존했다.

## ① 어떤 가게를 왜 선정했고, 기본 검색 노출은 얼마나 비슷한가?

| 항목 | A: 파르코 서울숲점 | B: 미테이블 성수본점 |
|---|---|---|
| 주소 | 서울 성동구 서울숲2길44 1층 | 서울 성동구 왕십리로8길5 1층 |
| 카카오 ID | 465733251 | 487665317 |
| Google ID | ChIJQ3ayrkGlfDURzlcSDToJTwo | ChIJG5j-_5ukfDURw4TPvEKfIPY |
| 대표 식사·표시가격 | 버섯치즈 리조또20,800원 | 랍스타 바질올리오21,900원 |
| 가격 비교 단위 | 메뉴표의 식사 단품 가격, 인분 미표시 | 동일 |
| 검색어·정렬 | 서울 성수동 파스타 / 카카오정확도순·Google기본 / 필터없음 | 동일 |
| 카카오 자연검색 순위 | 6위 | 9위 |
| Google 자연검색 순위 | 24위 | 6위 |
| Google 평점·리뷰 | 4.5 / 205 | 4.5 / 245 |
| 기본 사실 필드 수 | 7 | 7 |
| 카카오 텍스트 메뉴 / 메뉴판 사진 | 19 / 30 | 2 / 19 |
| 실제 판독한 메뉴판 이미지 | 18 | 18 |

가격 비율1.053, 리뷰 비율1.195, 평점 차이0.0, 순위 차이는 카카오3·Google18이다. 사전 수치 허용범위에는 들지만 **Google에서 B가 상당히 더 상위이며, 기본 검색 노출이 완전히 균형 잡혔다고 할 수 없다.** 파르코의 카카오 주업종은 피자, 미테이블은 양식이며 두 매장 모두 실제 다수의 파스타·리조또 등 이탈리안 식사를 제공한다. 파르코 공식 연결은 뚝섬역8번 출구357m, 미테이블 카카오는 뚝섬역7번 출구248m로 안내한다. 상권·주력 구성·플랫폼별 정보 존재 차이가 남아 있다.

미테이블의 매장 단품21,900원과 별도 포장 항목22,900원은 판매 경로를 구분했다. 인분·중량을 임의 환산하지 않았다. 기본 정보7필드는 상호·주소·한 채널 이상 전화·시간·업종·대표 식사 가격·공식 연결의 존재 수다. A의 Google 전화·웹사이트 누락은 별도로 기록했다. **텍스트 정보량까지 같다는 의미가 아니다.**

확정 전 후보를 확대하여 자동 교차연결186개를 얻었고, 실제 상세 조사46개·양 지도 상세 확인30개를 확보했다. 자동 연결은 동일 지점 확정과 다르다. 120개 이미지가 실제 판독되었다. 이 중 이번 회차 확정은1쌍이며 미검수 후보가 남아 있다. 지역 내 적합한 가게가 존재하지 않는다고 결론내리지 않는다. 명동·망원 표본을 채웠다고 기록하지 않았다.

확정하지 않은 사례: 코너룸은 공식 연결 페이지와 지도 마감시간 차이, 장모님멸치국수는 카카오 대표메뉴5,000원과 판독 메뉴판6,000원 차이, 명동돈가스는 공식 메뉴의 리필 안내와 주간시간 대조 등 추가 채점 필요, 23번지–원조남산 명동본점은 실제 도보1.7km 차이. 상세 미검수·4점·기준 불충족은 각각 구분한다.

## ② 실제로 어떤 GEO 정보 특성이 달랐는가?

| 분류 항목 | A | B | 실제 확인 근거 |
|---|---:|---:|---|
| 메뉴·가격·판매 단위 연결 | 1 | 1 | 양쪽 주메뉴명·가격은 있으나 인분·중량이 주요 메뉴 전반에 명시되지 않음 |
| 실제 이용 조건 | 1 | 2 | A의 서비스 마감시간이 지도별로 다름. B는 식사 주문 시 콘스프·빵 제공과20:20 주문마감을 연결 |
| 지점 정보 일관성 | 1 | 2 | A는 지도별 시간 차이·Google전화/웹사이트 미등록. B는 주소·전화·주간시간 대조 및 스마트콜 지점 연결 설명 확인 |
| 합계·집단 | 3 / A | 5 / B | 추천 실행 전 동결 |

A는 카카오21:30마감과 Google화~일20:00·월22:30마감을 병기했다. 어떤 시간이 정답인지 임의 결정하지 않았다. **A의 영업시간 차이가 항목②·③에 함께 기여한다. 따라서 서로 독립된 두 GEO 특성으로 해석하지 않는다.** 미테이블의 일부 스테이크250g만으로 전체 메뉴 단위를2점 처리하지 않았다. 사진 게시자나 플랫폼 요약 문구를 업주 작성이라고 추정하지 않았다. 모든 점수의 짧은 실제 문구·출처·시각·저장 근거는 GEO_항목별점수.csv 및 analysis/확정표본_20261103_01에 있다.

보조 메타데이터 정정: 동결 매장근거 JSON에 미테이블 메뉴 수19로 적힌 값은 메뉴판 사진 수와 혼동했다. 실제 텍스트 메뉴2·사진19를 최종검수의 정보량_보조변수_정정.csv에 기록했다. 기존 동결 파일·점수·집단을 변경하지 않았다.

## ③ 실제 추천 등장률은 각각 얼마였는가?

**A: 산출 불가 / B: 산출 불가 / B-A: 산출 불가.** 양쪽 유효 응답 분모가0이다. 0%로 기재하지 않는다. 유효 응답에서의 평균 추천순서·질문별 차이·쌍별 차이도 산출 불가다.

| 지역 | 호출 시도 | 추천 답변 생성 | 사용량 한도 실패 | 지도 확인 요건 미충족 | 유효 응답 |
|---|---:|---:|---:|---:|---:|
{area_table}
| 합계 | 90 | 15 | 75 | 15 | 0 |

한도 실패75회에는 CLI 원문에 `You’ve hit your usage limit` 및 turn.failed가 있다. 나머지15회는 모두 두 지도 직접 확인을 완료하지 못했다고 답했다. 이 중10회는 열람 관련 도구 오류 결과가 있으며, {only_search}회는 로그에 검색 이벤트만 있어 모델의 ‘접근 실패’ 자기보고를 실제 open 실패로 확정할 수 없다. 전체15회를 지도 본문 검증 요건 미충족으로 제외했다. 중립 준비성 점검8회는90회와 합산하지 않았다. 재시도는 수행하지 않았다.

## ④ 추천 답변은 어떤 정보를 근거로 삼았는가?

생성된15개 답변은 다이닝코드·테이블링·관광 안내·블로그·식당 안내 사이트 등 대체 출처로 메뉴·가격·구성·주소를 제시했다. 실패 답변의 후보75행과 순서·링크를 추출해 보존했다. **유효 지도 비교 결과로 대체하지 않았다.**

카카오 링크를 제시한 답변{map_link_counts['kakao']}개, Google 지도 링크를 제시한 답변{map_link_counts['google']}개지만, 링크 표시를 실제 지도 본문 확인으로 세지 않았다. URL별 검색 스니펫·열람 메타데이터·오류·모델 자기보고를 나누어 저장했다. 실패 답변의 외부 후보75행에 대한 실제 지점·가격·조건 전수 검수는 미완료다. 사실 오류·조건 누락을0건이라고 주장하지 않는다. 표본 두 매장의 유효 등장 관찰은 없다.

## ⑤ 어떤 정보부터 정비할 필요가 있는가?

이번 실측에서는 GEO 정보 정리 상태와 추천 등장률의 관계를 판단할 수 없다. 확인된 자료 차이를 기준으로는 파르코의 지도별 마감시간·전화·공식 연결을 먼저 사실 확인하고, 두 매장 주요 메뉴의 가격에 판매 단위·실제 주문 조건을 연결하는 작업이 필요하다. 이는 발견된 정보 차이에 따른 정비 후보이며, 이번 실험에서 입증한 노출 개선 효과가 아니다. 실제 지도 정보는 수정하지 않았다.

표본은1쌍이고 유효 응답은0회여서 불확실성 구간·유의성 검정·XGBoost를 산출하지 않았다. 반복 호출90개를 독립된90매장 표본으로 취급하지 않는다. 기존 매장 간 관찰 비교이며 정보 정비 전후 효과로 표현하지 않는다.

발표에 사용할 수 있는 실제 문장: **“CLI 추천90회 호출을 시도한 결과,75회는 사용량 한도 초과,15회는 두 지도 직접 확인 요건 미충족으로 제외되어 집단별 추천 등장률을 산출하지 못했다.”**

재계산: tools/audit_actual_runs.py로 원문을 검수 자료로 추출하고, 검수_시도판정.csv를 적용해 tools/analyze.py --output 새_출력폴더 를 실행한다. 원문90개 SHA256·새 세션90개·동결 선행·기존 연구파일{len(old)}개 보존을 확인했다. 최종검수 JSON과 분석 결과표를 함께 읽어야 한다.
'''
    with (ROOT/'최종보고서_실제90회_20261103.md').open('x',encoding='utf-8') as f:f.write(report)
    check_cohort()
    inventory=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    csv_new(ROOT/'산출물_목록_해시_실제90회_20261103.csv',inventory,['path','bytes','sha256'])
    print(json.dumps(report_state,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
