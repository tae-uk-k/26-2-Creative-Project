"""Fine-grained independent feature schema. Uncollected fields stay null, never inferred from AI answers."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parent/'지도기반_AI노출_20261016'
GROUPS={
 'identity':[
  ('name_address_matched','상호와 도로명 주소 동일성','all','same map detail name and address verified'),
  ('platform_id','플랫폼 상세 ID','all','stable source URL, not a name search link'),
  ('source_observed_at','출처 수집 시각','all','UTC timestamp'),
  ('owner_authorship_proven','업주 작성 확인','all','explicit author label; business verification is insufficient'),
  ('cross_map_identity','3개 지도 동일 지점 대조','all','road address, floor and branch match'),
 ],
 'meal_budget':[
  ('priced_text_menu_observed','본문 텍스트 메뉴 가격 관측','budget','images without recognized text remain unknown'),
  ('priced_menu_capture_count','관측한 가격 메뉴 수','budget','up to four sampled visible items, not full menu count'),
  ('min_captured_item_price','관측 메뉴 최저 표시가','budget','not minimum meal cost'),
  ('full_meal_item_identified','한 끼 메뉴 식별','budget','exclude drinks, sides and per-gram prices'),
  ('minimum_order_quantity','최소 주문 수량','budget,solo','explicit item-level minimum'),
  ('mandatory_extra_cost','필수 밥·상차림 추가비','budget','record exact applicable extra charges'),
  ('total_one_person_meal_cost','최소 주문 포함 1인 식사 총액','budget','only compute after complete applicable conditions'),
  ('price_effective_date','가격 적용 시점','budget','source date plus explicit validity if available'),
 ],
 'solo':[
  ('single_person_order_allowed','1인 주문 허용','solo','explicit source, not inferred from cuisine'),
  ('single_seat_or_bar','1인석·바 좌석','solo','observed seat statement or source-confirmed photo'),
  ('solo_review_statement','혼밥 이용 후기','solo','dated original review, distinguish from owner claim'),
  ('solo_peak_restriction','시간대별 혼밥 제한','solo','explicit timing and restriction'),
 ],
 'group':[
  ('six_same_table','6명 한 테이블 수용','group','same table required; six seats somewhere is insufficient'),
  ('group_capacity_range','단체 좌석 인원 범위','group','explicit minimum and maximum'),
  ('private_room_capacity','룸 인원','group','room capacity distinct from whole restaurant'),
  ('whole_store_capacity','매장 전체 수용 인원','group','never substitute for same-table capacity'),
  ('group_booking_terms','단체 예약 조건','group','deposit, minimum spend, advance notice'),
 ],
 'child':[
  ('child_entry_allowed','아이 동반 허용','child','explicit age scope; menu availability is not permission'),
  ('mild_meal_item','덜 매운 한 끼 메뉴','child','verified actual meal, not assumed from food category'),
  ('high_chair','유아 의자','child','explicit availability'),
  ('stroller_access','유모차 진입','child','entrance and internal access verified'),
  ('elevator_access','층수와 엘리베이터','child','floor count alone insufficient'),
 ],
 'parking':[
  ('dedicated_parking','전용 주차','parking','restaurant parking explicit'),
  ('partner_parking','제휴 주차','parking','explicit agreement or validation'),
  ('nearby_public_parking_only','근처 공영·유료 주차만 있음','parking','does not satisfy dedicated or partner requirement'),
  ('parking_capacity','주차 가능 대수','parking','explicit numeric capacity'),
  ('parking_discount_terms','무료 시간·지원 요금','parking','applicable spending and time conditions'),
 ],
 'reservation':[
  ('advance_seat_booking','좌석 사전 예약 가능','reservation','actual seat booking; waiting list is distinct'),
  ('waitlist_only','대기 등록만 가능','reservation','not a seat reservation'),
  ('booking_channel','예약 채널','reservation','working phone or exact booking listing'),
  ('booking_party_limits','예약 인원 제한','reservation,group','explicit min/max party size'),
  ('booking_time_limits','예약 시간·요일 제한','reservation','explicit available windows'),
 ],
 'vegan':[
  ('fully_vegan_store_claim','완전 비건 매장 명시','vegan','direct source claim, actual ingredients verification separate'),
  ('vegan_meal_item','비건 한 끼 메뉴','vegan','specified item and portion, not generic salad'),
  ('broth_animal_free','동물성 육수 배제','vegan','explicit confirmation'),
  ('sauce_animal_free','소스·드레싱 동물성 배제','vegan','fish sauce, dairy, eggs included in check'),
  ('vegan_customization_terms','비건 변경 주문 조건','vegan','what to remove, replace and advance notice'),
 ],
 'evidence':[
  ('explicit_numeric_condition','인원·가격·시간의 숫자 근거','all','complete scope with unit'),
  ('condition_scope_explained','조건 적용 범위 설명','all','day, party, menu and minimum restrictions'),
  ('source_updated_at','원문 갱신일','all','not model answer timestamp'),
  ('conflicting_source_facts','출처 간 조건 충돌','all','retain both statements with dates'),
  ('independent_corroboration','별도 출처 교차 확인','all','not copied pages counted as independent sources'),
 ]}

def read(path):return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
def write(name,rows,fields=None):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields or list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    codes=[{'feature':key,'group':group,'label_ko':label,'hypothesized_relevant_intent':intent,'definition':definition,
            'allowed_state':'observed|explicit_absence|not_collected|ambiguous','cause_proven':False,
            'prohibited_derivation':'do not derive independent restaurant features from generated recommendation reasons'}
           for group,items in GROUPS.items() for key,label,intent,definition in items]
    write('geo_feature_codebook.csv',codes)
    profiles=read(PRIOR/'kakao_features_60.csv')
    owners=json.loads((PRIOR/'naver_owner_matches.json').read_text(encoding='utf-8'))['profiles']
    owner_ids={p['restaurant_id'] for p in owners}
    rows=[]
    for p in profiles:
        known={
          'name_address_matched':(True,'observed','Kakao detail name and road address matched'),
          'platform_id':(p['source_url'].rsplit('/',1)[-1],'observed','Kakao detail URL'),
          'source_observed_at':(p['observed_at_utc'],'observed','browser observation timestamp'),
          'priced_text_menu_observed':(p['menu_price_status']=='observed_text_prices','observed' if p['menu_price_status']=='observed_text_prices' else 'ambiguous','not observed is not explicit absence'),
          'priced_menu_capture_count':(p['priced_menu_items_captured'],'observed','partial visible priced-item sample'),
          'min_captured_item_price':(p['first_up_to_four_min_displayed_item_price'],'observed' if p['first_up_to_four_min_displayed_item_price'] else 'ambiguous','not one-person meal total'),
        }
        for c in codes:
            value,state,note=known.get(c['feature'],('', 'not_collected','not yet collected under the condition-specific definition'))
            source=p['source_url'];time=p['observed_at_utc'];author='unknown'
            if p['restaurant_id'] in owner_ids and c['feature'] in ['owner_authorship_proven','cross_map_identity']:
                o=next(o for o in owners if o['restaurant_id']==p['restaurant_id'])
                value=True;state='observed';note=o['author_evidence'] if c['feature']=='owner_authorship_proven' else o['cross_map_identity']
                source=o['naver_url'];time=o['observed_at_utc'];author='owner'
            if p['restaurant_id']=='MN26-MD-03' and c['feature'] in ['group_capacity_range','whole_store_capacity']:
                o=next(o for o in owners if o['restaurant_id']==p['restaurant_id'])
                value=o['group_seat_field'] if c['feature']=='group_capacity_range' else o['total_capacity_statement']
                state='observed';source=o['naver_url'];time=o['observed_at_utc']
                author='platform_listing_structured_field' if c['feature']=='group_capacity_range' else 'owner'
                note=o['capacity_scope_note']+'; six at the same table remains unverified'
            rows.append({'restaurant_id':p['restaurant_id'],'area_id':p['area_id'],'name':p['name'],
                         'feature':c['feature'],'value':value,'observation_state':state,'source_url':source,
                         'observed_at_utc':time,'author_type':author,'note':note,'restaurant_fact_verified_beyond_source_claim':False,
                         'feature_collected_independently_of_new_AI_outcomes':True})
    write('independent_feature_observations_60.csv',rows)
    availability=[]
    for c in codes:
        group=[r for r in rows if r['feature']==c['feature']]
        availability.append({'feature':c['feature'],'label_ko':c['label_ko'],'restaurants':len(group),
                             **{s:sum(r['observation_state']==s for r in group) for s in ['observed','explicit_absence','not_collected','ambiguous']}})
    write('feature_availability_60.csv',availability)
    print(json.dumps({'restaurants':len(profiles),'features':len(codes),'long_rows':len(rows),
                      'note':'Most dining-condition features remain uncollected, not negative'},ensure_ascii=False))

if __name__=='__main__':main()
