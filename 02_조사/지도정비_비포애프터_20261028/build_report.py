from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
criteria_source = ROOT.parent / 'seelo_지도정보_정비기준_20261028.md'
if criteria_source.is_file():
    (ROOT / 'evidence' / '정비기준.md').write_text(criteria_source.read_text(encoding='utf-8'), encoding='utf-8')
source_index = json.loads((ROOT / 'evidence/sources.json').read_text(encoding='utf-8'))
STORE_META = [
    ('hiss', '힛사츠와자', '망원', '일본식 라면', '서울 마포구 포은로 97-1 1층', 'hiss-kakao-menuboard.jpg'),
    ('yuk', '육통령 명동본점', '명동', '고기구이', '서울 중구 명동8나길 37-2 1층', 'yuk-kakao-menu.jpg'),
    ('oreno', '오레노카츠 성수본점', '성수', '돈카츠', '서울 성동구 성수일로 47 1층 102호', 'oreno-kakao-home.jpg'),
    ('jung', '정각 서울망원본점', '망원', '숙성 돼지고기', '서울 마포구 망원로6길 57 2층', 'jung-kakao-brand.jpg'),
    ('pizza', '명동피자 명동본점', '명동', '피자·파스타', '서울 중구 명동10길 41 4층', 'pizza-kakao-menu.jpg'),
    ('plant', '플랜트 연남점', '연남', '비건 레스토랑', '서울 마포구 월드컵북로4길 87 1층', 'plant-official-menu.jpg'),
]
stores = []
for sid, name, area, food, address, image in STORE_META:
    sources = {s['provider']: s['url'] for s in source_index if s['store'] == name}
    if sid == 'plant':
        sources['official'] = 'https://plantcafeseoul.com/plant-yeonnam/'
        sources['official-menu'] = 'https://plantcafeseoul.com/plant-yeonnam-menu/'
    stores.append(dict(id=sid, name=name, area=area, food=food, address=address, image=image, sources=sources))

def row(label, value, note='', state=''):
    return dict(label=label, value=value, note=note, state=state)

def panel(rows=None, text='', note='', image='', tags=None):
    return dict(rows=rows or [], text=text, note=note, image=image, tags=tags or [])

cases = []
def add(id, store, category, status, title, lead, target, amount, before, after, changes, keep, check, reason, evidence, facts, sources=None):
    cases.append(dict(id=id, store=store, category=category, status=status, title=title, lead=lead,
        target=target, amount=amount, before=before, after=after, changes=changes, keep=keep,
        check=check, reason=reason, evidence=evidence, facts=facts, sources=sources or ['google', 'kakao']))

add('01','plant','기본정보','정정안','다른 지점의 대표번호가 연결돼 있다면',
    '전화번호 한 칸을 연남 지점 번호로 정정한다. 상호·주소·리뷰는 건드리지 않는다.',
    'Google · 전화번호','전화번호 1칸',
    panel([row('Google 공개 번호','02-749-1981'),row('카카오 공개 번호','02-337-1982'),row('공식 연남 지점','02 337 1982')],note='Google의 번호는 공식 사이트 하단 이태원 대표번호와 같다.'),
    panel([row('Google 전화번호','02-337-1982','공식 연남 지점 안내와 일치','changed'),row('주소','월드컵북로4길 87','기존 지점 주소 유지')],note='교차 확인한 정정안. 실제 변경은 소유자 승인·관리 권한 확인 후.'),
    'Google 전화번호만 정정','주소·가게 이름·예약 링크·메뉴·리뷰',
    '지점에서 현재 사용하는 대표번호인지 최종 확인',
    '같은 브랜드의 사이트 하단 회사 연락처를 해당 지점 연락처로 사용하면 잘못 연결될 수 있다.',
    ['plant-google-home.jpg','plant-kakao-home.jpg','plant-official-branch.jpg'],
    ['두 지도 주소는 월드컵북로4길 87로 일치한다.','공식 연남 지점 본문은 02 337 1982, 사이트 하단 이태원 회사 안내는 02-749-1981이다.'],
    ['google','kakao','official'])

add('02','hiss','기본정보','확인대기','시간·전화가 비어 있을 때는 소개를 늘리지 않는다',
    '카카오에 공개된 시간·전화는 후보 근거다. 최신 운영 여부를 확인해 Google 전용 칸에 넣는다.',
    'Google · 영업시간·전화','최대 2칸 후보',
    panel([row('Google 전화','장소의 전화번호 추가'),row('Google 시간','영업시간 추가'),row('카카오 관측','11:30–19:30 / 휴게 14:30–17:00')]),
    panel([row('전화번호 후보','02-332-2115','현행 대표번호 확인 필요','pending'),row('영업시간 후보','화–일 11:30–14:30 / 17:00–19:30','카카오 10/28–11/3 주간 표시 기준','pending'),row('휴무 후보','월요일 휴무','임시 일정인지 정기 일정인지 확인','pending')],note='소개에 시간표·전화번호를 붙이지 않고 각각의 입력 칸을 사용한다.'),
    '시간·전화의 빈 칸만 보완','상호·기존 메뉴 설명·사진·리뷰',
    '정규 영업·임시 영업·라스트오더와 번호의 최신성',
    '공개 화면의 누락은 확인했지만 다른 지도 값의 현재성을 자동 보증할 수는 없다.',
    ['hiss-google-overview.jpg','hiss-kakao-hours.jpg'],
    ['Google 개요에 전화·영업시간 추가 안내가 노출됐다.','카카오의 해당 주간에는 월 휴무, 나머지 요일 11:30–19:30와 휴게시간이 표시됐다.'])

add('03','hiss','메뉴·가격','확인대기','사진에서 읽은 가격은 텍스트 메뉴의 후보로',
    '사진은 보존한다. 판독한 가격과 현재 판매를 확인한 뒤, 기존 메뉴의 가격 보완과 새 항목 추가를 구분한다.',
    '카카오 · 메뉴별 가격','가격 후보 3개',
    panel([row('공개 텍스트','매운츠케멘 · 츠케멘','확인한 텍스트 항목에는 가격이 보이지 않았다.')],image='hiss-kakao-menuboard.jpg',note='블로그에서 제공된 메뉴판 사진. 업주 원본·가격 적용일은 확인하지 않았다.'),
    panel([row('매운츠케멘','13,000원','사진에서 판독 / 최신성 확인 전','pending'),row('차슈멘','15,500원','기존 등록 중복 여부 확인','pending'),row('매운 차슈멘','16,500원','기존 등록 중복 여부 확인','pending')],note='새 항목을 무조건 3개 만들지 않는다. 이미 있는 메뉴는 가격만 채운다.'),
    '확정한 메뉴의 누락 가격·미등록 항목만 보완','기존 메뉴명·사진 원본·정상 항목',
    '사장님 최신 메뉴판, 단위·조건, 동일 메뉴 중복, OCR 처리 가능 범위',
    '사진은 검색·번역에 사용할 텍스트와 역할이 다르다. 사진 업로드 시점만으로 현재 가격을 확정하지 않는다.',
    ['hiss-kakao-menuboard.jpg','hiss-kakao-menu.jpg'],
    ['메뉴 탭에서 가격 없는 텍스트 메뉴와 메뉴판 사진을 함께 확인했다.','열람한 사진에는 13,000·15,500·16,500원 금액이 보인다. 현행 판매가격으로 독립 확인하지 않았다.'])

