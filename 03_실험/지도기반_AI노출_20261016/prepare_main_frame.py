"""Freeze future natural-search candidates from native map lists, not AI answers."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    src=ROOT/'candidate_registry_source.tsv'
    native=list(csv.DictReader(src.open(encoding='utf-8'),delimiter='\t'))
    assert len(native)==60 and len({x['place_id'] for x in native})==60
    assert Counter(x['area_id'] for x in native)=={'MD':20,'SS':20,'MW':20}
    captured=json.loads((ROOT/'정보제공_통제실험'/'corpus.json').read_text(encoding='utf-8'))
    verified={p['url'] for p in captured}
    areas={'MD':'명동','SS':'성수','MW':'망원'}
    rows=[]
    for x in native:
        url='https://place.map.kakao.com/'+x['place_id'];ok=url in verified
        rows.append({'restaurant_id':f'MN26-{x["area_id"]}-{int(x["rank"]):02}', 'brand_group_id':'',
                     'area_id':x['area_id'],'observed_name':x['observed_name'],'observed_address':x['observed_address'],
                     'verified_name':x['observed_name'] if ok else '', 'verified_address':x['observed_address'] if ok else '',
                     'selected_at_utc':'2026-10-16T07:43:10.120Z','selection_query':areas[x['area_id']]+' 식당',
                     'selection_map':'kakao','selection_rank':int(x['rank']), 'selection_page':1 if int(x['rank'])<=15 else 2,
                     'is_sponsored':'no_label_observed','sort_mode':'default_accuracy','map_center':'not_manually_fixed',
                     'source_url':url,'identity_status':'detail_name_address_matched' if ok else 'native_list_only',
                     'future_main_outcome_label':'','other_map_match_status':'not_collected'})
    path=ROOT/'candidate_frame.csv'
    if path.exists():
        current=list(csv.DictReader(path.open(encoding='utf-8-sig')))
        assert not current or [r['source_url'] for r in current]==[r['source_url'] for r in rows], 'Do not silently change fixed candidates'
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
    meta={'candidate_count':60,'area_counts':dict(Counter(r['area_id'] for r in rows)),
          'unique_kakao_place_ids':60,'detail_name_address_verified':sum(r['identity_status']=='detail_name_address_matched' for r in rows),
          'selection_used_ai_response':False,'selection_rule':'First 20 native places per regional 식당 query; first 15 in all-results view, next five after 장소 더보기; ACTIVE page 2 verified in all three tabs; Myeongdong page 1 returned same initial four.',
          'native_search_context':'Current browser, no login or manual location/center control; region means map search vicinity, not administrative border.',
          'source_map':'kakao','google_naver_matches_complete':False,'brand_groups_complete':False,
          'selected_for_future_natural_search_only':True,'frozen_after_controlled_experiment_started':True,
          'interpretation':'Do not retroactively label absent candidates as non-selected in the 12-store provided-information experiments. No future main natural-search labels exist yet.',
          'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'frame_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (ROOT/'candidate_frame_freeze.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
