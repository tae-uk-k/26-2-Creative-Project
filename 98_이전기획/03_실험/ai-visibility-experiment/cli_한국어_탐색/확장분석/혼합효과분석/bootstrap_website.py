"""Restaurant-cluster resampling sensitivity, preserving the 10-store area quotas."""
from __future__ import annotations
import contextlib
import io
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from run_analysis import OUT, SEED, prepare_data, fit_mixed, save_json, emit


def main():
    _,df=prepare_data()
    rng=np.random.default_rng(SEED)
    samples=[];draws=[];diagnostics=[]
    for repetition in range(200):
        parts=[];slot=0
        for area,group in df[['area','brand_group']].drop_duplicates().groupby('area'):
            names=sorted(group.brand_group)
            for name in rng.choice(names,len(names),replace=True):
                sub=df[df.brand_group.eq(name)].copy()
                sub['brand_group']=name+f'__bootstrap_slot{slot}'
                parts.append(sub)
                draws.append({'repetition':repetition,'area':area,'slot':slot,'original_brand_group':name})
                slot+=1
        sampled=pd.concat(parts,ignore_index=True)
        assert len(sampled)==600 and sampled.brand_group.nunique()==30
        with contextlib.redirect_stdout(io.StringIO()):
            fit=fit_mixed(sampled,f'bootstrap_{repetition}',seed=SEED+repetition)
        index=fit['model'].fep_names.index('own_website')
        value=float(fit['result'].fe_mean[index])
        samples.append({'repetition':repetition,'website_log_odds':value,'website_odds_ratio':float(np.exp(value))})
        diagnostics.append(fit['diagnostic'])
        if (repetition+1)%50==0:emit({'restaurant_bootstrap_completed':repetition+1})
    pd.DataFrame(samples).to_csv(OUT/'bootstrap_website_estimates.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(draws).to_csv(OUT/'bootstrap_brand_draws.csv',index=False,encoding='utf-8-sig')
    values=np.array([r['website_odds_ratio'] for r in samples])
    output={'repetitions':200,'unit':'restaurant, within area, with replacement',
        'independent_source_stores':30,'resampled_slots_not_new_stores':True,
        'website_odds_ratio_median':float(np.median(values)),
        'website_odds_ratio_percentile95_low':float(np.quantile(values,.025)),
        'website_odds_ratio_percentile95_high':float(np.quantile(values,.975)),
        'all_optimizer_success':all(d['optimizer_success'] for d in diagnostics),
        'interpretation':'resampling sensitivity of fitted posterior means in a purposive cohort; not a causal confidence interval'}
    save_json('bootstrap_website_summary.json',output)
    save_json('bootstrap_model_diagnostics.json',diagnostics)
    emit(output)


if __name__=='__main__':
    with threadpool_limits(limits=2):main()