add('04','hiss','메뉴·가격','표현정리','긴 한·영 옵션 설명은 사실을 지우지 않고 나눈다',
    '계란·기본 토핑·면 중량·무료 요청사항을 짧은 줄로 정리한다. 판매 조건과 영어는 보존한다.',
    'Google · 차슈멘 메뉴 설명','설명 1칸',
    panel(text='계란기본제공 x … 기본제공 … 면중량 [선택] … 요청사항 [선택] …',note='같은 옵션이 한국어와 영어로 한 문단에 길게 이어진다. 원본 화면에서 전체 문구 확인 가능.'),
    panel([row('기본 구성','계란 미포함 · 차슈 2장 · 멘마 2개 · 김 1장','No egg. Chashu ×2, menma ×2, nori ×1.','changed'),row('면 중량','150g·200g 추가금 없음 / 300g +1,000원','Noodles: 150/200 g included; 300 g +KRW 1,000.','changed'),row('무료 요청','초생강 / 멘마 제외 / 적양파 많이','Free requests: pickled ginger; no menma; extra red onion.','changed')],note='실제 입력은 메뉴 설명 한 칸 안의 줄바꿈이다. 별도 옵션 칸이 있다고 가정하지 않는다.'),
    '설명 한 칸의 줄·순서·번역 표현만 정리','계란 미포함·추가금·토핑 수량·요청 옵션 전부',
    '기존 옵션의 현행성 및 해당 편집 칸의 줄바꿈 지원',
    '짧게 만드는 과정에서도 무료 옵션과 유료 중량을 합치거나 누락하면 안 된다.',
    ['hiss-google-menu.jpg'],
    ['Google 메뉴의 차슈멘 카테고리에서 수량·면 중량·요청 옵션의 한·영 문구를 확인했다.','새 가격·재료를 추가한 사례가 아니라 기존 사실의 표현 정리안이다.'])

add('05','yuk','메뉴·가격','표현정리','같은 원화 가격이어도 단위가 다르다',
    '280g 고기와 공깃밥 별도 찌개를 같은 한 끼 가격으로 요약하지 않는다.',
    '카카오 · 메뉴 설명','가격 0칸 / 설명 2칸',
    panel([row('소 양념왕갈비 (280g)','48,000원'),row('숙성김치찌개(공기밥별도)','8,000원')]),
    panel([row('소 양념왕갈비 (280g)','48,000원 / 280g','Marinated beef short rib, 280 g.','changed'),row('숙성김치찌개(공기밥별도)','8,000원 / 공깃밥 별도','Kimchi stew. Rice is charged separately.','changed')],note='최소 주문량·밥 가격은 확인하지 않았으므로 추가하지 않는다.'),
    '필요한 메뉴 설명에서 단위·별도 비용을 명확히 표시','현재 메뉴명·가격·다른 메뉴·사진',
    '최소 주문량 및 공깃밥 가격은 별도 확인',
    '8,000원을 1인 식사 총액으로 바꾸거나 280g을 임의의 인원 수로 나누지 않는다.',
    ['yuk-kakao-menu.jpg'],
    ['카카오 메뉴에 280g, 공기밥별도 문구가 실제 포함돼 있다.','현재 금액은 유지하고 필요한 영문 설명만 제안한다.'])

add('06','yuk','메뉴·가격','확인대기','고가 메뉴 두 개만으로 가게를 대표하지 않는다',
    '구이와 식사 메뉴를 함께 검토해 추천 표시 후보를 고른다. 정상 메뉴 전체는 유지한다.',
    '카카오 · 추천 상품 표시','추천 표시 최대 2개 검토',
    panel([row('먼저 보인 메뉴','소 양념왕갈비 48,000원 / 한우육회 38,000원'),row('이어 보인 식사','장기름육회 비빔밥 15,000원 / 숙성김치찌개 8,000원')]),
    panel([row('대표 후보 ①','소 양념왕갈비 (280g) · 48,000원','구이 대표성은 사장님 확인','pending'),row('대표 후보 ②','장기름육회 비빔밥 · 15,000원','식사 대표성은 사장님 확인','pending'),row('다른 메뉴','모두 유지','추천 지정은 전체 메뉴 삭제·노출 순서 보장이 아니다.')]),
    '사장님이 고른 항목의 추천 표시만 검토','기존 메뉴·가격·주문 단위·정상 사진 전부',
    '실제 대표성·판매 가능 시간·현 계정의 추천 기능',
    '공개 메뉴의 첫 순서나 가장 낮은 가격만으로 대표 메뉴를 정하면 가게의 실제 선택지가 왜곡된다.',
    ['yuk-kakao-menu.jpg','yuk-kakao-home.jpg'],
    ['동일 화면에서 고가 구이와 상대적으로 낮은 식사 항목을 함께 확인했다.','추천 두 항목은 확정된 판매 순위가 아니라 승인 전 선택 후보이다.'])

add('07','jung','소개·브랜드','유지','이미 정한 브랜드 문구는 그대로 둔다',
    '정보형 소개로 통째 바꾸지 않는다. 필요한 사실은 메뉴·시간 칸에서 보완한다.',
    '카카오 · 현재 등록 소개','소개 변경 0칸',
    panel(text="‘정각’ 正刻 (바를정, 새길각)\n숙성돼지고기 X 우리 술 의 만남",note='공개 매장정보 영역에서 관측한 문구. 작성자 본인의 확인을 받은 것은 아니다.'),
    panel(text="‘정각’ 正刻 (바를정, 새길각)\n숙성돼지고기 X 우리 술 의 만남",note='브랜드 표현·한자·말투 보존. 2문장 규칙을 기존 문구에 소급하지 않는다.'),
    '소개는 수정하지 않음','기존 표현·브랜드 의도·사장님 추천 메뉴',
    '사장님이 문구 변경·번역을 원하는 경우에만 선택안',
    '좋은 정비에는 바꾸지 않는 결정도 포함된다. 감성적인 문구는 사실 오류와 다르다.',
    ['jung-kakao-brand.jpg','jung-google-home.jpg'],
    ['카카오의 매장정보 아래에 해당 브랜드 문구가 노출돼 있었다.','상호·층·예약 연결 정보를 통해 Google의 정각 망원본점과 대응을 확인했다.'])

add('08','jung','소개·브랜드','확인대기','비슷한 태그가 많아도 마음대로 지우지 않는다',
    '현재 공개 태그와 관리자가 입력하는 태그를 구분한 뒤, 의미가 겹치지 않는 선택안을 제시한다.',
    '카카오 · 관리 가능한 태그','선택 정리안 / 확정 전 0칸',
    panel(tags=['데이트','망원동데이트','망원맛집','모임','회식','데이트코스','드라이에이징'],note='공개 화면에서 관측한 태그. 입력 주체·관리 화면의 수정 가능 범위는 미확인.'),
    panel(tags=['숙성돼지고기','우리술','모임'],note='현재 등록 문구에서 뽑은 선택안. 사장님 선택과 관리 가능 범위를 확인한 뒤만 반영.'),
    '사장님이 관리하는 태그에 한해 중복 표현 정리 제안','브랜드 소개·기존 정상 정보·플랫폼 자동 표시',
    '공개 태그의 작성 주체·현 계정의 태그 입력 한도·사업자 선호',
    '공개 화면에 7개가 보인다는 사실과 관리 화면의 입력 규칙은 다를 수 있다. 전체 7개를 직접 수정 가능하다고 가정하지 않는다.',
    ['jung-kakao-brand.jpg'],
    ['공개 태그에 데이트·망원동데이트·데이트코스 등 유사 표현이 함께 표시됐다.','3개 태그는 최적 노출 공식이 아니라 선택적 편집안이다.'])

