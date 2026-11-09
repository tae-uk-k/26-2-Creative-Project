"""Freeze-ready, evidence-backed small cohort; preserve earlier empty forms.

This prepares the one currently adjudicated pair, not the target 12 pairs.
No recommendation output is read. All quotations must exist in observed text.
"""
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'analysis' / '확정표본_20261103_01'
FRAME = ROOT / 'analysis' / '지역확대_v11_성수스크롤복구'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def readcsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    assert not (ROOT / 'cohort_lock.json').exists()
    assert not list((ROOT / 'raw').glob('*.jsonl'))
    DEST.mkdir(exist_ok=False)
    (DEST / 'sources').mkdir()
    (DEST / 'menu_photos').mkdir()
    obs = [json.loads(line) for line in (ROOT / 'evidence/browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    source_cache = {}

    def source(sid, platform, section, quote):
        matches = [(i, r) for i, r in enumerate(obs, 1) if r.get('kind') == 'detail' and r.get('store_id') == sid and r.get('platform') == platform and r.get('section') == section and quote in r.get('body', '')]
        assert matches, (sid, platform, section, quote)
        index, r = matches[-1]
        if index not in source_cache:
            path = DEST / 'sources' / f'{index:03d}_{sid}_{platform}_{section}.json'
            save(path, r)
            source_cache[index] = path
        path = source_cache[index]
        return dict(quote=quote, source_url=r['url'], observed_at=r['observed_at'], evidence_file=str(path.relative_to(ROOT)), sha256=digest(path), evidence_type='actual_detail_text', writer_status='not_inferred')

    scores = []

    def score(sid, item, value, reason, refs):
        path = DEST / f'{sid}_item_{item}.json'
        obj = dict(store_id=sid, item=item, score=value, status='confirmed', reason=reason, sources=refs, adjudicated_at_utc=datetime.now(timezone.utc).isoformat(), recommendation_outputs_seen=False)
        save(path, obj)
        scores.append(dict(store_id=sid, item=item, score=value, status='confirmed', quote=' | '.join(x['quote'] for x in refs), source_url=';'.join(x['source_url'] for x in refs), observed_at=';'.join(x['observed_at'] for x in refs), evidence_file=str(path.relative_to(ROOT)), reason=reason, writer_status='not_inferred'))

    a, b = 'SS-465733251', 'SS-487665317'
    score(a, 1, 1, '확인한 주메뉴의 명칭·가격은 연결되어 있으나 기본 인분·중량이 명시되지 않음. 메뉴판의 일부 음료 용량으로 주메뉴 전반을 2점 처리하지 않음.', [source(a, 'kakao', 'menu', '버섯치즈 리조또\n\n20,800원')])
    score(a, 2, 1, '메뉴 옵션과 예약 인원 일부는 명확하지만, 식사 서비스를 이용할 수 있는 마감 시간이 카카오 21:30, Google 화~일 20:00 및 월 22:30으로 다름. 공통 채점의 채널별 차이=1점 적용. 존재 미확인 최소주문·라스트오더를 가정하지 않음. 이 영업시간 차이가 항목3에도 기여하므로 두 항목을 독립 특성으로 해석하지 않음.', [source(a, 'official', 'linked_booking', '1~4명'), source(a, 'kakao', 'home_hours', '11:30 ~ 21:30'), source(a, 'google', 'overview_hours', '오후 5:00~8:00')])
    score(a, 3, 1, '동일 도로명 지점은 확인했지만 주간 마감 시간이 다르고 Google 상세는 전화·웹사이트 추가 요청을 표시함. 공식 연결 페이지의 번호를 임의로 지도 전화와 같다고 확정하지 않음.', [source(a, 'kakao', 'home_hours', '서울 성동구 서울숲2길 44'), source(a, 'google', 'overview_hours', '서울특별시 성동구 서울숲2길 44'), source(a, 'google', 'overview_hours', '장소의 전화번호 추가'), source(a, 'kakao', 'home_hours', '11:30 ~ 21:30'), source(a, 'google', 'overview_hours', '오후 5:00~8:00')])
    score(b, 1, 1, '주요 파스타의 메뉴·가격은 연결되지만 인분·중량은 미표시. 일부 스테이크250g·음료 용량만으로 주메뉴 전반을 2점 처리하지 않음.', [source(b, 'kakao', 'menu', '랍스타 바질올리오')])
    score(b, 2, 2, '식사 주문에 따른 기본 제공 구성과 매일20:20 주문마감이 해당 지점의 식사 서비스에 연결됨. 포장 가격22,900원은 포장 항목임을 기록하며 매장 단품21,900원과 섞지 않음.', [source(b, 'official', 'booking_seller_info', '주문 시 콘스프와 빵을 제공'), source(b, 'official', 'linked_weekly_hours', '20:20 라스트오더')])
    score(b, 3, 2, '두 지도에서 동일 주소·전화 및 평일/주말 영업시간 일치. 공식 연결 홈에서도 주간시간 대조. 0507번호는 실제 지점 연결 스마트콜 설명을 확인함.', [source(b, 'kakao', 'home_hours', '02-461-0089'), source(b, 'google', 'overview_hours', '02-461-0089'), source(b, 'official', 'linked_phone_explanation', '스마트콜 번호입니다.'), source(b, 'official', 'linked_weekly_hours', '11:30 - 21:00'), source(b, 'official', 'linked_weekly_hours', '11:00 - 21:00')])

    cards = readcsv(FRAME / 'native_cards.csv')
    native = [r for r in cards if r['area_id'] == 'SS' and r['query'] == '서울 성수동 파스타' and r['condition_id'] == 'default' and r['place_id'] in ['465733251', '487665317', 'ChIJQ3ayrkGlfDURzlcSDToJTwo', 'ChIJG5j-_5ukfDURw4TPvEKfIPY']]
    assert len(native) == 4
    save(DEST / '동일검색어_원래순위.json', native)
    photo_manifest = []
    for sid in [a, b]:
        bundles = [r for r in obs if r.get('kind') == 'detail' and r.get('store_id') == sid and r.get('section') == 'menu_photo_bundle']
        assert bundles
        for asset in bundles[-1]['bundle']['assets']:
            src = Path(asset['path'])
            if not src.exists():
                copies = sorted((ROOT / 'analysis').glob(f"상세검수_*/menu_photos/{sid}_{asset['id']}.*"))
                assert copies
                src = copies[-1]
            dst = DEST / 'menu_photos' / f"{sid}_{asset['id']}.jpg"
            with src.open('rb') as f, dst.open('xb') as g:
                shutil.copyfileobj(f, g)
            assert digest(src) == digest(dst)
            photo_manifest.append(dict(store_id=sid, asset_id=asset['id'], source_url=asset['url'], evidence_file=str(dst.relative_to(ROOT)), sha256=digest(dst), visually_read=True, writer_verified=False))
    save(DEST / '확인한_메뉴판_이미지.json', photo_manifest)

    stores = []
    for sid, group, name, address, menu, price, values in [
        (a, 'A', '파르코 서울숲점', '서울 성동구 서울숲2길 44 1층', '버섯치즈 리조또', 20800, [1,1,1]),
        (b, 'B', '미테이블 성수본점', '서울 성동구 왕십리로8길 5 1층', '랍스타 바질올리오', 21900, [1,2,2])]:
        kid = sid.split('-')[1]
        k = next(r for r in native if r['platform']=='kakao' and r['place_id']==kid)
        g = next(r for r in native if r['platform']=='google' and (r['name']=='파르코' if sid==a else r['name']=='미테이블 성수본점'))
        relevant = [r for r in obs if r.get('store_id')==sid and r.get('section') in ['home_hours','overview_hours']]
        profile = dict(store_id=sid, name=name, address=address, same_branch_evidence='두 지도 도로명·건물번호 일치. 지도 지점명 생략/별칭을 주소와 함께 대조.', kakao_phone='02-467-8588' if sid==a else '02-461-0089', google_phone=None if sid==a else '02-461-0089', current_operation_basis='2026-11-03 네이티브 검색의 영업중 표시, 당일 지점 상세의 영업 안내. 현장 방문 검증은 수행하지 않음.', menu_count_reported=19, basic_fields_present=['name','address','phone_in_at_least_one_public_channel','hours','cuisine','priced_meal','official_link'], official_authorship_verified=False, menu_photos=photo_manifest, observation_records=relevant)
        save(DEST / f'{sid}_매장근거.json', profile)
        stores.append(dict(store_id=sid, pair_id='SS-P01', area_id='SS', group=group, name=name, branch='서울숲점' if sid==a else '성수본점', address=address, kakao_id=kid, kakao_url=k['url'], google_id=g['place_id'], google_url=g['url'], food_group='이탈리안 캐주얼 식사(파스타·리조또 포함)', representative_menu=menu, price_krw=price, sale_unit='메뉴표의 식사 단품 가격(인분 미표시)', hours='카카오 매일11:30~21:30 BT15~17 / Google 화~일11:30~15,17~20 월17~22:30; 불일치 병기' if sid==a else '월~금11:30~21:00 토~일11:00~21:00; 공식 연결20:20LO', conditions='옵션·예약1~4명은 일부 명확. 채널별 서비스 마감시간 차이.' if sid==a else '식사 주문 시 콘스프·빵 제공; 매일20:20LO', search_query='서울 성수동 파스타', kakao_rank=k['rank'], google_rank=g['rank'], google_rating=g['rating'], google_reviews=g['reviews'], basic_fact_count=7, text_present='true', photo_present='true', score_1=values[0], score_2=values[1], score_3=values[2], score_total=sum(values), identity_verified='true', operation_verified='true', meal_eligible='true', source_evidence=str((DEST / f'{sid}_매장근거.json').relative_to(ROOT)), observed_at=f"K:{k['observed_at']};G:{g['observed_at']}", residual_difference='카카오 주업종 피자 vs 양식. 파르코는 피자·파스타·리조또, 미테이블은 스테이크·파스타를 주메뉴로 제공. 둘 다 실제 다수의 이탈리안 식사 메뉴를 갖춤. Google순위24vs6, 기본 전화의 채널별 존재 차이, 영업시간 차이의 항목2·3 중복 기여, 카카오평점4.4vs4.7 및 후기300vs531을 보정하지 못함.', search_condition_id='default'))

    # Both earlier files are generated, header-only forms. Preserve by moving to
    # an explicit in-study archive, without deleting or overwriting any data.
    old_forms = DEST / '기존_빈양식_보존'
    old_forms.mkdir()
    for name, data in [('매장_집단_매칭표.csv', stores), ('GEO_항목별점수.csv', scores)]:
        original = ROOT / name
        assert readcsv(original) == [], 'Refuse to replace existing study data'
        original.rename(old_forms / name)
        with original.open('x', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, list(data[0]))
            w.writeheader()
            w.writerows(data)
    save(DEST / '검수_고정전상태.json', dict(target_pairs=12, actual_pairs=1, target_stores=24, actual_stores=2, pairs_by_area={'MD':0,'SS':1,'MW':0}, scope_complete=False, actual_recommendation_attempts_before_selection=0, scores_finalized_before_outcomes=True, selected_stores=[a,b], native_frame_version=FRAME.name, note='목표 표본 미달. 미검수 후보가 남아 있으므로 지역 내 적합한 매장이 존재하지 않는다고 결론내리지 않음. 명동·망원 응답은 실행되더라도 집단비교 분모로 사용하지 않음.'))
    print(json.dumps(dict(prepared=True, pairs=1, stores=2, output=str(DEST)), ensure_ascii=False))


if __name__ == '__main__':
    main()
