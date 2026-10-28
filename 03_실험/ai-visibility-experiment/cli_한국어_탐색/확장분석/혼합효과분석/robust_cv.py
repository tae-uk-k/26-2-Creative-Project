"""Five area-balanced grouped partitions; no outcome-based split selection."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from run_analysis import OUT, BASE, SEED, INPUTS, MODEL_COLUMNS, prepare_data, feature_pipeline, fit_ebm, fit_mixed, predict_mixed, score, save_json, emit


def main():
    _,primary=prepare_data()
    models=['global_mean','context_mean','logistic_l2','mixed_logistic','ebm_main_effects','xgboost_shallow']
    all_predictions=[];fold_table=[];seed_scores=[];diagnostics=[]
    for repetition in range(5):
        seed=SEED+repetition
        rng=np.random.default_rng(seed)
        assignments={}
        for area,group in primary[['area','brand_group']].drop_duplicates().groupby('area'):
            brands=np.array(sorted(group.brand_group))
            assert len(brands)==10
            rng.shuffle(brands)
            for index,brand in enumerate(brands):assignments[brand]=index % 5
        fold_ids=primary.brand_group.map(assignments).to_numpy()
        predictions={m:np.empty(len(primary)) for m in models}
        for fold in range(5):
            tr=np.flatnonzero(fold_ids!=fold);te=np.flatnonzero(fold_ids==fold)
            train,test=primary.iloc[tr],primary.iloc[te]
            assert not set(train.brand_group)&set(test.brand_group)
            assert set(test[['brand_group','area']].drop_duplicates().area.value_counts())=={2}
            predictions['global_mean'][te]=train.y.mean()
            means=train.groupby(['prompt_id','backend']).y.mean().to_dict()
            predictions['context_mean'][te]=[means[(p,b)] for p,b in zip(test.prompt_id,test.backend)]
            for kind in ['logistic_l2','xgboost_shallow']:
                pipe=feature_pipeline(kind)
                pipe.fit(train[MODEL_COLUMNS],train.y)
                predictions[kind][te]=pipe.predict_proba(test[MODEL_COLUMNS])[:,1]
            ebm=fit_ebm(train)
            predictions['ebm_main_effects'][te]=ebm.predict_proba(test[MODEL_COLUMNS])[:,1]
            fit=fit_mixed(train,f'balanced_rep{repetition}_fold{fold}',seed=seed)
            predictions['mixed_logistic'][te]=predict_mixed(fit,test)
            diagnostics.append(fit['diagnostic'])
            fold_table += [{'repetition':repetition,'seed':seed,'fold':fold,'entity_id':r.entity_id,'brand_group':r.brand_group,'area':r.area}
                for r in test[['entity_id','brand_group','area']].drop_duplicates().itertuples(index=False)]
        for model,p in predictions.items():
            assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
            seed_scores.append({'repetition':repetition,'seed':seed,'model':model,**score(primary.y.to_numpy(),p)})
        saved=primary[['run_id','entity_id','name_ko','brand_group','backend','area','y']].copy()
        saved['repetition']=repetition;saved['seed']=seed;saved['fold']=fold_ids
        for model,p in predictions.items():saved[model]=p
        all_predictions.append(saved)
        emit({'balanced_group_cv_repetition_completed':repetition})
    oof=pd.concat(all_predictions,ignore_index=True)
    oof.to_csv(OUT/'robust_oof_predictions.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(fold_table).to_csv(OUT/'robust_cv_store_folds.csv',index=False,encoding='utf-8-sig')
    seeds=pd.DataFrame(seed_scores)
    seeds.to_csv(OUT/'robust_cv_by_seed.csv',index=False,encoding='utf-8-sig')
    by_brand=oof.groupby('brand_group',sort=True)
    rng=np.random.default_rng(SEED)
    bootstrap=rng.integers(0,len(by_brand),(5000,len(by_brand)))
    global_losses=by_brand.apply(lambda d:np.mean((d.y-d.global_mean)**2)).to_numpy()
    output=[]
    for model in models:
        losses=by_brand.apply(lambda d:np.mean((d.y-d[model])**2)).to_numpy()
        ci=np.quantile(losses[bootstrap].mean(axis=1),[.025,.975])
        delta_ci=np.quantile((losses-global_losses)[bootstrap].mean(axis=1),[.025,.975])
        scores=seeds[seeds.model.eq(model)]
        output.append({'model':model,'brier':float(scores.brier.mean()),'brier_seed_sd':float(scores.brier.std()),
            'log_loss':float(scores.log_loss.mean()),'pr_auc_average_precision':float(scores.pr_auc_average_precision.mean()),
            'roc_auc':float(scores.roc_auc.mean()),'brier_bootstrap95_low':float(ci[0]),'brier_bootstrap95_high':float(ci[1]),
            'brier_minus_global':float(np.mean(losses-global_losses)),
            'paired_difference95_low':float(delta_ci[0]),'paired_difference95_high':float(delta_ci[1]),
            'independent_stores':30,'unique_evaluation_rows':600,'evaluation_repetitions':5,
            'split':'5 fixed seeds, 5 folds, 2 held-out stores per area per fold',
            'interval':'restaurant-cluster bootstrap of fixed repeated OOF losses; does not refit models'})
    pd.DataFrame(output).sort_values('brier').to_csv(OUT/'robust_model_comparison.csv',index=False,encoding='utf-8-sig')
    save_json('robust_cv_diagnostics.json',diagnostics)
    save_json('robust_cv_validation.json',{'passed':True,'independent_stores':30,'unique_trials':600,
        'oof_rows_including_repeats':len(oof),'repeated_partitions':5,'folds_per_partition':5,
        'brands_cross_train_test':0,'held_out_stores_per_area':2,'all_probabilities_finite':True,
        'data_sha256':{n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in INPUTS},
        'code_sha256':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ['run_analysis.py','robust_cv.py']},
        'all_optimizer_success':all(d['optimizer_success'] for d in diagnostics),
        'source_recipe':'Fixed parameters, no hyperparameter search or choice of favorable seed',
        'ebm_outer_bags':1,'causal_validation':False})
    emit({'robust_cv_completed':True,'scores':output})


if __name__=='__main__':
    with threadpool_limits(limits=2):main()
