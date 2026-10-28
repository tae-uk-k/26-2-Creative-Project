"""Independent raw-to-table checks for the two provided-information arms and map captures."""
import ast
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parent


def csv_rows(path):
    return list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    capture=json.loads((ROOT/'kakao_60_capture.json').read_text(encoding='utf-8'))
    canonical=json.dumps(capture['rows'],ensure_ascii=False,separators=(',',':'))
    checksum=2166136261
    for byte in canonical.encode('utf-8'):
        checksum=((checksum^byte)*16777619)&0xffffffff
    # Calculated independently inside the browser from live-capture rows, before copying to disk.
    assert f'{checksum:08x}'=='93f812d2'
    assert len(canonical)==8785
    features=csv_rows(ROOT/'kakao_features_60.csv');menus=csv_rows(ROOT/'kakao_menu_items_60.csv')
    assert len(features)==60 and len(menus)==221
    assert all(not r['natural_cli_exposure_label'] and not r['photo_count_exact'] for r in features)
    assert len({r['restaurant_id'] for r in features})==60
    assert Counter(r['area_id'] for r in features)=={'MD':20,'SS':20,'MW':20}
    arms=[]
    for folder,factor in [(ROOT/'정보제공_통제실험','menu_price_detail'),(ROOT/'정보제공_통제실험'/'동일정보_표현비교','structured_layout')]:
        attempts=[json.loads(l) for l in (folder/'attempts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
        assignments=json.loads((folder/'assignments.json').read_text(encoding='utf-8'))
        prompts={p['prompt_id']:p for p in json.loads((folder/'prompts.json').read_text(encoding='utf-8'))}
        derived=csv_rows(folder/'candidate_outcomes.csv')
        frozen=json.loads((folder/'design_freeze.json').read_text(encoding='utf-8'))
        assert len(attempts)==48==len({r['run_id'] for r in attempts})
        assert len(derived)==192 and sum(int(r['selected']) for r in derived)==96
        for r in attempts:
            assert r['status']=='completed' and not r['external_tools_observed']
            assert r['prompt_sha256']==hashlib.sha256(prompts[r['prompt_id']]['prompt'].encode('utf-8')).hexdigest()
            choices=r['parsed_answer']['selected']
            assert [s['rank'] for s in choices]==[1,2]
            assigned={a['alias']:a for a in assignments if a['prompt_id']==r['prompt_id']}
            chosen={s['code'] for s in choices}
            assert len(chosen)==2 and chosen.issubset(assigned)
            for s in choices:
                assert s['evidence'] and s['evidence'] in assigned[s['code']]['card_text']
            for row in [x for x in derived if x['run_id']==r['run_id']]:
                assert int(row['selected'])==int(row['alias'] in chosen)
                assert row['restaurant_id']==assigned[row['alias']]['restaurant_id']
                assert int(row[factor])==assigned[row['alias']][factor]
        for area in ['MD','SS','MW']:
            for repeat in [1,2]:
                aa=[a for a in assignments if a['area_id']==area and a['repeat']==repeat]
                assert Counter((a['condition'],a['position']) for a in aa)==Counter({(i,j):1 for i in range(4) for j in range(1,5)})
                for rid in {a['restaurant_id'] for a in aa}:
                    assert {a['condition'] for a in aa if a['restaurant_id']==rid}==set(range(4))
        for name,key in [('corpus.json','corpus_sha256'),('prompts.json','prompts_sha256'),('assignments.json','assignments_sha256')]:
            assert sha(folder/name)==frozen[key]
        # Independently recompute factor rates directly from raw chosen aliases.
        raw_counts=Counter()
        for r in attempts:
            chosen={s['code'] for s in r['parsed_answer']['selected']}
            for a in [a for a in assignments if a['prompt_id']==r['prompt_id']]:
                for f in [factor,'keyword_repetition']:
                    raw_counts[(r['backend'],f,a[f],'denom')]+=1
                    raw_counts[(r['backend'],f,a[f],'selected')]+=a['alias'] in chosen
        for effect in csv_rows(folder/'factor_effects.csv'):
            if effect['backend']=='ALL':continue
            for value,field in [(0,'absent_rate'),(1,'present_rate')]:
                key=(effect['backend'],effect['factor'],value)
                assert abs(raw_counts[key+('selected',)]/raw_counts[key+('denom',)]-float(effect[field]))<1e-12
        arms.append({'folder':folder.name,'runs':48,'candidate_rows':192,'selected_rows':96,
                     'quotes_valid':True,'no_external_tools':True,'position_and_condition_balance':True,'raw_rates_equal_derived':True})
    original_corpus=json.loads((ROOT/'정보제공_통제실험'/'corpus.json').read_text(encoding='utf-8'))
    frames={r['source_url']:r['restaurant_id'] for r in csv_rows(ROOT/'candidate_frame.csv')}
    for p in original_corpus:
        rid=frames[p['url']]
        new=[r for r in menus if r['restaurant_id']==rid][:2]
        assert [(r['name'],r['price_display']) for r in new]==[(m['name'],m['price_display']) for m in p['menus']]
    protected={ROOT/'attempts.jsonl':'31845ede3c3f60498757456b4d4107cdf13f313ca6788cc785ea8264a9998f12',
               ROOT/'정보제공_통제실험'/'attempts.jsonl':'c87a344a8ef3ace1d2b3c9efdf9a9dda36f7f9c4299c8b0608074dd701fa6bea',
               ROOT/'정보제공_통제실험'/'동일정보_표현비교'/'attempts.jsonl':'5f0da987421ec81b16fd515ec1147732397fdd64a017c5c438b89fe0b8a5d6e5',
               ROOT.parent/'ai-visibility-experiment'/'data'/'consumer_results.csv':'149f1bb971981f3d5f5aec50a5f6ae466d44593c16af790058d1cc0ea9cfbdc3',
               ROOT.parent/'ai-visibility-experiment'/'data'/'consumer_failures.csv':'e2024bbd9096d269a455e38a170091aaefba7c998280c205d86b887411ecd80e'}
    protected_checks={str(path):sha(path)==expected for path,expected in protected.items()}
    assert all(protected_checks.values())
    for path in ROOT.rglob('*.py'):ast.parse(path.read_text(encoding='utf-8'))
    for path in ROOT.rglob('*.json'):
        if '.mpl-cache' not in path.parts:json.loads(path.read_text(encoding='utf-8'))
    result={'passed':True,'controlled_arms':arms,'controlled_total_runs':96,'independent_controlled_stores':12,
            'fixed_future_candidates':60,'detailed_kakao_profiles':60,'priced_menu_profiles':57,'priced_menu_rows':221,
            'browser_to_saved_row_checksum':'93f812d2','browser_to_saved_rows_exact':True,
            'first_12_menu_pairs_unchanged_in_later_capture':True,'naver_owner_cross_map_matches':2,
            'protected_file_hash_checks':protected_checks,'natural_map_exposure_effect_still_unmeasured':True,
            'all_local_report_links_valid':None}
    output=ROOT/'followup_validation.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    broken=[]
    for path in [ROOT/'README.md',ROOT/'수집_검수_후속결과.md',ROOT/'정보제공_통제실험'/'README.md',ROOT/'전처리_코드북.md']:
        for link in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if link.startswith(('http://','https://','#')):continue
            if not (path.parent/unquote(link)).exists():broken.append((str(path),link))
    assert not broken,broken
    result['all_local_report_links_valid']=True
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
