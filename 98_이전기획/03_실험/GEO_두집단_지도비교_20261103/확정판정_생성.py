"""Preserve initial coding and apply a documented source-review correction.
No recommendation outcomes exist at the time of this correction.
"""
import json
from pathlib import Path

root=Path(__file__).resolve().parent
data=json.loads((root/'수동검수_판정.json').read_text(encoding='utf-8'))
data['version']='20261103-final-before-any-recommendations'
data['coding_corrections']=[{
    'candidate_id':'MD-17531780','item':2,'old_score':1,'new_score':2,
    'reason':'메뉴 시간만으로 채점했던 초안에 공식 예약 지점별 무료 치즈 서비스의 BBQ 고객 조건을 반영. 실제 추천 호출 0 상태에서 근거 검수로 정정. 점심특선 정확한 주문 시간 미확인 자체는 유지.',
    'source':'https://www.wangbijib-restaurant.com/reservations'
}]
for store in data['stores']:
    if store['candidate_id']=='MD-17531780':
        store['scores'][1]={
            'item':2,'score':2,
            'quote':'Wangbijib Myeongdong Central Branch / 🧀 Get Free Grilled Cheese (BBQ customers only) / 2nd Floor, 45 Myeongdong 8na-gil, Jung District, Seoul, South Korea',
            'platform':'official_detail','section':'reservation_hours',
            'reason':'공식 예약 목록에서 중앙점 2층 지점의 무료 치즈 제공 서비스와 BBQ 고객 적용 조건이 직접 연결됨. 지도 메뉴의 평일점심특선 정확한 주문 시간은 여전히 미확인. 메뉴 시간만 반영했던 초안 1점을 근거 검수로 정정.',
            'additional_sources':['kakao_detail:menu']}
for pair in data['close_pair_reviews']:
    if 'MD-917289719' in pair['members']:
        pair['reason']='카카오44/53위·Google18/11위·평점4.8/4.7·리뷰3588/3139는 비슷함. 확정 점수5/5로 사전 최소 차이2점 미충족. 무한리필과 정식/중량 구이의 서비스 차이, 메뉴 수5/20 및 공식 가격 대응 미확정도 남음. 중앙점은 공식 무료 치즈의 BBQ 고객 조건을 반영해 초안4점에서5점으로 근거 검수 정정; 추천 호출은 정정 전후 모두0.'
with (root/'수동검수_확정판정.json').open('x',encoding='utf-8') as f:
    json.dump(data,f,ensure_ascii=False,indent=2)