add('09','oreno','리뷰·판단','유지','친절한 외국인 응대 리뷰가 영어 응대 보장은 아니다',
    '한 고객의 경험과 매장이 지속적으로 제공하는 서비스를 구분한다.',
    '리뷰 → 편의·언어 속성 판단','자동 변경 0칸',
    panel([row('관측한 리뷰','외국인 손님에게 친절하게 응대한 경험','카카오 2025.02.09 후기의 취지 요약'),row('Google 편의 정보','영어 응대 가능 여부는 이번 화면에서 확인 못 함')]),
    panel([row('리뷰·평점','그대로 유지'),row('영어 응대 가능','추가하지 않음','직원·지원 시간 확인 전','unchanged'),row('영문 메뉴','필요한 메뉴만 별도 번역 검토','응대 언어와 별개')]),
    '리뷰를 바탕으로 확인 질문만 생성','리뷰 원문·별점·기존 서비스 값',
    '지원 언어·직원·가능 시간과 영어 메뉴 필요 여부',
    '과거의 친절한 경험 하나로 상시 영어 서비스나 모든 외국 카드 결제를 보장하지 않는다.',
    ['oreno-kakao-home.jpg','oreno-google-info.jpg'],
    ['카카오 공개 후기에서 외국인 응대 경험을 확인했다.','Google 정보에는 카드·NFC 등이 보였지만 영어 응대라는 확인 값은 관측하지 못했다.'])

add('10','oreno','이용조건','확인대기','AI가 요약한 무료 주차는 업주 확인값과 다르다',
    'AI 요약을 지우거나 편의 항목에 복제하지 않는다. 실제 주차 조건부터 확인한다.',
    '카카오 요약 / Google 주차 정보','사실 확인 전 변경 0칸',
    panel([row('카카오 공개 안내','무료 주차','‘kanana 활용’ 표시'),row('Google 정보','일반 주차 조건은 이번 화면에서 확인 못 함')]),
    panel([row('플랫폼 요약','현재 표시 유지','이 영역을 업주 편집 칸으로 취급하지 않음'),row('공식 주차 조건','사장님 확인 대기','전용/제휴/인근·요금·시간·차량 조건','pending')],note='휠체어 이용 가능 주차장과 일반 주차 가능 여부도 같은 항목이 아니다.'),
    '확인 후 실제 지원되는 주차 속성만 정비','AI 요약·리뷰·확인된 기존 속성',
    '무료 여부·주차장 종류·이용 시간·지원 속성',
    '플랫폼 요약의 출처 표시와 관리자가 직접 확인한 시설 정보를 분리해야 잘못된 무료 주차 안내를 줄일 수 있다.',
    ['oreno-kakao-home.jpg','oreno-google-info.jpg'],
    ['카카오 매장정보의 무료 주차 문구에 kanana 활용 표시가 있었다.','일반 주차 조건을 업주에게 독립 확인하지 않았다.'])

add('11','oreno','기본정보','확인대기','050 번호와 일반 번호가 다르면 무조건 오류일까',
    '연결번호와 대표번호일 수 있다. 동작을 확인하지 않고 어느 하나로 통일하지 않는다.',
    'Google·카카오 · 전화번호 비교','확인 전 변경 0칸',
    panel([row('Google','050-71318-9976'),row('카카오','02-499-0323')]),
    panel([row('Google','050-71318-9976','기존 값 유지'),row('카카오','02-499-0323','기존 값 유지'),row('확인할 점','동일 지점으로 연결되는 번호인가','사장님 확인 대기','pending')]),
    '전화번호 차이를 확인 항목으로만 분류','확인 전 두 지도 번호 모두',
    '안심·연결 번호인지, 실제 지점 번호인지, 현재 수신 여부',
    '숫자가 다르다는 것만으로는 오류가 확정되지 않는다. 플랜트의 지점 번호 정정 사례와 다른 판단이다.',
    ['oreno-google-home.jpg','oreno-kakao-home.jpg'],
    ['주소는 성수일로 47 102호로 대응하고 공개 전화번호는 달랐다.','이번 조사에서 전화를 걸거나 연결 상태를 확인하지 않았다.'])

add('12','pizza','이용조건','표현정리','런치 가격은 주문 시간과 한 묶음으로',
    '긴 문장의 뒤에 있는 평일·14시 제한을 메뉴 설명 맨 앞으로 옮긴다.',
    '카카오 · 런치스페셜 설명','설명 1칸 / 가격 유지',
    panel([row('런치스페셜','14,900원'),row('현재 설명','파스타 3종 중 택1 + 탄산 택1. 평일 오후 2시까지 주문 가능.')]),
    panel([row('런치스페셜','14,900원','가격 유지'),row('정리한 설명','평일 14:00까지 주문 가능. 파스타 3종 중 1개 + 탄산 1개.','Weekdays, order by 2 pm. Pasta + one soft drink.','changed')]),
    '메뉴 설명의 조건 순서·영어 표현만 정리','메뉴명·14,900원·파스타 선택·음료 포함',
    '현재 런치 운영과 번역 문구 최종 승인',
    '가격만 먼저 읽으면 상시 주문 가능한 메뉴처럼 오해할 수 있다. 이용 제한을 메뉴 옆에서 먼저 읽게 한다.',
    ['pizza-kakao-menu.jpg'],
    ['카카오 메뉴에 평일 오후 2시까지 주문 조건이 실제 들어 있다.','새 제한을 만든 것이 아니라 기존 조건을 앞으로 옮긴 제안이다.'])

add('13','pizza','메뉴·가격','표현정리','2인 세트 가격을 1인 가격으로 바꾸지 않는다',
    '기존 세트명을 유지하고 인원·구성을 영어로 간단히 이해하게 한다.',
    '카카오 · 2인 세트 설명','설명 1칸 / 가격 유지',
    panel([row('결정장애세트(2인)','39,900원'),row('구성','반반피자(페퍼로니+고르곤졸라) + 명동 파스타 + 탄산 2개')]),
    panel([row('결정장애세트(2인)','39,900원 / 세트','Set for two','changed'),row('구성 안내','반반피자 + 명동 파스타 + 탄산 2개','Half-and-half pizza, Myeongdong pasta and two soft drinks.','changed')],note='19,950원/인처럼 계산한 금액을 판매 가격 칸에 넣지 않는다.'),
    '기존 메뉴 설명 1칸에서 인원·구성 번역','세트명·39,900원·피자 맛 선택·구성',
    '추가 선택·변경 옵션이 있다면 가격과 함께 확인',
    '판매 단위는 세트다. 사람이 나눠 계산한 금액과 실제 주문 금액을 구분한다.',
    ['pizza-kakao-menu.jpg'],
    ['카카오 전체 메뉴에서 2인 세트와 39,900원, 구성을 확인했다.','3인·4인 세트 등 나머지 정상 메뉴는 유지한다.'])

add('14','pizza','리뷰·판단','확인대기','맵기 리뷰와 업체 답변이 다를 때',
    '소비자의 인지 문제인지 실제 표시 누락인지 먼저 확인한다. 리뷰 한쪽을 정답으로 택하지 않는다.',
    '카카오 · 게딱지 밥 설명 후보','설명 1칸 후보 / 확정 전 0칸',
    panel([row('현재 카카오 메뉴','게딱지 밥 · 16,500원','이번 메뉴 화면에는 별도 맵기 설명이 보이지 않았다.'),row('Google 리뷰와 답변','맵기를 몰랐다는 후기 / 이미 표시돼 있다는 업체 답변','서로 다른 주장으로 기록')]),
    panel([row('메뉴명·가격','게딱지 밥 · 16,500원','그대로 유지'),row('설명 보완','실제 맵기·주재료 확인 후 명시','확인되지 않은 단계·재료는 입력하지 않음','pending')],note='아이에게 안전·순한맛·게 내장 포함 같은 새로운 주장은 만들지 않는다.'),
    '현재 메뉴 표시를 확인한 후 필요한 설명만 보완','기존 리뷰·업체 답변·평점·확인된 가격',
    '메뉴판의 현행 맵기 표시, 조리 내용, 사용자가 보는 칸',
    '리뷰는 개선할 질문의 근거다. 표현을 명확히 할 수 있지만 맛에 대한 평가를 바꾸거나 불만을 삭제할 수는 없다.',
    ['pizza-google-review-detail.jpg','pizza-kakao-menu.jpg'],
    ['Google에 맵기 인지에 관한 후기와 업체 대표의 다른 설명이 같이 있었다.','카카오 메뉴에서는 게딱지 밥 16,500원 이름·가격을 확인했다.'])

