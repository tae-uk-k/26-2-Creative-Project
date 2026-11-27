"""Independent count, denominator, provenance, and preservation checks for the GEO study."""
import ast
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'ai-visibility-experiment'/'cli_한국어_탐색'

def read(name):return list(csv.DictReader((ROOT/name).open(encoding='utf-8-sig',newline='')))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(text):return re.sub(r'[^0-9a-z가-힣]','',str(text or '').lower())

def main():
    checks={}
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    prompts=json.loads((ROOT/'prompts.json').read_text(encoding='utf-8'))
    freeze=json.loads((ROOT/'design_freeze.json').read_text(encoding='utf-8'))
    records=[json.loads(l) for l in (ROOT/'attempts.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(manifest)==96 and len({r['run_id'] for r in manifest})==96 and len(prompts)==24
    assert all(n==1 for n in Counter((r['area_id'],r['intent'],r['backend'],r['repeat']) for r in manifest).values())
    assert digest(ROOT/'prompts.json')==freeze['prompts_sha256']
    assert digest(ROOT/'manifest.json')==freeze['manifest_sha256']
    checks['frozen_design_and_full_factorial']=True
    for p,sha in freeze['protected_sha256'].items():assert digest(Path(p))==sha,p
    consumer=ROOT.parent/'ai-visibility-experiment'/'data'
    assert digest(consumer/'consumer_results.csv')=='149f1bb971981f3d5f5aec50a5f6ae466d44593c16af790058d1cc0ea9cfbdc3'
    assert digest(consumer/'consumer_failures.csv')=='e2024bbd9096d269a455e38a170091aaefba7c998280c205d86b887411ecd80e'
    checks['earlier_journals_and_consumer_data_unchanged']=True
    latest={}
    for r in records:
        old=latest.get(r['run_id'])
        if old is None or (old['status']!='completed' and r['attempt']>=old['attempt']) or r['status']=='completed':latest[r['run_id']]=r
        assert Path(r['raw_path']).exists() and Path(r['stderr_path']).exists()
    assert set(latest)=={r['run_id'] for r in manifest}
    runs=read('runs_audited.csv');recs=read('recommendations.csv')
    assert len(runs)==96 and all(r['status']!='not_attempted' for r in runs)
    for r in runs:
        raw=latest[r['run_id']]
        assert raw['status']==r['status']
        selected=[x for x in recs if x['run_id']==r['run_id']]
        if r['status']=='completed':
            rr=raw['parsed_answer']['restaurants']
            assert len(rr)==len(selected)==int(r['recommendations']) and len(rr)<=5
            assert [int(x['rank']) for x in rr]==list(range(1,len(rr)+1))
            assert len({norm(x['name']) for x in rr})==len(rr)
            assert sorted((norm(x['name']),x.get('condition_status')) for x in rr)==sorted((x['name_key'],x['condition_status_raw']) for x in selected)
        else:assert not selected and r['recommendations']==''
    assert all(r['condition_status'] in ['not_applicable','confirmed','partial','unknown'] for r in recs)
    assert all(r['evidence_level_claim'] in ['body','snippet','inference','unknown'] for r in recs)
    assert all(not r.get('unrequested_tool_calls') for r in runs)
    checks['new_outcomes_raw_counts_failure_exclusion_and_tool_scope']=True
    for summary in read('intent_summary.csv'):
        rr=[r for r in runs if r['intent']==summary['intent'] and (summary['backend']=='combined' or r['backend']==summary['backend'])]
        cc=[r for r in recs if r['intent']==summary['intent'] and (summary['backend']=='combined' or r['backend']==summary['backend'])]
        assert sum(r['status']=='completed' for r in rr)==int(summary['completed'])
        assert len(cc)==int(summary['recommendations'])
        assert sum(r['status']=='completed' and r['recommendations']=='0' for r in rr)==int(summary['zero_recommendation_answers'])
    for r in read('store_intent_rates.csv'):
        rr=[x for x in runs if x['status']=='completed' and x['area_id']==r['area_id'] and x['intent']==r['intent'] and (r['backend']=='combined' or x['backend']==r['backend'])]
        cc=[x for x in recs if x['area_id']==r['area_id'] and x['intent']==r['intent'] and x['name_key']==r['name_key'] and (r['backend']=='combined' or x['backend']==r['backend'])]
        assert len(rr)==int(r['successful_runs']) and len(cc)==int(r['appearances']) and len(cc)<=len(rr)
    checks['new_summary_and_store_denominators_recomputed']=True
    old_raw=[json.loads(l) for b in ['codex','agy'] for l in (OLD/f'results_{b}.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(old_raw)==240
    cleaned=list(csv.DictReader((OLD/'확장분석'/'recommendations_clean.csv').open(encoding='utf-8-sig')))
    lookup={(r['run_id'],int(r['rank'])):r for r in cleaned}
    for r in old_raw:
        assert r['status']=='success' and len(r['recommendations'])==5
        for rec in r['recommendations']:assert rec['name']==lookup[(r['run_id'],int(rec['rank']))]['name_raw']
    old_den=Counter((r['prompt_id'],r['backend']) for r in old_raw)
    old_k=Counter((r['entity_id'],r['prompt_id'],r['backend']) for r in cleaned if r['entity_id'])
    for r in read('legacy_intent_rates.csv'):
        bs=['codex','agy'] if r['backend']=='combined' else [r['backend']]
        assert sum(old_k[(r['entity_id'],r['prompt_id'],b)] for b in bs)==int(r['appearances'])
        assert sum(old_den[(r['prompt_id'],b)] for b in bs)==int(r['successful_runs'])
    checks['legacy_raw_240_to_1200_and_intent_counts']=True
    codes=read('geo_feature_codebook.csv');features=read('independent_feature_observations_60.csv')
    assert len(codes)==47 and len(features)==60*47
    assert len({r['restaurant_id'] for r in features})==60
    assert len({(r['restaurant_id'],r['feature']) for r in features})==len(features)
    assert all(r['value']=='' for r in features if r['observation_state']=='not_collected')
    assert all(r['source_url'].startswith('https://') for r in features)
    assert all(r['feature_collected_independently_of_new_AI_outcomes']=='True' for r in features)
    checks['feature_schema_and_unknown_not_negative']=True
    for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    for p in ROOT.glob('*.json'):json.loads(p.read_text(encoding='utf-8'))
    assert (ROOT/'조건별_추천변화.png').stat().st_size>20000
    checks['python_json_and_figure_artifacts']=True
    result={'passed':True,'checks':checks,'unique_cells':len(latest),'total_attempts':len(records),
            'status_counts':dict(Counter(r['status'] for r in runs)),'new_recommendations':len(recs),
            'legacy_recommendations':len(cleaned),'features':len(codes),'feature_rows':len(features),
            'journal_sha256':digest(ROOT/'attempts.jsonl'),
            'limits':['branch identities not verified','condition labels self-reported except separate source audits',
                      'two repeats insufficient for confirmation','condition features mostly missing; no causal or XGBoost fit']}
    (ROOT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
