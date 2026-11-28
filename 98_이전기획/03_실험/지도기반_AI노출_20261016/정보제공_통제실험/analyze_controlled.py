"""Audited candidate-level tables and finite-corpus exploratory comparisons."""
import csv
import hashlib
import itertools
import json
import math
import os
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mpl-cache'))
import numpy as np
from scipy.linalg import helmert
from scipy.optimize import minimize
from scipy.special import logsumexp


def read_json(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8'))


def write_csv(name, rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)


def rate(rows, factor, value):
    group=[x for x in rows if x[factor]==value]
    return sum(x['selected'] for x in group)/len(group) if group else None


def conditional_model(rows,backend):
    group=[x for x in rows if x['backend']==backend]
    contrasts=helmert(4,full=False).T
    stores={area:sorted({r['restaurant_id'] for r in rows if r['area_id']==area}) for area in ['MD','SS','MW']}
    sets=[]
    pairs=list(itertools.combinations(range(4),2))
    for run_id in sorted({r['run_id'] for r in group}):
        choice=sorted([r for r in group if r['run_id']==run_id],key=lambda x:x['position'])
        X=[]
        for r in choice:
            v=np.zeros(15);area_index=['MD','SS','MW'].index(r['area_id'])
            v[3*area_index:3*area_index+3]=contrasts[stores[r['area_id']].index(r['restaurant_id'])]
            v[9]=r['menu_price_detail']-.5;v[10]=r['keyword_repetition']-.5;v[11]=v[9]*v[10]
            v[12:15]=contrasts[r['position']-1];X.append(v)
        X=np.asarray(X);pairX=np.asarray([X[list(pair)].sum(axis=0) for pair in pairs])
        actual=tuple(i for i,r in enumerate(choice) if r['selected'])
        assert len(actual)==2
        sets.append((pairX,pairs.index(actual)))
    def loss(beta):
        value=.5*np.dot(beta,beta);grad=beta.copy()
        for pairX,actual in sets:
            scores=pairX@beta;z=logsumexp(scores);p=np.exp(scores-z)
            value+=z-scores[actual];grad+=p@pairX-pairX[actual]
        return value,grad
    fit=minimize(loss,np.zeros(15),method='BFGS',jac=True,options={'gtol':1e-7,'maxiter':1000})
    b=fit.x
    assert np.isfinite(b).all()
    return {'backend':backend,'choice_sets':len(sets),'ridge_lambda':1,'success':bool(fit.success),
            'optimizer_message':str(fit.message),'gradient_max_abs':float(np.max(np.abs(fit.jac))),
            'menu_detail_beta_at_average_repetition':float(b[9]),
            'repetition_beta_at_average_detail':float(b[10]),'interaction_beta':float(b[11]),
            'detail_conditional_odds_ratio_repeat_absent':float(math.exp(b[9]-.5*b[11])),
            'detail_conditional_odds_ratio_repeat_present':float(math.exp(b[9]+.5*b[11])),
            'repetition_conditional_odds_ratio_detail_absent':float(math.exp(b[10]-.5*b[11])),
            'repetition_conditional_odds_ratio_detail_present':float(math.exp(b[10]+.5*b[11])),
            'interpretation':'Regularized 2-of-4 subset-choice coefficient; no CI, predictive score, or real map exposure interpretation.'}


def plot_conditions(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    fig,ax=plt.subplots(figsize=(10.5,6.2))
    colors=['#2864A0','#D38322']
    for b,backend in enumerate(['codex','agy']):
        rr=sorted([r for r in summary if r['backend']==backend],key=lambda x:x['condition'])
        xx=np.arange(4)+(b-.5)*.36
        bars=ax.bar(xx,[r['selection_rate']*100 for r in rr],width=.34,color=colors[b],
                    label='Codex' if backend=='codex' else 'Gemini / Antigravity',hatch='' if b==0 else '//')
        for bar,r in zip(bars,rr):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1.5,f'{100*r["selection_rate"]:.1f}%\n{r["selected_count"]}/{r["candidate_trials"]}',ha='center',va='bottom',fontsize=9)
    ax.set_xticks(range(4),['기본 정보','메뉴·가격 추가','지역·업종 반복','메뉴·가격 추가\n+ 지역·업종 반복'])
    ax.set_ylim(0,115);ax.set_yticks(range(0,101,20));ax.set_ylabel('후보가 상위 2곳으로 선택된 비율 (%)')
    ax.set_title('실제 지도 정보를 제공했을 때의 조건별 선택',loc='left',pad=17,fontweight='bold')
    ax.spines[['top','right']].set_visible(False);ax.legend(loc='upper left',frameon=False,fontsize=10)
    ax.axhline(50,color='#777777',lw=.8,ls=':')
    fig.text(.09,.035,'카카오맵 12곳 · 새 CLI 응답 48건 · 후보마다 4조건 교차 · 지도 자연 검색 노출 실험과 별도',fontsize=10)
    fig.subplots_adjust(bottom=.2,top=.84,left=.09,right=.98)
    fig.savefig(ROOT/'조건별_선택률.png',dpi=170);plt.close(fig)


def main():
    frozen=read_json('design_freeze.json');prompts={p['prompt_id']:p for p in read_json('prompts.json')}
    assignments=read_json('assignments.json');corpus={p['restaurant_id']:p for p in read_json('corpus.json')}
    raw_path=ROOT/'attempts.jsonl';raw_hash=hashlib.sha256(raw_path.read_bytes()).hexdigest()
    attempts=[json.loads(l) for l in raw_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    latest={r['run_id']:r for r in sorted(attempts,key=lambda x:(x['run_id'],x['attempt']))}
    assert len(latest)==48,'Wait until every planned cell has been attempted.'
    assert all(r['prompt_sha256']==prompts[r['prompt_id']]['prompt_sha256'] for r in latest.values())
    checks={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==frozen[key] for name,key in
            [('corpus.json','corpus_sha256'),('prompts.json','prompts_sha256'),('assignments.json','assignments_sha256')]}
    assert all(checks.values())
    runs=[];rows=[]
    for run_id,r in sorted(latest.items()):
        valid=r['status']=='completed' and not r['external_tools_observed']
        runs.append({'run_id':run_id,'backend':r['backend'],'area_id':r['area_id'],'repeat':r['repeat'],
                     'rotation':r['rotation'],'status':r['status'],'analysis_eligible':valid,
                     'evidence_exact_match':r['evidence_exact_match'],'elapsed_seconds':r['elapsed_seconds'],
                     'reported_models':' | '.join(r['reported_models']),'raw_path':r['raw_path']})
        if not valid:continue
        selected={s['code']:i+1 for i,s in enumerate(r['parsed_answer']['selected'])}
        for a in [x for x in assignments if x['prompt_id']==r['prompt_id']]:
            p=corpus[a['restaurant_id']];rank=selected.get(a['alias'],0)
            rows.append({**{k:a[k] for k in ['prompt_id','restaurant_id','area_id','repeat','rotation','condition','menu_price_detail','keyword_repetition','alias','position','card_sha256']},
                         'run_id':run_id,'backend':r['backend'],'name':p['name'],'source_url':p['url'],
                         'selected':int(rank>0),'selected_rank':rank,'rank_score':3-rank if rank else 0,
                         'evidence_exact_match':r['evidence_exact_match']})
    assert len(rows)==4*sum(r['analysis_eligible'] for r in runs)
    assert all(sum(x['selected'] for x in rows if x['run_id']==run_id)==2 for run_id in {r['run_id'] for r in rows})
    write_csv('runs_audited.csv',runs);write_csv('candidate_outcomes.csv',rows)
    summaries=[];effects=[];store_deltas=[]
    for backend in ['codex','agy','ALL']:
        rr=[r for r in rows if backend=='ALL' or r['backend']==backend]
        for condition in range(4):
            cc=[r for r in rr if r['condition']==condition]
            summaries.append({'backend':backend,'condition':condition,'menu_price_detail':condition&1,
                              'keyword_repetition':(condition>>1)&1,'candidate_trials':len(cc),
                              'selected_count':sum(r['selected'] for r in cc),'selection_rate':sum(r['selected'] for r in cc)/len(cc),
                              'first_choice_count':sum(r['selected_rank']==1 for r in cc)})
        for rid in sorted(corpus):
            ss=[r for r in rr if r['restaurant_id']==rid]
            d={factor:rate(ss,factor,1)-rate(ss,factor,0) for factor in ['menu_price_detail','keyword_repetition']}
            store_deltas.append({'backend':backend,'restaurant_id':rid,'name':corpus[rid]['name'],'area_id':corpus[rid]['area_id'],
                                 'candidate_trials':len(ss),'detail_absent_rate':rate(ss,'menu_price_detail',0),
                                 'detail_present_rate':rate(ss,'menu_price_detail',1),'detail_delta':d['menu_price_detail'],
                                 'repetition_absent_rate':rate(ss,'keyword_repetition',0),
                                 'repetition_present_rate':rate(ss,'keyword_repetition',1),'repetition_delta':d['keyword_repetition']})
        for factor in ['menu_price_detail','keyword_repetition']:
            effects.append({'backend':backend,'factor':factor,'absent_rate':rate(rr,factor,0),'present_rate':rate(rr,factor,1),
                            'delta':rate(rr,factor,1)-rate(rr,factor,0),'independent_stores':12})
    write_csv('condition_summary.csv',summaries);write_csv('factor_effects.csv',effects);write_csv('within_store_deltas.csv',store_deltas)
    blocks=[];tests=[]
    for area in ['MD','SS','MW']:
        for repeat in [1,2]:
            rr=[r for r in rows if r['area_id']==area and r['repeat']==repeat]
            if len(rr)!=32:continue
            for factor in ['menu_price_detail','keyword_repetition']:
                blocks.append({'area_id':area,'repeat':repeat,'factor':factor,'delta':rate(rr,factor,1)-rate(rr,factor,0)})
    write_csv('randomization_block_deltas.csv',blocks)
    for factor in ['menu_price_detail','keyword_repetition']:
        ds=np.array([r['delta'] for r in blocks if r['factor']==factor])
        if len(ds)!=6:continue
        observed=abs(ds.mean());null=[abs(np.mean(ds*np.array(signs))) for signs in itertools.product([-1,1],repeat=6)]
        p=sum(t>=observed-1e-12 for t in null)/len(null)
        tests.append({'factor':factor,'randomization_blocks':len(ds),'absolute_observed_delta':float(observed),'two_sided_exact_p':p,
                      'enumerated_flips':len(null),'analysis_status':'supplemental_specified_after_collection_started_before_effect_inspection'})
    previous=0
    for i,t in enumerate(sorted(tests,key=lambda x:x['two_sided_exact_p'])):
        previous=max(previous,min(1,(len(tests)-i)*t['two_sided_exact_p']));t['holm_p_two_factor_tests']=previous
    (ROOT/'randomization_tests.json').write_text(json.dumps(tests,ensure_ascii=False,indent=2),encoding='utf-8')
    models=[conditional_model(rows,b) for b in ['codex','agy']]
    (ROOT/'conditional_choice_ridge.json').write_text(json.dumps(models,ensure_ascii=False,indent=2),encoding='utf-8')
    plot_conditions(summaries)
    protected={
        str(ROOT.parent/'attempts.jsonl'):'31845ede3c3f60498757456b4d4107cdf13f313ca6788cc785ea8264a9998f12',
        str(ROOT.parent.parent/'ai-visibility-experiment'/'data'/'consumer_results.csv'):'149f1bb971981f3d5f5aec50a5f6ae466d44593c16af790058d1cc0ea9cfbdc3',
        str(ROOT.parent.parent/'ai-visibility-experiment'/'data'/'consumer_failures.csv'):'e2024bbd9096d269a455e38a170091aaefba7c998280c205d86b887411ecd80e'}
    protected_checks={path:hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected for path,expected in protected.items()}
    assert all(protected_checks.values())
    validation={'planned_runs':48,'attempts':len(attempts),'unique_cells':len(latest),'status_counts':dict(Counter(r['status'] for r in runs)),
                'independent_stores':len(corpus),'candidate_outcome_rows':len(rows),'selected_rows':sum(r['selected'] for r in rows),
                'every_quote_matches_supplied_card':all(r['evidence_exact_match'] for r in runs if r['analysis_eligible']),
                'no_external_tools_in_eligible_runs':all(not r['external_tools_observed'] for r in latest.values() if r['status']=='completed'),
                'input_hash_checks':checks,'protected_prior_file_hash_checks':protected_checks,
                'original_journal_unchanged':raw_hash==hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                'conditional_optimizers_converged':all(r['success'] for r in models),
                'natural_map_exposure_measured':False,'xgboost_fit':False,'population_causal_claim':False,
                'raw_journal_sha256':raw_hash}
    (ROOT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validation':validation,'effects':effects,'randomization_tests':tests,'choice_models':models},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