add('15','plant','메뉴·가격','확인대기','배달 메뉴 링크와 매장 직접 메뉴를 구분한다',
    '직접 메뉴에 사이드 하나만 보인다고 식사 메뉴가 없다고 결론내리지 않는다.',
    '카카오 · 매장용 메뉴 보완','식사 메뉴 후보 3개',
    panel([row('직접 메뉴에서 관측','Sour cream / 사워 크림 · 3,000원'),row('별도 경로','배달 메뉴 보기 링크도 있음')],image='plant-kakao-menu.jpg',note='사워크림은 현재 등록된 항목으로 유지한다.'),
    panel([row('식사 후보 ①','HUMMUS TEMPEH BOWL · 후무스 템페 보울','공식 사진 표기 15.0 / 금액 단위·최신성 확인','pending'),row('식사 후보 ②','TOFU CAESAR WRAP · 두부 시저 랩','공식 사진 표기 15.0 / 금액 단위·최신성 확인','pending'),row('식사 후보 ③','LENTIL VEGGIE BOWL · 렌틸 베지 보울','중복·매장 판매 조건 확인','pending')],note='15.0 표기를 추측해서 원화 가격으로 확정하지 않는다. 확인한 항목만 추가한다.'),
    '외부 메뉴와 매장 직접 메뉴를 대조한 뒤 누락분만 보완','사워크림 3,000원·배달 링크·기존 정상 항목',
    '매장/배달 판매 조건·가격 단위·원본 사용·현재 판매·중복',
    '이 페이지의 단일 저가 사이드가 식당 전체의 식사 메뉴·예산을 대표하지 않는다.',
    ['plant-kakao-menu.jpg','plant-official-menu.jpg'],
    ['카카오 직접 메뉴 탭에는 사워크림 3,000원이 보였고 별도 배달 메뉴 링크가 있었다.','공식 연남 메뉴 이미지에서 식사 메뉴 세 가지를 확인했다. 가격 적용 여부는 미확인이다.'],
    ['google','kakao','official-menu'])

add('16','plant','리뷰·판단','유지','비건 정보는 유지하고 보장을 확대하지 않는다',
    '이미 있는 비건·채식 속성을 다시 채우지 않는다. 알레르기·할랄은 별도 사실이다.',
    'Google · 식단 관련 속성','속성 변경 0칸',
    panel([row('Google 현재 속성','비건 메뉴 · 채식 메뉴'),row('공식 안내','100% vegan'),row('공식 메뉴판','메뉴마다 GF·NF·SF 등의 개별 표기')]),
    panel([row('비건·채식 속성','유지','이미 확인된 정보'),row('알레르기·할랄 보장','추가하지 않음','인증·조리·교차 접촉 등 별도 확인이 필요')],note='일부 메뉴의 식단 표시를 모든 메뉴와 주방 전체의 보장으로 확대하지 않는다.'),
    '새 식단 속성을 추가하지 않음','기존 비건·채식 속성·공식 링크·현재 메뉴',
    '고객의 구체적 식단 문의가 있으면 매장에 별도 확인',
    '맞는 정보를 유지하는 것이 정비다. 문구를 더 많이 붙이는 것이 항상 더 정확한 정보는 아니다.',
    ['plant-google-info.jpg','plant-official-menu.jpg'],
    ['Google 정보에서 비건 메뉴·채식 메뉴 속성을 확인했다.','공식 메뉴판에는 전체 비건 안내와 메뉴별 식단 표시가 병존한다.'],
    ['google','kakao','official-menu'])

add('17','plant','이용조건','정정안','예약 링크는 유지하면서 예외 조건만 보완한다',
    '예약 버튼이 있다고 모든 요일에 예약 가능한 것은 아니다. 공식 지점의 제한을 짧게 안내한다.',
    'Google · 소개 또는 지원되는 예약 안내','조건 안내 1문장 후보',
    panel([row('Google 개요','예약하기 링크 제공'),row('공식 연남 안내','주말·공휴일 예약을 받지 않음')]),
    panel([row('예약 링크','현재 링크 유지'),row('안내 문장 후보','주말·공휴일에는 예약을 받지 않습니다.','No reservations on weekends or national holidays.','changed')],note='예약 조건 전용 칸이 없다면 기존 소개를 보존한 채 필요한 1문장만 제안한다. 새 칸이 있다고 가정하지 않는다.'),
    '해당 지점 예약 조건 1문장만 보완','예약 버튼·가게 소개의 기존 표현·영업시간',
    '현재 예약 정책·지원 입력 칸·기존 소개와의 배치',
    '예약 가능 자체를 끄기보다 예외 조건을 알려야 평일 예약 기능을 잃지 않는다.',
    ['plant-google-home.jpg','plant-official-branch.jpg'],
    ['Google 개요에 예약 링크가 있었다.','공식 연남 지점 안내에 주말·공휴일 예약 불가 조건이 명시돼 있다.'],
    ['google','kakao','official'])

add('18','hiss','리뷰·판단','유지','사진의 SOLD OUT은 판매 종료 증거가 아니다',
    '특정 촬영 시점의 품절 표시를 근거로 현재 메뉴를 삭제하지 않는다.',
    '메뉴판 사진 → 판매 상태 판단','삭제·변경 0칸',
    panel(image='hiss-kakao-menuboard.jpg',text='메뉴판 사진에 SOLD OUT 표시가 보임',note='사진 촬영 시점과 현재 재고·판매 정책은 미확인.'),
    panel([row('기존 메뉴 목록','유지'),row('사진 원본','유지'),row('현재 판매 상태','사장님 확인 전 판단 보류','일시 품절·계절 판매·영구 종료를 구분')]),
    '현재 메뉴를 지우지 않음','기존 항목·사진·가격 정보',
    '현재 판매 여부와 플랫폼의 품절/판매 종료 표시 지원',
    '일시적 상황을 영구 사실로 바꾸면 판매 가능한 메뉴를 오히려 숨길 수 있다.',
    ['hiss-kakao-menuboard.jpg'],
    ['열람한 메뉴판 사진에 품절 배지가 있었다.','현재 품절·영구 종료·사진의 최신성은 확인하지 않았다.'])

payload = dict(stores=stores, cases=cases, observedDate='2026-10-28', mapCount=12,
    note='공개 화면을 읽어 만든 정비 시안. 실제 지도는 수정하지 않았으며 업주 승인·관리 화면 지원 확인 전이다.')
