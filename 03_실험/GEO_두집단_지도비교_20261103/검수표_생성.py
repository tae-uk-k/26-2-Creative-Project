"""Rebuild screening/audit outputs from public observations. Never overwrite evidence.

No recommendation is requested by this script. Ineligible/unknown stores do not
receive exposure zeroes. Native map search-card evidence is kept distinct from
detail-page evidence. Use a new --output directory for a repeat calculation.
"""
import argparse
import csv
import hashlib
import itertools
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AREAS = {'MD': '명동', 'SS': '성수', 'MW': '망원'}


def readcsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def writecsv(directory, name, rows, fields):
    with (directory/name).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def writejson(directory, name, obj):
    with (directory/name).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatible_baseline(a, b):
    if a['area_id'] != b['area_id']:
        return False
    try:
        for key in ['kakao_rank', 'google_rank']:
            x, y = int(a[key]), int(b[key])
            if abs(x-y) > 15 or (x-1)//20 != (y-1)//20:
                return False
        ra, rb = float(a['google_rating']), float(b['google_rating'])
        ca, cb = int(a['google_review_count']), int(b['google_review_count'])
        return abs(ra-rb) <= .40000001 and min(ca, cb) > 0 and max(ca, cb)/min(ca, cb) <= 3
    except (ValueError, ZeroDivisionError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='최종_검수자료')
    args = parser.parse_args()
    dest = ROOT/args.output
    dest.mkdir(exist_ok=False)
    manual = json.loads((ROOT/'수동검수_확정판정.json').read_text(encoding='utf-8'))
    screening = json.loads((ROOT/'추가_메뉴선별_판정.json').read_text(encoding='utf-8'))['stores']
    sources = [json.loads(x) for x in (ROOT/'browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    cards = readcsv(ROOT/'search_cards.csv')
    candidates = readcsv(ROOT/'possible_crossmap_matches.csv')
    scored = {s['candidate_id']: s for s in manual['stores']}
    card_by_id = {(c['platform'], c['place_id']): c for c in cards if c['sponsored'] == 'False'}
    for alias in manual['additional_name_alias_candidates']:
        k, g = card_by_id['kakao', alias['kakao_id']], card_by_id['google', alias['google_id']]
        candidates.append(dict(candidate_id=k['area_id']+'-'+k['place_id'], area_id=k['area_id'],
            kakao_name=k['name'], kakao_id=k['place_id'], kakao_rank=k['rank'], kakao_url=k['url'],
            kakao_address_card=k['address_search_card'], kakao_category_card=k['category_search_card'],
            google_name=g['name'], google_id=g['place_id'], google_rank=g['rank'], google_url=g['url'],
            google_address_card=g['address_search_card'], google_category_card=g['category_search_card'],
            google_rating=g['rating'], google_review_count=g['review_count'], identity_status=alias['reason']))

    detail_index = {}
    for i, s in enumerate(sources, 1):
        ids = s.get('candidate_ids', [s.get('candidate_id')])
        for candidate_id in ids:
            detail_index[candidate_id, s['platform'], s.get('section')] = (i, s)
    score_rows, store_rows = [], []
    for c in candidates:
        s = scored.get(c['candidate_id'])
        row = dict(c)
        row.update(group='', pair_id='', inclusion_status='excluded_or_not_fully_verified',
            identity_detail=s['identity'] if s else '미확인: 이름/주소 검색 카드 후보이며 상세 대조 미완료',
            operating_evidence=s['operation'] if s else '미확인: 검색 카드만으로 현재 운영 확정 안 함',
            representative_menu=s['representative_menu'] if s else '미확인',
            price_krw=s['price_krw'] if s and s['price_krw'] is not None else '',
            sale_unit=s['sale_unit'] if s else '미확인',
            condition=s['condition'] if s else '미확인',
            score_1=s['scores'][0]['score'] if s else '',
            score_2=s['scores'][1]['score'] if s else '',
            score_3=s['scores'][2]['score'] if s and s['scores'][2]['score'] is not None else '',
            score_total=sum(x['score'] for x in s['scores']) if s and all(x['score'] is not None for x in s['scores']) else '',
            kakao_menu_count=s['kakao_menu_count'] if s else '',
            text_photo='카카오 텍스트 메뉴와 두 지도 사진 존재 확인; 사진 속 세부 글씨 전체 판독 아님' if s else '미확인',
            kakao_business_verified=s['kakao_business_verified'] if s else '',
            menu_writer=s['menu_writer'] if s else '미확인',
            information_flags=s['information_flags'] if s else '기본 정보량·소개 길이·메뉴·가격·작성자 미확인',
            detail_evidence_records='|'.join(str(i) for (cid, p, sec), (i, cap) in detail_index.items() if cid == c['candidate_id']),
            field_count_all_channels=7 if s and c['candidate_id'] != 'MD-8995971' else '',
            field_count_note='상호·주소·전화·시간·업종·메뉴가격·공식연결의 존재 필드 수. 내용 정확성·가격 충돌은 별도 검수.' if s else '미확인')
        if c['candidate_id'] in screening:
            more = screening[c['candidate_id']]
            row['representative_menu'] = '선별 화면상 상위 메뉴: '+more['quote']
            row['information_flags'] = more.get('note', '')+' Google 상세·공식·GEO 전체 점수 미확인. '+more.get('price_status', '')
            menu_ref = detail_index.get((c['candidate_id'], 'kakao_detail', 'menu_screening'))
            row['detail_evidence_records'] = '|'.join(str(i) for (cid, p, sec), (i, cap) in detail_index.items() if cid == c['candidate_id'])
        store_rows.append(row)
        for item in (s['scores'] if s else [{'item': k, 'score': None, 'quote': '', 'reason': '상세 조사 미완료. 검색 카드만으로 채점하지 않음.'} for k in [1, 2, 3]]):
            ref = detail_index.get((c['candidate_id'], item.get('platform'), item.get('section')))
            additional = []
            for extra in item.get('additional_sources', []):
                p, section = extra.split(':', 1)
                er = detail_index.get((c['candidate_id'], p, section))
                if er:
                    additional.append({'line': er[0], 'url': er[1]['url'], 'observed_at_utc': er[1]['observed_at']})
            score_rows.append(dict(candidate_id=c['candidate_id'], name=c['kakao_name'], item=item['item'],
                score=item['score'] if item['score'] is not None else '', score_state='confirmed_observed_scope' if item['score'] is not None else 'unknown',
                quote=item['quote'], reason=item['reason'], source_url=ref[1]['url'] if ref else '',
                observed_at_utc=ref[1]['observed_at'] if ref else '', raw_capture_line=ref[0] if ref else '',
                additional_sources=json.dumps(additional, ensure_ascii=False)))
    writecsv(dest, '매장_후보_집단_검수표.csv', store_rows, list(store_rows[0]))
    writecsv(dest, 'GEO_항목별_점수_근거.csv', score_rows, list(score_rows[0]))

    special = {frozenset(p['members']): p for p in manual['close_pair_reviews']}
    pairs = []
    for a, b in itertools.combinations(candidates, 2):
        if not compatible_baseline(a, b):
            continue
        key = frozenset([a['candidate_id'], b['candidate_id']])
        review = special.get(key)
        if review:
            reason = review['reason']
        else:
            ga = screening.get(a['candidate_id'], {'food_group':a['kakao_category_card']})['food_group']
            gb = screening.get(b['candidate_id'], {'food_group':b['kakao_category_card']})['food_group']
            reason = ('동일 세부 주력 음식군 미충족: '+a['kakao_name']+' ['+ga+'] 대 '+b['kakao_name']+' ['+gb+']. 카카오 실제 상세 메뉴를 읽어 선별 제외. 부수 메뉴의 일부 공통성만으로 주력 음식군을 같게 바꾸지 않음. Google 상세·공식·GEO 전체 점수까지 확인 완료된 것은 아님.')
        pairs.append(dict(area_id=a['area_id'], candidate_1=a['candidate_id'], name_1=a['kakao_name'],
            candidate_2=b['candidate_id'], name_2=b['kakao_name'],
            kakao_rank_1=a['kakao_rank'], kakao_rank_2=b['kakao_rank'],
            google_rank_1=a['google_rank'], google_rank_2=b['google_rank'],
            rating_1=a['google_rating'], rating_2=b['google_rating'],
            reviews_1=a['google_review_count'], reviews_2=b['google_review_count'],
            basic_rank_rating_review_pass=True, decision='exclude', reason=reason,
            evidence_1=a['kakao_url']+' | '+a['google_url'], evidence_2=b['kakao_url']+' | '+b['google_url'],
            menu_quote_1=screening.get(a['candidate_id'], {}).get('quote', scored.get(a['candidate_id'], {}).get('representative_menu','미확인')),
            menu_quote_2=screening.get(b['candidate_id'], {}).get('quote', scored.get(b['candidate_id'], {}).get('representative_menu','미확인'))))
    writecsv(dest, '매칭_가능성_전수검수.csv', pairs, list(pairs[0]))
    writecsv(dest, '확정_매장쌍.csv', [], ['pair_id','area_id','A_candidate_id','B_candidate_id','selection_reason','residual_difference'])

    common = '카카오맵과 구글 지도의 공개 정보를 확인하고, 정확한 지점명, 추천 이유, 대표 메뉴·가격, 확인한 출처 링크를 제시해줘. 확인할 수 없는 사실은 추측하지 마.'
    texts = ['{area}에서 한 끼 식사하기 좋은 음식점 5곳을 추천해줘.', '{area}을 처음 방문하는 사람에게 추천할 음식점 5곳을 알려줘.', '{area}에서 대표 메뉴를 먹어볼 만한 식당 5곳을 추천해줘.']
    prompts = [dict(area_id=a, question_id=f'Q{i}', text=t.format(area=name).replace('성수을', '성수를')+'\n'+common) for a, name in AREAS.items() for i, t in enumerate(texts, 1)]
    config = dict(model_requested='gpt-6.1-sol', cli_version='codex-cli 0.166.0-alpha.5.1',
        provider_resolved_model_id='미반환: 중립 준비성 점검에서 요청 모델 실행 성공',
        web_search='live', model_reasoning_effort='low', sandbox='read-only',
        ignore_user_config=True, ephemeral=True, skip_git_repo_check=True, project_doc_max_bytes=0,
        working_directory=r'C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\geo_groups_20261103_empty',
        separation='조사 자료를 전달하지 않은 빈 작업 폴더, 새 독립 세션. 추천 측정은 아직 실행하지 않음.',
        allowed_tools='고정 CLI 내장 live web search. 로컬 파일·터미널·다른 에이전트 사용 금지 문구 예정. 실제 도구 준수는 원시 이벤트로 별도 검수.',
        recommendation_response_format='아직 실제 호출에 사용하지 않음. 후보·집단·가설 없이 추천 항목의 이름·주소·순서·메뉴·가격·출처를 공통 JSON으로 받도록 규약에 명시.',
        random_seed=20261103, planned_unique_cells=90, actual_recommendation_calls=0, prompts=prompts)
    writejson(dest, '고정_질문_모델_실행설정.json', config)
    schedule = [dict(p, repeat=r, status='not_started_cohort_unavailable', attempt_count=0) for p in prompts for r in range(1, 11)]
    random.Random(20261103).shuffle(schedule)
    for i, row in enumerate(schedule, 1):
        row['execution_order'] = i
        row['cell_id'] = f"{row['area_id']}-{row['question_id']}-R{row['repeat']:02d}"
    writecsv(dest, '전체_실행목록_90셀.csv', schedule, ['execution_order','cell_id','area_id','question_id','repeat','text','status','attempt_count'])
    writecsv(dest, '실제_추천_시도_기록.csv', [], ['attempt_id','cell_id','started_at','ended_at','returncode','status','error','raw_file'])
    readiness = [dict(kind='neutral_cli_readiness', target='카카오맵 공식 서비스 홈페이지 URL; 식당 검색 금지', status='process_success',
        error='', evidence='../readiness/20261102T160712Z.jsonl', included_in_exposure=False),
        dict(kind='api_readiness', target='Google Places; 서울특별시청', status='access_failure', error='HTTP403 API_KEY_IP_ADDRESS_BLOCKED', evidence='../readiness/official_map_api_probe.json', included_in_exposure=False),
        dict(kind='api_readiness', target='Kakao Local; 서울특별시청', status='access_failure', error='HTTP401 AccessDeniedError', evidence='../readiness/official_map_api_probe.json', included_in_exposure=False)]
    writecsv(dest, '준비성_점검_실패기록.csv', readiness, list(readiness[0]))
    writecsv(dest, '추천_매장_순서_출처_추출표.csv', [], ['attempt_id','cell_id','candidate_id','rank','name','branch','address','menu','price','unit','reason','source_url','source_support','identity_status'])
    writecsv(dest, '매장별_노출결과.csv', [], ['candidate_id','group','area_id','question_id','valid_denominator','appearance_count','exposure_pct','mean_rank_when_present'])
    group_results = [dict(area_id=a, question_id=q, group=g, store_count=0, valid_denominator=0,
        exposure_pct='', state='not_estimable_no_cohort_no_measurements') for a in list(AREAS)+['ALL'] for q in ['Q1','Q2','Q3','ALL'] for g in ['A','B']]
    writecsv(dest, '집단별_노출결과.csv', group_results, list(group_results[0]))
    writecsv(dest, '매장쌍별_노출차이.csv', [], ['pair_id','question_id','A_exposure_pct','B_exposure_pct','B_minus_A_pp'])
    known = sum(r['score_state'] != 'unknown' for r in score_rows)
    summary = dict(status='incomplete_blocked_at_cohort_formation', scope='사전 고정 검색 틀과 현재 검수 범위',
        natural_search_cards=sum(c['sponsored']=='False' for c in cards), sponsored_cards=sum(c['sponsored']=='True' for c in cards),
        possible_crossmap_candidates=len(candidates), stores_with_kakao_home_and_menu_text_read=len(scored)+len(screening), stores_with_three_item_review_records=len(scored), stores_with_three_known_scores=sum(all(x['score'] is not None for x in s['scores']) for s in scored.values()), stores_with_google_overview_and_weekly_hours_read=6,
        preliminary_baseline_pairs=len(pairs), confirmed_pairs=0, group_A_stores=0, group_B_stores=0,
        planned_cells=90, actual_recommendation_calls=0, valid_responses=0, actual_recommendation_failures=0,
        unstarted_cells=90, unknown_score_cells=len(score_rows)-known, known_score_cells=known,
        exposure_A_pct=None, exposure_B_pct=None, pair_uncertainty_interval=None,
        reason='추천 측정 전 집단 구성 미성립. 미실행은 실패나 미노출이 아님. 전체 지역에 적합 매장이 없다는 뜻이 아님.',
        region_candidates={a:sum(c['area_id']==a for c in candidates) for a in AREAS},
        region_baseline_pairs={a:sum(p['area_id']==a for p in pairs) for a in AREAS})
    writejson(dest, '진행상태_분석결과.json', summary)
    evidence_files = ['연구규약.md','검색어_범위확정_20261103.json','browser_observed.jsonl','search_cards.csv','수동검수_확정판정.json','추가_메뉴선별_판정.json','질문_문법정정_20261103.md']
    writejson(dest, '사전등록_해시_잠금상태.json', dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        restaurant_recommendation_calls_so_far=0, cohort_ready=False,
        reason='확정 쌍 0으로 측정 시작 요건 미충족. 이 파일은 완료된 A/B 집단 잠금 증명이 아님.',
        sha256={name:digest(ROOT/name) for name in evidence_files}))
    (dest/'AI_응답원문_보존상태.md').write_text('실제 식당 추천 호출은 0회다. 따라서 보존할 추천 답변 원문이 없다.\n90셀은 전부 미실행이며 실패·미노출로 계산하지 않는다.\n../readiness/20261102T160712Z.jsonl 은 식당 이름·지역 없이 실시한 중립 도구 준비성 점검 원문이며 실험 응답이 아니다.\n지도 상세 원문은 ../browser_observed.jsonl 에 별도 보존했다.\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
