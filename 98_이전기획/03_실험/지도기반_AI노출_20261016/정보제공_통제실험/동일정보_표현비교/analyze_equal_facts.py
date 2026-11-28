"""Descriptive equal-facts follow-up; no confirmatory significance claims."""
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import analyze_controlled as common
common.ROOT=ROOT


def main():
    frozen=json.loads((ROOT/'design_freeze.json').read_text(encoding='utf-8'))
    assignments=json.loads((ROOT/'assignments.json').read_text(encoding='utf-8'))
    corpus={p['restaurant_id']:p for p in json.loads((ROOT/'corpus.json').read_text(encoding='utf-8'))}
    attempts=[json.loads(l) for l in (ROOT/'attempts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    latest={r['run_id']:r for r in sorted(attempts,key=lambda x:(x['run_id'],x['attempt']))}
    assert len(latest)==48,'All 48 cells must be attempted first.'
    checks={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==frozen[key] for name,key in
            [('corpus.json','corpus_sha256'),('prompts.json','prompts_sha256'),('assignments.json','assignments_sha256')]}
    assert all(checks.values())
    runs=[];rows=[]
    for run_id,r in sorted(latest.items()):
        valid=r['status']=='completed' and not r['external_tools_observed']
        runs.append({'run_id':run_id,'backend':r['backend'],'area_id':r['area_id'],'repeat':r['repeat'],'rotation':r['rotation'],
                     'status':r['status'],'analysis_eligible':valid,'evidence_exact_match':r['evidence_exact_match']})
        if not valid:continue
        chosen={s['code']:i+1 for i,s in enumerate(r['parsed_answer']['selected'])}
        for a in [x for x in assignments if x['prompt_id']==r['prompt_id']]:
            rank=chosen.get(a['alias'],0)
            rows.append({**{k:a[k] for k in ['prompt_id','restaurant_id','area_id','repeat','rotation','condition','structured_layout','keyword_repetition','alias','position']},
                         'run_id':run_id,'backend':r['backend'],'name':corpus[a['restaurant_id']]['name'],
                         'selected':int(rank>0),'selected_rank':rank,'evidence_exact_match':r['evidence_exact_match']})
    assert len(rows)==4*sum(r['analysis_eligible'] for r in runs)
    common.write_csv('runs_audited.csv',runs);common.write_csv('candidate_outcomes.csv',rows)
    summaries=[];effects=[];stores=[]
    for backend in ['codex','agy','ALL']:
        rr=[r for r in rows if backend=='ALL' or r['backend']==backend]
        for condition in range(4):
            cc=[r for r in rr if r['condition']==condition]
            summaries.append({'backend':backend,'condition':condition,'structured_layout':condition&1,
                              'keyword_repetition':(condition>>1)&1,'candidate_trials':len(cc),
                              'selected_count':sum(r['selected'] for r in cc),
                              'selection_rate':sum(r['selected'] for r in cc)/len(cc)})
        for factor in ['structured_layout','keyword_repetition']:
            effects.append({'backend':backend,'factor':factor,'absent_rate':common.rate(rr,factor,0),
                            'present_rate':common.rate(rr,factor,1),'delta':common.rate(rr,factor,1)-common.rate(rr,factor,0),
                            'independent_stores':12})
        for rid,p in corpus.items():
            ss=[r for r in rr if r['restaurant_id']==rid]
            stores.append({'backend':backend,'restaurant_id':rid,'name':p['name'],'area_id':p['area_id'],
                           'candidate_trials':len(ss),'selected_count':sum(x['selected'] for x in ss),
                           'selection_rate':sum(x['selected'] for x in ss)/len(ss),
                           'layout_delta':common.rate(ss,'structured_layout',1)-common.rate(ss,'structured_layout',0),
                           'repetition_delta':common.rate(ss,'keyword_repetition',1)-common.rate(ss,'keyword_repetition',0)})
    common.write_csv('condition_summary.csv',summaries);common.write_csv('factor_effects.csv',effects)
    common.write_csv('within_store_deltas.csv',stores)
    equal=True
    for rid in corpus:
        for repeat in [1,2]:
            for repetition in [0,1]:
                cards=[r['card_text'] for r in assignments if r['restaurant_id']==rid and r['repeat']==repeat and r['keyword_repetition']==repetition]
                equal &= len(cards)==2 and len({' '.join(re.sub(r'(?m)^- ','',c).split()) for c in cards})==1
    validation={'planned_runs':48,'attempts':len(attempts),'unique_cells':len(latest),'independent_stores':12,
                'status_counts':dict(Counter(r['status'] for r in runs)),'candidate_rows':len(rows),
                'selected_rows':sum(r['selected'] for r in rows),'input_hash_checks':checks,
                'identical_facts_across_layouts':equal,'every_quote_matches_supplied_card':all(r['evidence_exact_match'] for r in runs if r['analysis_eligible']),
                'no_external_tools':all(not r['external_tools_observed'] for r in latest.values()),
                'same_corpus_as_prior_arm':(ROOT/'corpus.json').read_bytes()==(ROOT.parent/'corpus.json').read_bytes(),
                'original_information_arm_hash_unchanged':hashlib.sha256((ROOT.parent/'attempts.jsonl').read_bytes()).hexdigest()=='c87a344a8ef3ace1d2b3c9efdf9a9dda36f7f9c4299c8b0608074dd701fa6bea',
                'natural_map_exposure_measured':False,'confirmatory_test':False,
                'raw_journal_sha256':hashlib.sha256((ROOT/'attempts.jsonl').read_bytes()).hexdigest()}
    assert equal and validation['original_information_arm_hash_unchanged']
    (ROOT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validation':validation,'effects':effects,'store_selection_rates':[r for r in stores if r['backend']=='ALL']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