(ROOT / 'evidence/cases.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

CSS = r'''
:root{--ink:#172d2b;--muted:#677774;--paper:#f5f6f2;--line:#dce2dc;--green:#16745e;--green-soft:#e8f3ec;--amber:#9a641d;--amber-soft:#fff3dd;--blue:#3e648c;--white:#fff;--serif:Georgia,'Batang',serif}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:92px}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 'Pretendard','Segoe UI','Malgun Gothic',sans-serif;-webkit-font-smoothing:antialiased}button,input,select{font:inherit}button,a,select,input{touch-action:manipulation}button{cursor:pointer}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #81b7aa;outline-offset:4px}a{color:inherit;text-underline-offset:3px}button{color:inherit}button:disabled{cursor:default}.skip{position:fixed;top:-80px;left:20px;z-index:20;background:white;padding:12px}.skip:focus{top:10px}
.topbar{height:76px;position:sticky;top:0;z-index:12;background:rgba(245,246,242,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(15px)}.top-inner{max-width:1360px;height:100%;margin:auto;padding:0 34px;display:flex;align-items:center;gap:30px}.brand{font-size:30px;font-weight:800;letter-spacing:-1.8px;text-decoration:none}.brand:after{content:'';display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-left:4px}.top-label{font-size:12px;color:var(--muted);border-left:1px solid var(--line);padding-left:23px;line-height:1.5}.top-right{margin-left:auto;display:flex;gap:16px;align-items:center}.date{font-size:12px;color:var(--muted)}.print-btn{border:1px solid var(--line);background:transparent;border-radius:7px;padding:8px 13px;font-size:12px}.print-btn:hover{background:white}
.page{max-width:1360px;padding:0 34px;margin:auto}.hero{padding:58px 0 40px;display:grid;grid-template-columns:1.4fr 1fr;gap:60px;border-bottom:1px solid var(--line)}.eyebrow{font-size:11px;letter-spacing:2px;font-weight:700;color:var(--green);text-transform:uppercase;margin:0 0 16px}.hero h1{font-size:clamp(32px,4.3vw,57px);line-height:1.2;letter-spacing:-2.4px;margin:0 0 20px;font-weight:650;word-break:keep-all}.hero h1 span{color:var(--green)}.hero-copy{max-width:600px;color:var(--muted);font-size:14px;margin:0;word-break:keep-all}.hero-aside{align-self:end}.statusline{display:flex;align-items:center;gap:8px;font-size:12px;margin:0 0 20px}.statusdot{height:7px;width:7px;border-radius:50%;background:var(--green)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.stat strong{display:block;font-size:34px;line-height:1.3;font-weight:550;letter-spacing:-1.5px}.stat small{font-size:11px;color:var(--muted)}.scope-note{font-size:11px;color:var(--muted);margin:18px 0 0}
.store-strip{display:flex;gap:8px;padding:24px 0 25px;flex-wrap:wrap}.store-chip{display:flex;align-items:center;gap:8px;border:1px solid var(--line);background:transparent;border-radius:99px;padding:7px 12px;font-size:12px}.store-chip span{font-size:10px;color:var(--muted)}.store-chip.active{background:var(--ink);border-color:var(--ink);color:white}.store-chip.active span{color:#bfd1ca}
.workspace{display:grid;grid-template-columns:208px minmax(0,1fr);gap:36px;align-items:start}.sidebar{position:sticky;top:99px;padding:18px 0 30px}.side-title{font-size:10px;font-weight:700;letter-spacing:1.4px;color:var(--muted);margin:0 0 13px}.side-item{display:flex;align-items:center;gap:8px;border:0;background:transparent;width:100%;text-align:left;padding:10px 12px;margin-bottom:4px;border-radius:7px;font-size:13px}.side-item b{margin-left:auto;font-size:10px;font-weight:400;color:var(--muted)}.side-item.active{background:#e4ebe3;color:var(--green);font-weight:700}.side-item:hover{background:#e9ede6}.side-note{border-top:1px solid var(--line);margin-top:26px;padding-top:20px;font-size:12px;color:var(--muted)}.side-note strong{display:block;color:var(--ink);font-size:12px;margin-bottom:7px}.legend{display:flex;flex-direction:column;gap:8px;margin-top:16px}.legend div{display:flex;align-items:center;gap:8px;font-size:11px}.dot{width:7px;height:7px;border-radius:50%;background:var(--green)}.dot.pending{background:#bb863a}.dot.keep{background:#8a9790}.dot.edit{background:var(--blue)}
.main{min-width:0}.toolbar{display:flex;align-items:center;gap:10px;padding:17px 0 22px;flex-wrap:wrap}.search{position:relative;flex:1;min-width:180px}.search svg{position:absolute;left:12px;top:13px;width:16px;height:16px;stroke:#788982;fill:none;stroke-width:1.6}.search input{width:100%;background:white;border:1px solid var(--line);padding:10px 12px 10px 36px;border-radius:7px;font-size:12px}.toolbar select{border:1px solid var(--line);padding:10px 28px 10px 12px;background:white;border-radius:7px;font-size:12px;max-width:100%}.highlight-control{display:flex;gap:6px;align-items:center;font-size:11px;white-space:nowrap}.highlight-control input{accent-color:var(--green)}.results-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.results-heading h2{font-size:14px;margin:0;font-weight:650}.results-heading span{font-size:11px;color:var(--muted)}.empty{padding:60px 15px;text-align:center;color:var(--muted);border:1px dashed var(--line)}
.case{background:white;border:1px solid var(--line);border-radius:12px;margin-bottom:25px;overflow:hidden;scroll-margin-top:96px}.case-header{padding:23px 25px 18px}.case-meta{display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-bottom:10px}.case-number{color:var(--green);font-size:12px;font-weight:750;letter-spacing:1px}.case-sep{width:1px;height:10px;background:var(--line)}.badge{padding:3px 8px;border-radius:4px;font-size:10px;font-weight:650;background:var(--green-soft);color:var(--green)}.badge.pending{background:var(--amber-soft);color:var(--amber)}.badge.keep{background:#eef0ed;color:#627268}.badge.edit{background:#edf2f8;color:var(--blue)}.case-header h3{font-size:21px;line-height:1.4;letter-spacing:-.65px;margin:0 0 9px;word-break:keep-all}.case-lead{font-size:12px;color:var(--muted);margin:0;max-width:760px;word-break:keep-all}.mapping{margin-top:16px;display:flex;align-items:center;gap:8px;justify-content:space-between;font-size:11px;flex-wrap:wrap}.mapping .target{color:var(--muted)}.mapping .quantity{font-weight:650;color:var(--ink);background:#f1f4ef;padding:4px 9px;border-radius:4px}.compare{display:grid;grid-template-columns:1fr 1fr;margin:0 24px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.panel{min-width:0;padding:17px 20px 21px 0}.panel.after{border-left:1px solid var(--line);padding:17px 0 21px 22px}.panel-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:15px}.panel-title strong{font-size:10px;letter-spacing:1.6px}.panel-title span{font-size:10px;color:var(--muted)}.panel.after .panel-title strong{color:var(--green)}.pending-case .panel.after .panel-title strong{color:var(--amber)}.keep-case .panel.after .panel-title strong{color:#68796c}.panel-content{background:#f6f7f4;border:1px solid #e8ece6;padding:16px;border-radius:7px;min-height:152px}.after .panel-content{background:#f1f7f1;border-color:#dceadd}.pending-case .after .panel-content{background:#fffbf2;border:1px dashed #e2c99c}.keep-case .after .panel-content{background:#f4f6f2;border-color:#e2e7dd}.field+.field{border-top:1px solid rgba(21,61,42,.08);margin-top:12px;padding-top:12px}.field-label{font-size:10px;color:var(--muted);display:block;margin-bottom:4px}.field-value{font-size:13px;line-height:1.7;font-weight:550;white-space:pre-line;overflow-wrap:anywhere}.field-note{font-size:10px;line-height:1.6;color:var(--muted);margin:5px 0 0;overflow-wrap:anywhere}.emphasis .after .changed .field-value{background:#dceede;padding:2px 4px;margin-left:-4px;box-decoration-break:clone;-webkit-box-decoration-break:clone}.emphasis .after .pending .field-value{background:#fff0cf;padding:2px 4px;margin-left:-4px;box-decoration-break:clone;-webkit-box-decoration-break:clone}.panel-text{font-size:14px;line-height:1.85;white-space:pre-line;word-break:keep-all;margin:0;font-weight:500}.panel-note{font-size:10px;color:var(--muted);line-height:1.75;margin:11px 0 0;word-break:keep-all}.tags{display:flex;gap:6px;flex-wrap:wrap}.tag{border:1px solid #dce3da;background:white;padding:4px 8px;border-radius:5px;font-size:11px}.after .tag{background:#e7f0e3;border-color:#cdddc7}.source-thumb{width:100%;padding:0;border:0;background:#e8ece5;display:block;border-radius:5px;overflow:hidden;margin:12px 0 0;position:relative}.source-thumb img{display:block;width:100%;height:165px;object-fit:cover;object-position:center}.source-thumb .zoom{position:absolute;bottom:7px;right:7px;background:rgba(16,37,28,.82);color:white;padding:3px 7px;border-radius:3px;font-size:9px}.source-thumb:only-child{margin-top:0}.before .source-thumb img{object-fit:contain;background:#e2e5de}
.decision{padding:20px 25px;display:grid;grid-template-columns:1fr 1fr;gap:11px 25px}.decision div{font-size:11px;line-height:1.7;color:#60716a;word-break:keep-all}.decision b{display:block;font-size:10px;font-weight:650;color:var(--ink);margin-bottom:3px}.decision .check b{color:var(--amber)}.decision .why{grid-column:1/-1;border-left:2px solid #d7e1d2;padding-left:12px;font-size:12px;color:#385447}.evidence{border-top:1px solid var(--line);background:#fbfcf9;padding:0 25px}.evidence>summary{padding:13px 0;cursor:pointer;font-size:11px;font-weight:550;list-style:none;display:flex;justify-content:space-between;align-items:center}.evidence>summary::-webkit-details-marker{display:none}.evidence>summary:after{content:'+';font-size:18px;color:var(--muted);font-weight:400}.evidence[open]>summary:after{content:'−'}.evidence-body{padding:3px 0 19px}.facts{padding:0 0 0 15px;color:var(--muted);font-size:11px;line-height:1.85;margin:0 0 12px}.source-links{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}.source-link{display:inline-flex;align-items:center;gap:5px;text-decoration:none;background:white;border:1px solid var(--line);border-radius:5px;padding:5px 8px;font-size:10px}.source-link:hover{border-color:#93b09e}.source-link .g{color:#4276bc;font-weight:750}.source-link .k{background:#f6dc55;color:#3a3323;font-weight:750;width:13px;height:13px;display:inline-flex;justify-content:center;align-items:center;border-radius:2px;font-size:9px}.evidence-pics{display:flex;gap:8px;overflow-x:auto;margin-top:12px;padding-bottom:4px}.evidence-pics .source-thumb{width:145px;min-width:145px;margin:0}.evidence-pics .source-thumb img{height:92px;object-fit:cover}.evidence-pics figcaption{font-size:9px;color:var(--muted);margin-top:3px}.evidence-pics figure{margin:0;width:145px;min-width:145px}.case-foot{display:flex;gap:8px;padding:10px 25px;border-top:1px solid #e7ece4;background:#fafbf8;font-size:9px;color:#738176;align-items:center}.case-foot .mini{height:5px;width:5px;border-radius:50%;background:#8ba38f}.method{border-top:1px solid var(--line);padding:28px 0 35px;margin:8px 0 0}.method h2{font-size:15px;margin:0 0 13px}.method-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}.method-grid h3{font-size:11px;margin:0 0 7px}.method-grid p{margin:0;color:var(--muted);font-size:11px;line-height:1.85;word-break:keep-all}.store-table{width:100%;border-collapse:collapse;margin:24px 0;font-size:11px}.store-table th,.store-table td{text-align:left;border-bottom:1px solid var(--line);padding:10px 8px;vertical-align:top}.store-table th{font-weight:550;color:var(--muted)}.store-table td a{margin-right:8px;white-space:nowrap}.bottom{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:18px 0 35px;font-size:10px;color:var(--muted);gap:15px}.back-top{position:fixed;bottom:22px;right:23px;z-index:10;background:var(--ink);color:white;width:36px;height:36px;display:flex;align-items:center;justify-content:center;text-decoration:none;border-radius:50%;box-shadow:0 3px 15px #0b2b2520}.source-dialog{border:0;background:#f7f8f4;padding:0;border-radius:10px;width:min(1250px,95vw);max-height:94vh;box-shadow:0 10px 100px #09221960}.source-dialog::backdrop{background:#122820b8;backdrop-filter:blur(5px)}.dialog-head{display:flex;justify-content:space-between;align-items:center;padding:13px 18px;background:white;border-bottom:1px solid var(--line);font-size:12px}.dialog-head button{border:1px solid var(--line);background:white;border-radius:5px;padding:4px 10px;font-size:11px}.dialog-body{padding:12px;overflow:auto;max-height:calc(94vh - 58px)}.dialog-body img{width:100%;height:auto;display:block}.no-js{padding:50px;border:1px solid var(--line);background:white}
@media(min-width:1200px){.hero{gap:90px}.case-header h3{font-size:22px}}
@media(max-width:1000px){.workspace{grid-template-columns:165px minmax(0,1fr);gap:22px}.hero{gap:30px}.hero h1{font-size:41px}.page,.top-inner{padding-left:23px;padding-right:23px}.compare{margin:0 18px}.panel{padding-right:15px}.panel.after{padding-left:15px}.case-header,.decision{padding-left:19px;padding-right:19px}.field-value{font-size:12px}}
@media(max-width:760px){.topbar{height:64px}.top-inner{padding:0 18px;gap:14px}.brand{font-size:26px}.top-label{padding-left:14px;font-size:10px}.date{display:none}.top-right{gap:0}.print-btn{font-size:10px;padding:6px 9px}.page{padding:0 17px}.hero{grid-template-columns:1fr;padding:35px 0 25px;gap:27px}.hero h1{font-size:36px;letter-spacing:-1.7px}.hero-copy{font-size:12px}.hero-aside{width:100%}.stats{gap:10px}.stat strong{font-size:28px}.stat small{font-size:10px}.statusline{margin-bottom:13px;font-size:11px}.scope-note{font-size:10px}.store-strip{gap:6px;padding:19px 0}.store-chip{font-size:10px;padding:6px 9px}.store-chip span{font-size:9px}.workspace{display:block}.sidebar{position:static;padding:0 0 5px}.side-title,.side-note{display:none}.side-nav{display:flex;gap:4px;overflow-x:auto;padding:3px 0 8px}.side-item{width:auto;min-width:max-content;font-size:11px;padding:8px 10px;margin:0;border:1px solid var(--line);border-radius:6px}.side-item b{margin-left:6px}.toolbar{padding:10px 0 15px;gap:8px}.search{flex-basis:100%;min-width:0}.toolbar select{flex:1}.highlight-control{font-size:10px}.results-heading{margin-bottom:11px}.results-heading span{font-size:9px}.case{border-radius:9px;margin-bottom:20px}.case-header{padding:18px 16px 15px}.case-header h3{font-size:19px;line-height:1.45;letter-spacing:-.6px}.case-meta{gap:7px;font-size:10px}.case-lead{font-size:11px}.mapping{margin-top:12px;font-size:10px}.compare{grid-template-columns:1fr;margin:0 15px}.panel{padding:15px 0}.panel.after{border-left:0;border-top:1px solid var(--line);padding:15px 0}.panel-content{min-height:0;padding:14px}.panel-title{margin-bottom:10px}.field-value{font-size:13px}.decision{padding:16px;gap:13px;grid-template-columns:1fr}.decision .why{grid-column:auto;font-size:11px}.evidence{padding:0 16px}.case-foot{padding:10px 16px;line-height:1.6}.method-grid{grid-template-columns:1fr;gap:20px}.store-table{font-size:10px}.store-table th:nth-child(2),.store-table td:nth-child(2){display:none}.store-table th,.store-table td{padding:9px 4px}.bottom{display:block;line-height:1.9}.bottom span{display:block}.back-top{right:15px;bottom:15px;width:32px;height:32px}.source-dialog{max-height:96vh}.dialog-head{padding:10px 12px;font-size:10px}.dialog-body{padding:3px}}
@media print{html{scroll-behavior:auto}body{background:white;font-size:10pt}.topbar{position:static;background:white}.top-right,.sidebar,.toolbar,.store-strip,.back-top,.source-dialog{display:none!important}.page{max-width:none;padding:0}.hero{padding:20px 0;gap:30px}.hero h1{font-size:30px}.workspace{display:block}.case{break-inside:avoid;page-break-inside:avoid;border-radius:0;margin-bottom:20px}.case-header h3{font-size:16px}.compare{grid-template-columns:1fr 1fr}.panel.after{border-top:0;border-left:1px solid var(--line);padding-left:15px}.panel{padding-right:15px}.evidence>summary{display:none}.evidence-body{display:block}.evidence:not([open]) .evidence-body{display:block}.evidence-pics{display:none}.source-link{font-size:8px;border:0;padding:0 4px}.source-links{margin:0;padding:8px 0}.facts{font-size:8px}.source-thumb{max-height:150px}.decision{grid-template-columns:1fr 1fr}.method{break-before:page}.method-grid{grid-template-columns:1fr 1fr 1fr}.case[hidden]{display:none!important}.print-warning{display:block!important;font-size:9px;color:#777}.top-label{font-size:9px}a{text-decoration:none}.store-table{font-size:9px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
'''

JS = r'''
const DATA = JSON.parse(document.getElementById('case-data').textContent);
const stores = Object.fromEntries(DATA.stores.map(s=>[s.id,s]));
const categories=['전체','기본정보','메뉴·가격','소개·브랜드','이용조건','리뷰·판단'];
const state={store:'all',category:'전체',status:'all',query:''};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusClass=s=>s==='확인대기'?'pending':s==='유지'?'keep':s==='표현정리'?'edit':'';
function sourceLinks(c){const s=stores[c.store];return `<div class="source-links">${c.sources.map(key=>{const href=s.sources[key];if(!href)return '';const label=key==='google'?'Google 지도':key==='kakao'?'카카오맵':key==='official-menu'?'공식 메뉴':'공식 지점';return `<a class="source-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer"><span class="${key==='google'?'g':key==='kakao'?'k':''}">${key==='google'?'G':key==='kakao'?'K':'↗'}</span>${label}</a>`}).join('')}</div>`}
function photoButton(file,label){return `<button class="source-thumb" data-image="${esc(file)}" data-caption="${esc(label)}" aria-label="${esc(label)} 원본 화면 확대"><img src="images/${esc(file)}" alt="${esc(label)}" loading="lazy"><span class="zoom">원본 확대 ↗</span></button>`}
function renderPanel(p,side,c){const content=`${p.text?`<p class="panel-text">${esc(p.text)}</p>`:''}${p.tags?.length?`<div class="tags">${p.tags.map(t=>`<span class="tag">#${esc(t)}</span>`).join('')}</div>`:''}${p.rows.map(r=>`<div class="field ${esc(r.state)}"><span class="field-label">${esc(r.label)}</span><span class="field-value">${esc(r.value)}</span>${r.note?`<p class="field-note">${esc(r.note)}</p>`:''}</div>`).join('')}${p.image?photoButton(p.image,`${stores[c.store].name} · 현재 공개 화면`):''}`;return `<section class="panel ${side}" aria-label="${side==='after'?'정비 제안':'현재 공개 내용'}"><div class="panel-title"><strong>${side==='after'?'AFTER':'BEFORE'}</strong><span>${side==='after'?(c.status==='유지'?'현재 정보 유지':'승인 전 정비 시안'):'확인한 공개정보 재구성'}</span></div><div class="panel-content">${content}</div>${p.note?`<p class="panel-note">${esc(p.note)}</p>`:''}</section>`}
function card(c){const s=stores[c.store],sc=statusClass(c.status);return `<article class="case ${sc}-case" id="case-${c.id}" data-id="${c.id}"><header class="case-header"><div class="case-meta"><span class="case-number">CASE ${c.id}</span><span class="case-sep"></span><span>${esc(s.name)}</span><span class="badge ${sc}">${esc(c.status)}</span></div><h3>${esc(c.title)}</h3><p class="case-lead">${esc(c.lead)}</p><div class="mapping"><span class="target">${esc(c.target)}</span><span class="quantity">${esc(c.amount)}</span></div></header><div class="compare">${renderPanel(c.before,'before',c)}${renderPanel(c.after,'after',c)}</div><div class="decision"><div><b>바꾸는 부분</b>${esc(c.changes)}</div><div><b>유지하는 부분</b>${esc(c.keep)}</div><div class="check"><b>사장님·관리 화면에서 확인</b>${esc(c.check)}</div><div class="why">${esc(c.reason)}</div></div><details class="evidence"><summary>관측 근거 · 원본 화면 · 출처</summary><div class="evidence-body"><ul class="facts">${c.facts.map(f=>`<li>${esc(f)}</li>`).join('')}</ul>${sourceLinks(c)}<div class="evidence-pics">${c.evidence.map((img,i)=>`<figure>${photoButton(img,`${s.name} · 근거 화면 ${i+1}`)}<figcaption>${esc(img.replace('.jpg',''))}</figcaption></figure>`).join('')}</div></div></details><div class="case-foot"><span class="mini"></span>2026.10.28 공개 화면 관측 · 실제 지도 수정 없음 · 근거 화면은 당시의 표시 상태</div></article>`}
document.getElementById('cards').innerHTML=DATA.cases.map(card).join('');
document.getElementById('store-chips').innerHTML=`<button class="store-chip active" data-store="all">모든 가게 <span>6</span></button>`+DATA.stores.map(s=>`<button class="store-chip" data-store="${s.id}">${esc(s.name)} <span>${esc(s.area)}</span></button>`).join('');
document.getElementById('category-nav').innerHTML=categories.map(cat=>`<button class="side-item ${cat==='전체'?'active':''}" data-category="${esc(cat)}"><span>${esc(cat==='전체'?'모든 경우':cat)}</span><b>${cat==='전체'?DATA.cases.length:DATA.cases.filter(c=>c.category===cat).length}</b></button>`).join('');
document.getElementById('store-table-body').innerHTML=DATA.stores.map(s=>`<tr><td><strong>${esc(s.name)}</strong><br><span style="color:var(--muted)">${esc(s.area)} · ${esc(s.food)}</span></td><td>${esc(s.address)}</td><td><a href="${esc(s.sources.google)}" target="_blank" rel="noopener noreferrer">Google ↗</a><a href="${esc(s.sources.kakao)}" target="_blank" rel="noopener noreferrer">카카오 ↗</a>${s.sources.official?`<a href="${esc(s.sources.official)}" target="_blank" rel="noopener noreferrer">공식 ↗</a>`:''}</td></tr>`).join('');
function applyFilters(){let count=0;DATA.cases.forEach(c=>{const s=stores[c.store];const hay=[s.name,c.title,c.lead,c.target,c.changes,c.keep,...c.facts].join(' ').toLowerCase();const show=(state.store==='all'||state.store===c.store)&&(state.category==='전체'||state.category===c.category)&&(state.status==='all'||state.status===c.status)&&(!state.query||hay.includes(state.query));document.getElementById(`case-${c.id}`).hidden=!show;if(show)count++});document.getElementById('result-count').textContent=`${count}개 사례`;document.getElementById('empty').hidden=count!==0;document.querySelectorAll('[data-store]').forEach(el=>{el.classList.toggle('active',el.dataset.store===state.store);el.setAttribute('aria-pressed',String(el.dataset.store===state.store))});document.querySelectorAll('[data-category]').forEach(el=>{el.classList.toggle('active',el.dataset.category===state.category);el.setAttribute('aria-pressed',String(el.dataset.category===state.category))});document.getElementById('view-label').textContent=(state.store==='all'?'6개 가게':stores[state.store].name)+' · '+(state.category==='전체'?'모든 경우':state.category);}
document.getElementById('store-chips').addEventListener('click',e=>{const b=e.target.closest('[data-store]');if(!b)return;state.store=b.dataset.store;applyFilters()});
document.getElementById('category-nav').addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(!b)return;state.category=b.dataset.category;applyFilters()});
document.getElementById('search').addEventListener('input',e=>{state.query=e.target.value.trim().toLowerCase();applyFilters()});
document.getElementById('status-select').addEventListener('change',e=>{state.status=e.target.value;applyFilters()});
document.getElementById('emphasis-toggle').addEventListener('change',e=>document.body.classList.toggle('emphasis',e.target.checked));
document.getElementById('reset').addEventListener('click',()=>{state.store='all';state.category='전체';state.status='all';state.query='';document.getElementById('search').value='';document.getElementById('status-select').value='all';applyFilters()});
document.getElementById('print').addEventListener('click',()=>window.print());
const dialog=document.getElementById('image-dialog');let lastImageButton=null;
document.addEventListener('click',e=>{const b=e.target.closest('[data-image]');if(!b)return;lastImageButton=b;document.getElementById('dialog-image').src='images/'+b.dataset.image;document.getElementById('dialog-image').alt=b.dataset.caption;document.getElementById('dialog-caption').textContent=b.dataset.caption;dialog.showModal()});
document.getElementById('dialog-close').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});dialog.addEventListener('close',()=>lastImageButton?.focus());
applyFilters();
'''

HTML = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="description" content="실제 서울 가게 6곳의 Google·카카오 공개 화면을 바탕으로 만든 18가지 지도 정보 정비 비포·애프터 시안."><title>seelo · 지도 정보 정비 Before / After</title><style>__CSS__</style></head>
<body class="emphasis" id="top"><a class="skip" href="#main-content">사례로 바로 가기</a>
<header class="topbar"><div class="top-inner"><a class="brand" href="#top" aria-label="seelo 처음으로">seelo</a><div class="top-label">지도 정보 정비<br>BEFORE / AFTER STUDY</div><div class="top-right"><span class="date">2026.10.28 · 서울</span><button class="print-btn" id="print">인쇄 / PDF</button></div></div></header>
<div class="page"><section class="hero"><div><p class="eyebrow">REAL PLACES, PRECISE CHANGES</p><h1>어디를 고치고,<br><span>어디를 남길까.</span></h1><p class="hero-copy">실제 가게의 지도 페이지에서 출발해, 바꿀 칸과 남길 정보를 구분했습니다. 사진·리뷰·브랜드 문구를 모두 소개에 몰아넣지 않고 필요한 부분만 정비합니다.</p></div><div class="hero-aside"><p class="statusline"><span class="statusdot"></span>두 지도를 직접 확인한, 승인 전 정비 시안</p><div class="stats"><div class="stat"><strong>6</strong><small>실제 가게</small></div><div class="stat"><strong>12</strong><small>지도 페이지</small></div><div class="stat"><strong>18</strong><small>서로 다른 상황</small></div><div class="stat"><strong>0</strong><small>실제 지도 수정</small></div></div><p class="scope-note">현재 화면과 제안 화면을 재구성한 비교입니다.<br>확인대기 항목은 사실이 확정되기 전 반영하지 않습니다.</p></div></section>
<div class="store-strip" id="store-chips" aria-label="가게별 필터"></div>
<div class="workspace"><aside class="sidebar" aria-label="상황별 필터"><p class="side-title">EXPLORE BY SITUATION</p><nav class="side-nav" id="category-nav"></nav><div class="side-note"><strong>수정량을 채우지 않습니다.</strong>틀린 값만 정정하고 정상 정보는 보존합니다. 수정할 근거가 없으면 0건이 맞습니다.<div class="legend"><div><span class="dot"></span>정정안 · 근거를 대조한 보완</div><div><span class="dot edit"></span>표현정리 · 같은 사실을 명확하게</div><div><span class="dot pending"></span>확인대기 · 사실·지원 칸 확인</div><div><span class="dot keep"></span>유지 · 바꾸지 않는 판단</div></div></div></aside>
<main class="main" id="main-content"><div class="toolbar"><label class="search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg><input id="search" type="search" placeholder="가게·상황·수정 항목 검색" aria-label="사례 검색"></label><select id="status-select" aria-label="판단 상태별 필터"><option value="all">모든 판단</option>__STATUS_OPTIONS__</select><label class="highlight-control"><input type="checkbox" id="emphasis-toggle" checked>변경점 강조</label><button class="print-btn" id="reset">초기화</button></div><div class="results-heading"><h2 id="view-label">모든 사례</h2><span id="result-count" role="status" aria-live="polite">18개 사례</span></div><noscript><p class="no-js">이 HTML은 사례 비교를 표시하기 위해 JavaScript가 필요합니다.</p></noscript><div id="cards"></div><p class="empty" id="empty" hidden>조건에 맞는 사례가 없습니다. 필터를 초기화해 주세요.</p>
<section class="method" id="sources"><p class="eyebrow">SOURCE & SCOPE</p><h2>무엇을 확인했고, 무엇은 아직 모르는가</h2><div class="method-grid"><div><h3>공개 화면을 직접 확인</h3><p>2026년 10월 28일 Google·카카오에서 가게 6곳을 찾고, 지점명·주소/층·연결 정보를 대조했습니다. 메뉴 탭·사진 원문·리뷰·속성을 필요한 범위에서 확인했습니다.</p></div><div><h3>실제 변경은 하지 않음</h3><p>관리자 권한으로 들어가거나 수정 제안을 제출하지 않았습니다. AFTER는 공개 정보를 바탕으로 만든 제안이며, 업주 승인·현재 사실·실제 지원 칸을 확인한 뒤만 적용할 수 있습니다.</p></div><div><h3>이후 변화는 별도 검증</h3><p>리뷰·AI 요약을 확정 사실로 취급하지 않았습니다. 빈칸은 공개 화면의 관측 범위이며 관리 화면까지 검증한 결과가 아닙니다. 지도 반영이나 AI 추천 개선 효과를 측정한 자료도 아닙니다.</p></div></div><table class="store-table"><thead><tr><th>조사한 가게</th><th>대조한 지점</th><th>실제 출처</th></tr></thead><tbody id="store-table-body"></tbody></table><p class="scope-note">사진·리뷰·전화·영업시간은 이후 바뀔 수 있습니다. 원본 화면은 당시 관측의 근거이며 실제 페이지 전체를 그대로 복제한 UI가 아닙니다. OCR·사진 관리·리뷰 답글은 현재 기본 정비와 구현 범위를 따로 확인해야 합니다.</p><p class="scope-note"><a href="evidence/cases.json">사례별 근거 데이터</a> · <a href="evidence/sources.json">출처·관측 시각</a> · <a href="evidence/정비기준.md">정비 기준 문서</a></p></section>
</main></div><footer class="bottom"><span>seelo / 지도 정보 정비 실무 시안</span><span>사실은 정확하게. 기존 표현은 존중하며. 변경은 필요한 만큼.</span></footer></div><a class="back-top" href="#top" aria-label="맨 위로">↑</a>
<dialog class="source-dialog" id="image-dialog" aria-labelledby="dialog-caption"><div class="dialog-head"><strong id="dialog-caption">원본 화면</strong><button id="dialog-close" type="button">닫기 ×</button></div><div class="dialog-body"><img id="dialog-image" alt="원본 화면"></div></dialog>
<script type="application/json" id="case-data">__DATA__</script><script>__JS__</script></body></html>'''

html = (HTML.replace('__CSS__',CSS).replace('__JS__',JS)
    .replace('__DATA__',json.dumps(payload, ensure_ascii=False).replace('<','\\u003c'))
    .replace('__STATUS_OPTIONS__',''.join(f'<option value="{s}">{s}</option>' for s in ['정정안','표현정리','확인대기','유지'])))
(ROOT / 'index.html').write_text(html, encoding='utf-8')
print(json.dumps({'html':str(ROOT/'index.html'),'stores':len(stores),'mapSources':12,'cases':len(cases)},ensure_ascii=False))
