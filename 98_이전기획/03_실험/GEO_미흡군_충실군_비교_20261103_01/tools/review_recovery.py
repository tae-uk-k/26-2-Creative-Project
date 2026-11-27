"""Source-linked review checkpoint. Does not select/freeze a cohort or run recommendations."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'analysis/상세검수_20261103_05'
FRAME = ROOT/'analysis/지역확대_v9_후속검수'
DEST = ROOT/'analysis/복구후_판정검수_20261103_01'


def readcsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def savecsv(name, data, fields):
    with (DEST/name).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(data)


def savejson(name, data):
    with (DEST/name).open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    inventory = readcsv(ARCHIVE/'상세_근거목록.csv')
    observed = [(row, json.loads((ROOT/row['evidence_file']).read_text(encoding='utf-8'))) for row in inventory]
    photos = readcsv(ARCHIVE/'사진_근거목록.csv')
    candidates = readcsv(FRAME/'crossmap_candidates.csv')
    findings, sources, evidence_docs = [], [], []

    def textref(sid, platform, needle, quote=None, section=None):
        matches = [(row, r) for row, r in observed if r['store_id']==sid and r['platform']==platform
                   and needle in r.get('body', '') and (not section or r['section']==section)]
        if not matches:
            raise ValueError(f'Missing actual quote: {sid} {platform} {needle}')
        row, r = matches[-1]
        quote = quote or needle
        assert quote in r['body']
        return dict(quote=quote, source_url=r['url'], observed_at=r['observed_at'],
                    evidence_file=row['evidence_file'], evidence_type='actual_detail_text', author_status='not_inferred')

    def photoref(sid, aid, quote):
        p = next(p for p in photos if p['store_id']==sid and p['asset_id']==aid)
        assert p['visually_read']=='True' and p['is_menu_asset']=='True'
        assert p['branch_scope_uncertain']=='False'
        return dict(quote=quote, source_url=p['source_url'], observed_at='2026-11-03',
                    evidence_file=p['evidence_file'], evidence_type='manual_transcription_of_visually_read_photo',
                    author_status='uploader_not_assumed_owner', observed_date_note='판독일; 사진 촬영일 아님')

    def add(sid, item, score, reason, refs, status='reviewed_provisional'):
        assert score in [0, 1, 2]
        number = len(findings)+1
        filename = f'점수근거_{number:03d}_{sid}_{item}.json'
        evidence_docs.append((filename, dict(store_id=sid, item=item, score=score, status=status, reason=reason, sources=refs,
                                            outcome_seen=False, frozen=False)))
        findings.append(dict(store_id=sid, item=item, score=score, status=status, reason=reason,
                             quote=' | '.join(x['quote'] for x in refs),
                             source_url=';'.join(x['source_url'] for x in refs),
                             observed_at=';'.join(x['observed_at'] for x in refs),
                             evidence_file=str((DEST/filename).relative_to(ROOT)), frozen=False))
        for x in refs:
            sources.append(dict(store_id=sid, item=item, **{k:x[k] for k in ['quote','source_url','observed_at','evidence_file','evidence_type','author_status']}))

    # All values remain outside the final cohort tables. No recommendation outcomes exist.
    add('SS-16879903', 1, 1, '백반·찌개 주메뉴 가격은 연결되나 인분 미표기. 삼겹살 200g 한 항목을 전체 2점으로 일반화하지 않음.',
        [textref('SS-16879903','kakao','가정식백반\n\n7,000원'), textref('SS-16879903','kakao','삼겹살(200g)')])
    add('SS-16879903', 2, 1, '확인한 주메뉴표와 사진3장에서는 일반 이용시간과 음식 목록만 연결됨. 별도 최소주문 서비스가 없다고 추정하거나 0점 감점하지 않음.',
        [textref('SS-16879903','kakao','06:00 ~ 21:00'), photoref('SS-16879903','5b4f6d33f6df0d9c','가정식백반 7,000 / 된장찌개 9,000')])
    add('SS-16879903', 3, 1, '같은 지점 전화는 일치하나 공개 주간 영업시간·일요일 휴무가 다름. 어느 쪽이 정답인지 확정하지 않음.',
        [textref('SS-16879903','kakao','일(11/8)\n휴무일'), textref('SS-16879903','google','02-464-5852')])

    add('MD-23961602', 1, 1, '주요 돈까스 단품은 메뉴·가격 연결. 정식/세트 단위는 일부 항목에만 존재. 1인1메뉴 이용 규정을 모든 메뉴의 1인분 중량 표시로 바꾸지 않음.',
        [textref('MD-23961602','kakao','남산 왕 돈까스\n\n14,000원')])
    add('MD-23961602', 2, 2, '한 펼침의 전체 주메뉴에 제공·리필 조건과 추가주문 할인이 연결되고 세트·플래터 구성도 명시됨.',
        [photoref('MD-23961602','5a4ed22663ca84be','밥, 스프, 샐러드 무한리필, 단 1인 1메뉴 주문 시 제공'),
         photoref('MD-23961602','5a4ed22663ca84be','1인 1메뉴 주문하시면, 추가 주문 시 3,000원 할인')])
    add('MD-23961602', 3, 2, '카카오·Google 동일 도로명 주소, 전화, 매일11~22 일치. 웹사이트 미등록 자체는 감점하지 않음.',
        [textref('MD-23961602','kakao','070-8847-8685'), textref('MD-23961602','google','070-8847-8685')])

    add('MD-27244728', 1, 1, '주메뉴6개 전체 가격은 메뉴판과 일치하지만 인분·중량·개수 판매 단위가 없음. 사용자 확정에 따라 1점.',
        [textref('MD-27244728','kakao','남산왕돈까스\n\n13,500원'), photoref('MD-27244728','ac12beb8949d0ad6','돈까스 13,500')])
    add('MD-27244728', 2, 1, '반반 구성·셀프 제공 안내는 일부 명확하나 일반 영업시간과 개별 메뉴 주문 조건의 연결은 부분적. 존재가 확인되지 않은 제한을 가정하지 않음.',
        [textref('MD-27244728','kakao','돈까스와 바삭하고 부드러운 생선까스가 함께 나오는 메뉴'),
         textref('MD-27244728','kakao','고추와 깍두기는 셀프 제공')])
    add('MD-27244728', 3, 1, '동일 주소·전화·공식 사이트 연결은 일치하지만 카카오22시와Google21:30 마감이 다름.',
        [textref('MD-27244728','kakao','09:00 ~ 22:00'), textref('MD-27244728','google','오전 9:00~오후 9:30')])

    add('SS-487665317', 1, 1, '대부분 파스타는 가격만, 일부 스테이크에만 중량. 주요 메뉴 전반에 단위가 있다는 2점은 부여하지 않음.',
        [textref('SS-487665317','kakao','랍스타 바질올리오')])
    add('SS-487665317', 2, 2, '식사 주문 시 기본 제공 구성과 공식 연결 홈의 주문마감 시간이 연결됨. 포장22,900원은 매장21,900원과 판매 경로를 구분함.',
        [textref('SS-487665317','official','주문 시 콘스프와 빵을 제공'), textref('SS-487665317','official','20:20')])
    add('SS-487665317', 3, 2, '동일 지점 연락처·주간시간 대조. 네이버0507은 실제 스마트콜 연결 설명을 확인하여 다른 지점 전화라고 오판하지 않음.',
        [textref('SS-487665317','kakao','02-461-0089'), textref('SS-487665317','google','02-461-0089'),
         textref('SS-487665317','official','스마트콜 번호입니다.')])

    add('SS-623393395', 1, 1, '일부 개수/중량 표시만으로 전체 주요 메뉴에 단위가 있다는2점을 주지 않음.',
        [textref('SS-623393395','kakao','메뉴 목록',quote='메뉴 목록',section='menu')])
    add('SS-623393395', 2, 2, '공식 프로필에서 연결된 해당 지점 예약 화면에 인원·룸별 최소 주문 조건이 연결됨. 지도 메뉴만 읽었을 때의 미확인 판정과 구분.',
        [textref('SS-623393395','official','200,000')])
    add('SS-623393395', 3, 1, '카카오11:30과Google11시 개점 차이. 동일 지점 소스 간 차이를 병기.',
        [textref('SS-623393395','kakao','11:30'),textref('SS-623393395','google','오전 11:00')])

    add('SS-142054376', 1, 1, '주요 파스타·피자 메뉴명과 가격은 연결되나 판매 단위는 전반적으로 미표기. 다른 상호 사진2장은 제외.',
        [textref('SS-142054376','kakao','까르보나라')])
    add('SS-142054376', 2, 2, '동일 지점 공식 예약에 1~6명, 초과인원 연락, 반려동물 접종증명, 예약 지각 취소와 주문 마감 안내가 연결됨.',
        [textref('SS-142054376','official','예약 인원 6인까지'), textref('SS-142054376','official','라스트오더는 20:00 입니다')])
    add('SS-142054376', 3, 1, '양 지도 주말 휴게시간 표기 차이를 병기. 공식 지점 링크로 Dos/Tres 분리 확인.',
        [textref('SS-142054376','kakao','15:00 ~ 17:00'),textref('SS-142054376','google','오전 11:00~오후 9:00')])

    add('MW-1355498173', 1, 1, '2인 세트는 있으나 주요 단품 파스타·리조또 전반에는 판매 단위가 없어 일부 명확1점.',
        [textref('MW-1355498173','kakao','2인')])
    add('MW-1355498173', 2, 2, '공식 프로필 연결 예약에서 실제 세트별 인원·선예약·콜키지 조건이 연결됨.',
        [textref('MW-1355498173','official','2인 세트 주문 시 와인 콜키지 1병 가능'),
         textref('MW-1355498173','official','부르고뉴 2인 세트는 예약 하실 때 체크해 주셔야 주문 가능합니다')])
    add('MW-1355498173', 3, 1, '카카오·공식 프로필과Google 개점/마감 표기 차이가 남아 있음.',
        [textref('MW-1355498173','kakao','11:00'),textref('MW-1355498173','google','오전 10:00')])

    add('MW-1992765166', 1, 1, '매장 주메뉴 일부는 200g·210g·2p, 모짜/카레 등은 단위가 없어 전반2점 보류. 배달18메뉴와 매장7메뉴를 혼합하지 않음.',
        [textref('MW-1992765166','kakao','등심돈카츠(210g)'),textref('MW-1992765166','kakao','모짜체다카츠(한정)')])
    add('MW-1992765166', 2, 1, '한정수량이라는 실제 조건은 있지만 확인한 전체 매장 메뉴표에는 수량·주문시간이 연결되지 않음. 다른 일부 구성은 명확하여1점 검토값.',
        [photoref('MW-1992765166','b60d2d566cfd4f26','모짜 체다 카츠(한정수량) 13,000')])

    # Validate all source quotes before writing a new checkpoint.
    DEST.mkdir(exist_ok=False)
    for filename, document in evidence_docs:
        savejson(filename, document)
    # Unknown/unreviewed items never become zero or enter the frozen tables.
    ids = sorted({r['store_id'] for r in inventory})
    for sid in ids:
        for item in [1,2,3]:
            if not any(x['store_id']==sid and x['item']==item for x in findings):
                findings.append(dict(store_id=sid,item=item,score='',status='not_yet_adjudicated',reason='채널·주요 메뉴 범위 또는 지점 일관성 추가 검수 필요. 0점 대체 금지.',quote='',source_url='',observed_at='',evidence_file='',frozen=False))
    savecsv('GEO_항목별_재검수.csv', findings, list(findings[0]))
    savecsv('실제문구_출처표.csv', sources, list(sources[0]))

    profiles=[]
    for sid in ids:
        rr=[r for row,r in observed if r['store_id']==sid]
        links=[c for c in candidates if c['store_id']==sid]
        scored=[r for r in findings if r['store_id']==sid]
        known=[r for r in scored if r['score']!='']
        total=sum(r['score'] for r in known) if len(known)==3 else None
        label='A 점수 범위 후보' if total is not None and total<=3 else 'B 점수 범위 후보' if total is not None and total>=5 else '4점 제외 후보' if total==4 else '채점 미완료'
        profiles.append(dict(store_id=sid,area_id=sid.split('-')[0],name=links[0]['name'] if links else '',
            address=links[0]['kakao_address'] if links else '', kakao_id=sid.split('-')[1],kakao_url='https://place.map.kakao.com/'+sid.split('-')[1],
            google_ids_unadjudicated=';'.join(sorted({c['google_id'] for c in links})),
            kakao_detail=any(r['platform']=='kakao' for r in rr), google_detail=any(r['platform']=='google' for r in rr),
            official_detail=any(r['platform']=='official' for r in rr),reviewed_items=len(known),score_total=total if total is not None else '',
            candidate_class=label, final_group='',pair_id='',final_selection=False,
            note='자동연결 Google ID는 동일 지점 확정 아님. 후보 점수는 주분석 표본 확정 아님.'))
    savecsv('후보별_검수현황.csv',profiles,list(profiles[0]))

    matching=[
        dict(case='SS-01',store_A='SS-16879903',store_B='SS-1632057090',search_query='서울 성수역 백반',condition='station_v1',kakao_rank_A=12,kakao_rank_B=20,google_rank_A=8,google_rank_B=15,decision='보류',reason='장흥 백반7000 대 채육 제육정식13500은1.929배. 찌개9000 대12000은 숫자만 맞지만 채육 메뉴판12500과 충돌하여 비교가격 미확정. 채육 총점도 미확정.'),
        dict(case='SS-02',store_A='SS-465733251',store_B='SS-487665317',search_query='서울 성수동 파스타',condition='default',kakao_rank_A=1,kakao_rank_B=16,google_rank_A=29,google_rank_B=7,decision='순위 기준 불충족',reason='Google 자연순위차22>고정20. 파르코의 A분류도 미확정이므로 점수 확정 매칭쌍이 아님.'),
        dict(case='MD-01',store_A='MD-453813079',store_B='MD-13050974',search_query='서울 명동 파스타',condition='default',kakao_rank_A=6,kakao_rank_B=5,google_rank_A=6,google_rank_B=1,decision='리뷰 규모 기준 불충족',reason='Google 리뷰46 대925, 비율20.109>고정8. 양 점수 미확정.'),
        dict(case='MD-02',store_A='MD-27244728',store_B='MD-23961602',search_query='서울 명동역 돈까스',condition='station_v1',kakao_rank_A=20,kakao_rank_B=36,google_rank_A=22,google_rank_B=7,decision='주분석 보류',reason='가격13500/14000, 평점3.5/3.9, 리뷰1021/359는 수치조건 통과. 소파로 회현역 접근권 대 명동7길 을지로입구역 접근권 차이가 남아 유사 위치 매칭과 A의 조건 범위를 추가 검수. 억지로 같은 위치로 확정하지 않음.'),
        dict(case='MW-01',store_A='MW-1992765166',store_B='MW-740043035',search_query='서울 망원역 돈까스',condition='station_v1',kakao_rank_A=23,kakao_rank_B=9,google_rank_A=5,google_rank_B=1,decision='가격·집단 보류',reason='정성 매장등심12500(210g)과 배달13500(200~220g)은 판매경로 구분. 망원돈까스 등심은K텍스트11000 대 실제메뉴판12000 차이. 가격을 하나로 확정하지 않았으며 양 집단도 미확정.')]
    savecsv('매칭_보류근거.csv',matching,list(matching[0]))

    coverage=[]
    for row in readcsv(FRAME/'native_cards.csv'):
        key=(row['platform'],row['area_id'],row['query'],row['condition_id'])
        existing=next((x for x in coverage if (x['platform'],x['area_id'],x['query'],x['condition_id'])==key),None)
        if not existing:
            existing=dict(platform=key[0],area_id=key[1],query=key[2],condition_id=key[3],unique_places=0,max_observed_rank=0)
            coverage.append(existing)
        existing['unique_places']+=1
        existing['max_observed_rank']=max(existing['max_observed_rank'],int(row['rank']))
    savecsv('검색조건별_실제확보범위.csv',coverage,list(coverage[0]))
    counts=dict(reviewed_stores=len(ids),item_rows=len(findings),scored_review_items=sum(r['score']!='' for r in findings),
                pending_items=sum(r['score']=='' for r in findings),candidate_classes=dict(Counter(p['candidate_class'] for p in profiles)),
                finalized_pairs=0,restaurant_attempts=0,recommendation_results_seen=False,
                scoring_note='모든 점수는 조사 근거에 대한 검토값. 최종 채널 범위·매칭 확정 전이므로 주분석 집단에 편입하지 않음.',
                checked_at_utc=datetime.now(timezone.utc).isoformat())
    savejson('검수요약.json',counts)
    manifests=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(DEST.rglob('*')) if p.is_file()]
    savecsv('산출물_해시.csv',manifests,['path','sha256'])
    print(json.dumps(counts,ensure_ascii=False))


if __name__=='__main__':main()
