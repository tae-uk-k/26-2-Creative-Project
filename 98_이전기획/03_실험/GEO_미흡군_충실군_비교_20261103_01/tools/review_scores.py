"""Sourced partial adjudication; unknown items prohibit group assignment."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'analysis/상세검수_20261103_03'


def main():
    with (DEST/'상세_근거목록.csv').open(encoding='utf-8-sig', newline='') as file:
        evidence = list(csv.DictReader(file))
    latest = {(row['store_id'], row['platform'], row['section']): row for row in evidence}
    output = []

    def item(sid, number, score, sources, reason, pending=''):
        citations = []
        for platform, section, quote in sources:
            row = latest[sid, platform, section]
            body = json.loads((ROOT/row['evidence_file']).read_text(encoding='utf-8'))['body']
            assert quote in body, (sid, number, quote)
            citations.append(dict(quote=quote, url=row['source_url'], observed_at=row['observed_at'], evidence_file=row['evidence_file']))
        output.append(dict(store_id=sid, item=number, score=score, status='confirmed' if score!='미확인' else 'unknown',
            reason=reason, pending=pending, evidence=json.dumps(citations, ensure_ascii=False),
            classification_final=False, used_in_recommendation_measurement=False))

    item('MD-453813079',1,1,[('kakao','menu','비프타르타르(4pc)'),('kakao','menu','Cacio e Pepe\n\n21,000원')],
         '수량이 연결된 전채와 가격이 연결된 주요 식사가 함께 확인된다. 전체 메뉴와 확보된 메뉴판 1장을 검수했지만, 전채 4pc만으로 주요 메뉴 전반의 판매 단위가 명확하다고 채점하지 않는다.')
    item('MD-453813079',2,'미확인',[('kakao','home_hours','콜키지 부과')],
         '실제 제공되는 유료 서비스는 확인했으나 구체적 적용 조건 확인이 남았다. 존재하지 않는 서비스의 설명 부재로 감점하지 않는다.',
         '연결된 공식 안내와 주요 메뉴 이용 조건 추가 확인')
    item('MD-453813079',3,1,[('kakao','home_hours','15:00 ~ 17:00 브레이크타임'),('google','overview_hours','Break 15:30 - 17:00 **Tue OFF')],
         '같은 주소의 지점에서 평일 휴게 시작 시각이 30분 다르게 표시된다. 어느 값을 실제 운영의 정답으로 선택하지 않는다.')

    item('SS-623393395',1,1,[('kakao','menu','마늘빵 4PCS\n\n4,500원'),('kakao','menu','새우 오일 파스타\n\n21,500원')],
         '27개 텍스트 메뉴를 확인했다. 곁들임 빵의 개수는 명확하지만 주요 파스타·리조또·스테이크 전반의 판매 단위가 명시된 것으로 처리하지 않는다. 메뉴판 분류 사진 1장은 POS 주문 목록이었다.')
    item('SS-623393395',2,'미확인',[('kakao','menu','허니갈릭버터소스, 렌치소스, 카레마요, 토마토 소스 중 택 1')],
         '사이드 두 품목의 선택 조건은 확인됐다. 재료·조리 설명을 주문 조건으로 바꾸지 않고, 주요 조건 전반을 판단하기 위한 공식 안내 검수를 남긴다.',
         '사이드 선택 조건만으로 매장 전체 2점을 부여하지 않음')
    item('SS-623393395',3,1,[('kakao','home_hours','11:30 ~ 22:00'),('google','overview_hours','오전 11:00에 영업 시작'),('google','overview_hours','070-4101-1408')],
         '동일 건물·층과 연락처가 확인되지만 관측된 영업 시작 시각은 30분 다르다. Google 전체 주간표는 펼쳐지지 않았으므로 전체 주간표를 확인했다고 기록하지 않는다.')

    item('SS-487665317',1,1,[('kakao','menu','채끝 스테이크(250g)\n\n39,900원'),('kakao','menu','랍스타 바질올리오\n\n21,900원')],
         '중량이 명시된 스테이크와 단위가 암묵적인 주요 파스타가 함께 있다. 확보한 사진 18장을 판독했으며 일부 스테이크 중량만으로 전체에 2점을 부여하지 않는다. 지도 표시 19장 중 미확보 1장은 미확인이다.')
    item('SS-487665317',2,'미확인',[('official','linked_business_info','콜키지 유료'),('official','linked_business_info','최소 2명 ~ 최대 6명')],
         '단체석 인원 조건, 유료 콜키지, 과거 메뉴 사진의 런치 시간·면 추가 조건을 확인했다. 현재 주요 조건의 전반적 연결 여부와 콜키지 세부 조건 확인이 남아 2점으로 확정하지 않는다.',
         '연결된 포장 주문 가격은 매장 식사 가격과 구분; 오래된 사진의 런치 조건을 현재 조건으로 자동 확정하지 않음')
    item('SS-487665317',3,'미확인',[('kakao','home_hours','02-461-0089'),('google','overview_hours','02-461-0089'),('official','linked_business_home_uitree','0507-1434-0089')],
         '카카오·Google의 전화와 주간 영업시간은 일치한다. Google 연결 업체 홈에 표시된 0507 번호와 일반 번호의 연결 관계, 공식 안내의 주간 시간 확인이 끝나지 않아 채널 전체 일관성 2점은 보류한다.',
         '0507 번호가 다르다는 이유만으로 서로 다른 실제 전화라고 단정하지 않음; 연결 홈의 원래 UI 관측 원문을 별도로 보존했음')

    item('MW-1181461605',1,'미확인',[('kakao','menu','마르게리따 피자\n\n15,500원'),('kakao','menu','까르보나라\n\n11,900원')],
         '판독한 사진 4장에는 피자 S/L와 빵 개수가 있지만 주요 파스타는 단위가 암묵적이다. 확보 22장 중 18장은 미판독이므로 최종 점수는 보류한다.',
         '미판독 18장 검수')
    item('MW-1181461605',2,'미확인',[('kakao','home_hours','목요일은 개인 사정으로 쉬는 날이 종종 있습니다.')],
         '일부 사진에서 매운맛 조절 문구를 확인했다. 전체 사진 검수가 끝나지 않아 주요 이용 조건 전체에 2점을 부여하지 않는다.',
         '미판독 사진의 추가 이용 조건 확인')
    item('MW-1181461605',3,1,[('kakao','home_hours','11:20 ~ 22:00'),('google','overview_hours','오전 11:30~오후 10:00')],
         '동일 주소·전화의 지점이며 개점 시각이 10분 다르게 표시된다. 실제 운영시간의 정답은 선택하지 않는다.')

    item('MW-1355498173',1,1,[('kakao','menu','브런치 라자냐 2인세트\n\n48,000원')],
         '세트 인원·가격은 명확하나 판독한 메뉴 사진 5장의 주요 단품 식사 전반에 명시적 판매 단위가 있다고 볼 수 없어 1점이다. 2인 세트를 임의로 1인 가격으로 나누지 않는다.')
    item('MW-1355498173',2,'미확인',[('kakao','home_hours','콜키지 부과')],
         '사진의 추가 선택 가격은 일부 명확하다. 콜키지 등 실제 제공 서비스와 주요 세트 구성의 현재 조건 검수가 남아 전체 2점은 보류한다.',
         '공식 안내의 현재 조건 확인')
    item('MW-1355498173',3,1,[('kakao','home_hours','11:00 ~ 23:00'),('google','overview_hours','오전 10:00~오후 3:00\n오후 5:00~10:00')],
         '전화와 주소는 일치하지만 주중 개·폐점 시간이 각각 다르게 표시된다. 두 값을 모두 보존한다.')

    path = DEST/'GEO_점수_사용자기준재검수.csv'
    with path.open('x', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, list(output[0])); writer.writeheader(); writer.writerows(output)
    summaries = []
    for sid in sorted({row['store_id'] for row in output}):
        rows = [row for row in output if row['store_id']==sid]
        known = all(row['score']!='미확인' for row in rows)
        total = sum(row['score'] for row in rows) if known else None
        summaries.append(dict(store_id=sid, score_total=total, unknown_items=[row['item'] for row in rows if row['score']=='미확인'],
            group=None if total is None or total==4 else 'A' if total<=3 else 'B', selected=False))
    with (DEST/'GEO_집단판정_보류.json').open('x', encoding='utf-8') as file:
        json.dump(summaries, file, ensure_ascii=False, indent=2)
    print(json.dumps(dict(items=len(output), source_quotes_verified=True, groups_finalized=0), ensure_ascii=False))


if __name__=='__main__':
    main()
