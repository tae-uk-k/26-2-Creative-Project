"""Normalize browser-captured facts without attaching retrospective exposure labels."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def write_csv(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    data=json.loads((ROOT/'kakao_60_capture.json').read_text(encoding='utf-8'))
    frame=list(csv.DictReader((ROOT/'candidate_frame.csv').open(encoding='utf-8-sig')))
    frames={r['restaurant_id']:r for r in frame}
    observations=[dict(zip(data['row_columns'],r)) for r in data['rows']]
    assert len(observations)==60 and {x['restaurant_id'] for x in observations}==set(frames)
    intro={p['restaurant_id']:p for p in data['store_information_paragraphs']}
    missing={p['restaurant_id']:p for p in data['menu_followup_checks']}
    features=[];menus=[];fields=[];menu_sensitivity=[]
    for r in observations:
        rid=r['restaurant_id'];fr=frames[rid];text=intro.get(rid)
        if text:assert len(text['text'])==text['chars']
        prices=[]
        for position,(name,price) in enumerate(r['first_priced_menu_items'],1):
            match=re.fullmatch(r'([\d,]+)원',price)
            assert match,price
            won=int(match[1].replace(',',''));prices.append(won)
            menus.append({'restaurant_id':rid,'map_id':'kakao','menu_position_within_priced_capture':position,
                          'name':name,'price_display':price,'price_won':won,
                          'explicit_gram_unit':bool(re.search(r'\d+\s*g\b',name,re.I)),
                          'explicit_person_unit':bool(re.search(r'\d+\s*인',name)),
                          'explicit_order_minimum':bool(re.search(r'\d+\s*인\s*이상',name)),
                          'explicit_other_condition':bool(re.search(r'별도|한정|점심|저녁|공휴일|평일|주말|[~～]',name)),
                          'author_type':'unknown','source_url':fr['source_url'],'observed_at_utc':r['observed_at_utc'],
                          'price_is_total_meal_cost':False})
        status='observed_text_prices' if prices else missing[rid]['status']
        first_two_min=min(prices[:2]) if prices else None
        captured_min=min(prices) if prices else None
        features.append({'restaurant_id':rid,'area_id':fr['area_id'],'name':fr['observed_name'],
                         'verified_address':fr['observed_address'],'source_url':fr['source_url'],
                         'observed_at_utc':r['observed_at_utc'],'identity_status':'detail_name_address_matched',
                         'rating_display':float(r['rating_display']),'review_count_exact':r['review_count_exact'],
                         'photo_count_display':r['photo_count_display'],'photo_count_exact':None,
                         'photo_count_missing_reason':'plus_suffixed_display_not_exact',
                         'business_verification_label_observed':r['business_verification_label_observed'],
                         'business_verification_owner_text_proven':False,
                         'platform_ai_place_summary_observed':True,
                         'store_info_paragraph_status':'observed_author_unknown' if text else 'not_observed_in_home',
                         'store_info_paragraph_chars':text['chars'] if text else None,
                         'owner_description_status':'not_attributable_or_not_observed',
                         'owner_description_chars':None,'menu_price_status':status,
                         'priced_menu_items_captured':len(prices),
                         'first_two_min_displayed_item_price':first_two_min,
                         'first_up_to_four_min_displayed_item_price':captured_min,
                         'first_two_omit_lower_priced_visible_item':first_two_min>captured_min if prices else None,
                         'min_price_is_representative_meal_cost':False,
                         'natural_cli_exposure_label':None,'other_map_match_status':'not_collected',
                         'feature_effect_model_eligible':False})
        if prices and first_two_min>captured_min:
            menu_sensitivity.append({'restaurant_id':rid,'name':fr['observed_name'],'first_two_min_item_price':first_two_min,
                                     'first_up_to_four_min_item_price':captured_min,
                                     'scope':'Visible captured item prices; neither minimum meal total nor full menu.'})
        source_values=[('name',fr['observed_name'],'platform','observed'),('address',fr['observed_address'],'unknown','observed'),
                       ('rating',r['rating_display'],'platform','observed'),('review_count',r['review_count_exact'],'platform','observed'),
                       ('photo_count_display',r['photo_count_display'],'platform','observed'),('platform_place_summary_present',True,'platform_ai','observed'),
                       ('business_verification_label',r['business_verification_label_observed'],'platform','label_observed' if r['business_verification_label_observed'] else 'label_not_observed'),
                       ('store_information_paragraph',text['text'] if text else None,'unknown','observed' if text else 'not_observed_in_home'),
                       ('text_menu_prices',r['first_priced_menu_items'],'unknown',status)]
        for field,value,author,field_status in source_values:
            fields.append({'restaurant_id':rid,'map_id':'kakao','snapshot_at_utc':r['observed_at_utc'],
                           'source_url':fr['source_url'],'field':field,
                           'value':json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value,
                           'author_type':author,'field_status':field_status,'collection_method':'browser_rendered_dom',
                           'full_page_archive_available':False})
    write_csv('kakao_features_60.csv',features);write_csv('kakao_menu_items_60.csv',menus)
    write_csv('kakao_field_observations_60.csv',fields)
    if menu_sensitivity:write_csv('menu_capture_sensitivity.csv',menu_sensitivity)
    validation={'fixed_candidates':len(frame),'detailed_profiles':len(features),
                'unique_restaurant_ids':len({r['restaurant_id'] for r in features}),
                'area_counts':dict(Counter(r['area_id'] for r in features)),
                'detail_name_address_match_count':60,'priced_menu_profiles':sum(bool(r['priced_menu_items_captured']) for r in features),
                'priced_menu_item_rows':len(menus),'unobserved_or_unpriced_profiles':len(missing),
                'unpriced_name_only_menu_profile':'MN26-MW-09','platform_ai_summary_profiles':60,
                'business_verification_labels_observed':sum(r['business_verification_label_observed'] for r in features),
                'short_store_info_paragraphs_author_unknown':len(intro),'owner_attributed_descriptions':0,
                'first_two_omit_lower_visible_price_profiles':len(menu_sensitivity),
                'exact_photo_count_available':0,'natural_cli_outcome_labels_available':0,
                'raw_capture_sha256':hashlib.sha256((ROOT/'kakao_60_capture.json').read_bytes()).hexdigest(),
                'frozen_candidate_csv_unchanged':hashlib.sha256((ROOT/'candidate_frame.csv').read_bytes()).hexdigest()==json.loads((ROOT/'candidate_frame_freeze.json').read_text(encoding='utf-8'))['frame_sha256'],
                'causal_claim':False,'complete_menu_collection':False,'cross_map_matches_complete':False}
    assert len(menus)==221 and len(features)==60
    assert all(r['natural_cli_exposure_label'] is None for r in features)
    assert validation['frozen_candidate_csv_unchanged']
    (ROOT/'kakao_60_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(validation,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
