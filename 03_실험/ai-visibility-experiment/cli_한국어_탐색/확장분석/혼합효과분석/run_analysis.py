"""Small-cohort pilot: repeated Bernoulli observations, grouped validation.

This never changes the frozen candidate frame, original labels or consumer data.
All associations are conditional on a purposively selected 30-restaurant cohort.
The original broad-feature readiness guard is not a statistical power rule;
this explicit pilot uses only two documented restaurant predictors.
"""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import time
import warnings
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.special import expit
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import brier_score_loss, log_loss, average_precision_score, roc_auc_score
from interpret.glassbox import ExplainableBoostingClassifier
from xgboost import XGBClassifier
from threadpoolctl import threadpool_limits

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
SEED = 20261014
MENU_LEVELS = ['noodles_dumplings', 'soups_stews', 'barbecue', 'set_meals',
               'western_dining', 'market_snacks', 'other_meals', 'jokbal']
MODEL_COLUMNS = ['own_website', 'menu_family_external', 'prompt_id', 'backend']
INPUTS = ['exposure_trials.csv', 'restaurant_features.csv', 'restaurant_registry.csv',
          'category_codebook.csv', 'frame_freeze.json']


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                           default=lambda v: v.item() if hasattr(v, 'item') else str(v)), encoding='utf-8')


def prepare_data():
    trials = pd.read_csv(BASE / 'exposure_trials.csv')
    feat = pd.read_csv(BASE / 'restaurant_features.csv', keep_default_na=False)
    feat = feat[feat.sampling_cohort.eq('original30_preselected')].copy()
    assert len(feat) == 30 and feat.entity_id.is_unique
    df = trials[trials.sampling_cohort.eq('original30_preselected')].merge(
        feat[['entity_id','name_ko','own_website_external','menu_family_external','identity_status']],
        on='entity_id', validate='many_to_one')
    df['own_website'] = pd.to_numeric(df.own_website_external, errors='raise')
    df['y'] = df.appeared_brand.astype(int)
    assert len(df) == 2400 and df[['run_id','entity_id']].duplicated().sum() == 0
    assert df.own_website.notna().all() and set(df.y) == {0,1}
    assert set(df.menu_family_external) <= set(MENU_LEVELS)
    primary = df[df.intent.eq('general')].copy().reset_index(drop=True)
    assert len(primary) == 600 and primary.groupby('entity_id').size().eq(20).all()
    primary.to_csv(OUT / 'data_primary_general.csv', index=False, encoding='utf-8-sig')
    df.to_csv(OUT / 'data_all_queries.csv', index=False, encoding='utf-8-sig')
    coverage = []
    for column in ['own_website_external','menu_family_external','menu_price_public_external',
                   'signature_price_krw_external','solo_seating_external','tourism_individual_page_external',
                   'guide_individual_page_external','established_year_external','google_review_count','google_star_rating']:
        coverage.append({'feature':column,'documented_stores':int(feat[column].ne('').sum()),
                         'independent_stores':len(feat),'included_in_pilot':int(column in ['own_website_external','menu_family_external'])})
    pd.DataFrame(coverage).to_csv(OUT / 'feature_coverage.csv', index=False, encoding='utf-8-sig')
    return df, primary


def fixed_design(df, prompts):
    # The vocabulary is defined by the prior question plan and external codebook.
    # There is no outcome-based feature selection or learned global encoding.
    names = ['intercept','own_website']
    arrays = [np.ones(len(df)), df.own_website.to_numpy(float)]
    for level in MENU_LEVELS[1:]:
        names.append('menu:' + level)
        arrays.append(df.menu_family_external.eq(level).to_numpy(float))
    for prompt in prompts[1:]:
        names.append('prompt:' + prompt)
        arrays.append(df.prompt_id.eq(prompt).to_numpy(float))
    names.append('backend:codex_vs_agy')
    arrays.append(df.backend.eq('codex').to_numpy(float))
    return np.column_stack(arrays), names


def fit_mixed(df, label, fe_prior=1.0, store_only=False, seed=SEED):
    started = time.monotonic()
    prompts = sorted(df.prompt_id.unique())
    x, names = fixed_design(df, prompts)
    stores = sorted(df.brand_group.unique())
    runs = sorted(df.run_id.unique())
    store_index = {s:i for i,s in enumerate(stores)}
    run_index = {r:i for i,r in enumerate(runs)}
    row_idx = np.arange(len(df))
    columns = np.array([store_index[s] for s in df.brand_group])
    if not store_only:
        columns = np.concatenate([columns, [len(stores)+run_index[r] for r in df.run_id]])
        row_idx = np.concatenate([row_idx,row_idx])
    nvc = len(stores) + (0 if store_only else len(runs))
    z = csr_matrix((np.ones(len(row_idx)), (row_idx,columns)), shape=(len(df),nvc))
    ident = np.concatenate([np.zeros(len(stores),dtype=int),
                            np.ones(0 if store_only else len(runs),dtype=int)])
    vc_names = ['store:'+s for s in stores] + ([] if store_only else ['run:'+r for r in runs])
    model = BinomialBayesMixedGLM(df.y.to_numpy(), x, z, ident, fe_p=fe_prior,
              vcp_p=.5, fep_names=names, vcp_names=['store_sd'] + ([] if store_only else ['run_sd']), vc_names=vc_names)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = model.fit_vb(minim_opts={'maxiter':1500,'gtol':1e-5}, rng=np.random.default_rng(seed))
    opt = result.optim_retvals
    grad = float(np.max(np.abs(opt.get('jac', np.array([np.inf])))))
    assert np.isfinite(result.fe_mean).all() and np.isfinite(result.fe_sd).all()
    assert (result.fe_sd > 0).all()
    diagnostic = {'model':label,'rows':len(df),'independent_stores':len(stores),'response_clusters':len(runs),
        'fe_prior_sd':fe_prior,'vc_logsd_prior_sd':.5,'optimizer_success':bool(opt.get('success',False)),
        'optimizer_message':str(opt.get('message','')),'max_abs_gradient':grad,
        'warnings':[str(w.message) for w in caught],'elapsed_seconds':round(time.monotonic()-started,2),
        'store_sd_posterior_geometric_mean':float(np.exp(result.vcp_mean[0])),
        'run_sd_posterior_geometric_mean':float(np.exp(result.vcp_mean[1])) if not store_only else 0}
    emit({'fit':label,'success':diagnostic['optimizer_success'],'gradient':grad,'seconds':diagnostic['elapsed_seconds']})
    if not diagnostic['optimizer_success'] and grad > 1e-3:
        raise RuntimeError(f'Unreliable optimization: {diagnostic}')
    return {'model':model,'result':result,'prompts':prompts,'stores':store_index,
            'store_only':store_only,'diagnostic':diagnostic}


def effect_rows(fit, label):
    result=fit['result']
    return [{'model':label,'term':term,'log_odds_mean':float(mu),'posterior_sd_approx':float(sd),
             'odds_ratio':float(np.exp(mu)),'credible95_low_approx':float(np.exp(mu-1.96*sd)),
             'credible95_high_approx':float(np.exp(mu+1.96*sd)),
             'interval_excludes_one_approx':int(mu-1.96*sd>0 or mu+1.96*sd<0),
             'interpretation':'mean-field VB approximate posterior; association, not causal effect'}
            for term,mu,sd in zip(fit['model'].fep_names,result.fe_mean,result.fe_sd)]


def predict_mixed(fit, df, known_stores=False):
    x,_=fixed_design(df,fit['prompts'])
    result=fit['result']
    eta=x @ result.fe_mean
    variances=np.zeros(len(df))
    sigma2=np.exp(2*result.vcp_mean)
    for i, group in enumerate(df.brand_group):
        if known_stores and group in fit['stores']:
            eta[i]+=result.vc_mean[fit['stores'][group]]
        else:
            variances[i]+=sigma2[0]
    if not fit['store_only']: variances+=sigma2[1]
    # New store/response effects are integrated, never read from test labels.
    nodes,weights=np.polynomial.hermite.hermgauss(30)
    return np.sum(expit(eta[:,None] + np.sqrt(2*variances[:,None])*nodes) * weights,axis=1)/np.sqrt(np.pi)


def feature_pipeline(kind):
    encoder=ColumnTransformer([('numeric','passthrough',['own_website']),
        ('category',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['menu_family_external','prompt_id','backend'])])
    if kind=='logistic_l2':
        estimator=LogisticRegression(C=.1,max_iter=2000,random_state=SEED)
    else:
        estimator=XGBClassifier(n_estimators=120,max_depth=2,learning_rate=.03,min_child_weight=5,
             reg_lambda=10,subsample=.8,colsample_bytree=.8,objective='binary:logistic',
             eval_metric='logloss',n_jobs=2,tree_method='hist',random_state=SEED)
    return Pipeline([('encode',encoder),('model',estimator)])


def fit_ebm(df):
    model=ExplainableBoostingClassifier(feature_names=MODEL_COLUMNS,
        feature_types=['continuous','nominal','nominal','nominal'],interactions=0,
        max_bins=16,outer_bags=1,validation_size=0,early_stopping_rounds=0,
        max_rounds=1000,learning_rate=.03,min_samples_leaf=20,n_jobs=2,random_state=SEED)
    model.fit(df[MODEL_COLUMNS],df.y)
    return model


def score(y,p):
    p=np.clip(p,1e-7,1-1e-7)
    return {'brier':float(brier_score_loss(y,p)),'log_loss':float(log_loss(y,p)),
            'pr_auc_average_precision':float(average_precision_score(y,p)),
            'roc_auc':float(roc_auc_score(y,p)) if len(np.unique(y))>1 else None}


def benchmark(primary):
    models=['context_mean','logistic_l2','mixed_logistic','ebm_main_effects','xgboost_shallow']
    preds={m:np.empty(len(primary)) for m in models}
    fold_ids=np.zeros(len(primary),dtype=int)
    diagnostics=[]
    splits=[]
    for fold,(tr,te) in enumerate(GroupKFold(n_splits=5).split(primary,primary.y,primary.brand_group)):
        train,test=primary.iloc[tr],primary.iloc[te]
        assert not set(train.brand_group)&set(test.brand_group)
        fold_ids[te]=fold
        means=train.groupby(['prompt_id','backend']).y.mean().to_dict()
        preds['context_mean'][te]=[means.get((p,b),train.y.mean()) for p,b in zip(test.prompt_id,test.backend)]
        for kind in ['logistic_l2','xgboost_shallow']:
            pipe=feature_pipeline(kind)
            pipe.fit(train[MODEL_COLUMNS],train.y)
            preds[kind][te]=pipe.predict_proba(test[MODEL_COLUMNS])[:,1]
        ebm=fit_ebm(train)
        preds['ebm_main_effects'][te]=ebm.predict_proba(test[MODEL_COLUMNS])[:,1]
        mixed=fit_mixed(train,f'cv_fold_{fold}')
        diagnostics.append(mixed['diagnostic'])
        preds['mixed_logistic'][te]=predict_mixed(mixed,test)
        splits += [{'entity_id':r.entity_id,'brand_group':r.brand_group,'fold':fold}
                   for r in test[['entity_id','brand_group']].drop_duplicates().itertuples(index=False)]
        emit({'cross_validation_fold_completed':fold,'held_out_stores':test.entity_id.nunique()})
    pd.DataFrame(splits).to_csv(OUT/'cv_store_folds.csv',index=False,encoding='utf-8-sig')
    output=primary[['run_id','entity_id','name_ko','brand_group','backend','area','y']].copy()
    output['fold']=fold_ids
    for m,p in preds.items():
        assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
        output[m]=p
    output.to_csv(OUT/'oof_predictions.csv',index=False,encoding='utf-8-sig')
    rng=np.random.default_rng(SEED)
    brands=sorted(primary.brand_group.unique())
    sampled=rng.integers(0,len(brands),(5000,len(brands)))
    baseline_losses=np.array([np.mean((primary.loc[primary.brand_group.eq(g),'y'].to_numpy()-preds['context_mean'][primary.brand_group.eq(g)])**2) for g in brands])
    scores=[]
    for m,p in preds.items():
        metrics=score(primary.y.to_numpy(),p)
        losses=np.array([np.mean((primary.loc[primary.brand_group.eq(g),'y'].to_numpy()-p[primary.brand_group.eq(g)])**2) for g in brands])
        ci=np.quantile(losses[sampled].mean(axis=1),[.025,.975])
        delta_ci=np.quantile((losses-baseline_losses)[sampled].mean(axis=1),[.025,.975])
        scores.append({'model':m,**metrics,'brier_bootstrap95_low':float(ci[0]),'brier_bootstrap95_high':float(ci[1]),
                      'brier_minus_context':float(np.mean(losses-baseline_losses)),
                      'paired_difference95_low':float(delta_ci[0]),'paired_difference95_high':float(delta_ci[1]),
                      'independent_stores':len(brands),'evaluation_rows':len(primary),
                      'split':'GroupKFold5 held-out restaurants','interval':'fixed OOF predictions, restaurant cluster bootstrap; exploratory'})
    pd.DataFrame(scores).sort_values('brier').to_csv(OUT/'model_comparison.csv',index=False,encoding='utf-8-sig')
    return scores,diagnostics


def phase_validation(primary):
    train=primary[primary.phase.eq('baseline')]
    test=primary[primary.phase.eq('prospective')].copy()
    fit=fit_mixed(train,'phase_train_repeats1to5')
    group_rates=train.groupby(['entity_id','backend']).y.agg(['sum','count'])
    prior=float(train.y.mean())
    test['history_shrinkage']=[(group_rates.loc[(e,b),'sum']+5*prior)/(group_rates.loc[(e,b),'count']+5)
                                for e,b in zip(test.entity_id,test.backend)]
    test['mixed_known_store']=predict_mixed(fit,test,known_stores=True)
    test['mixed_features_only']=predict_mixed(fit,test)
    test[['run_id','entity_id','backend','y','history_shrinkage','mixed_known_store','mixed_features_only']].to_csv(
        OUT/'phase_holdout_predictions.csv',index=False,encoding='utf-8-sig')
    scores=[{'model':m,**score(test.y.to_numpy(),test[m].to_numpy()),'stores':test.entity_id.nunique(),
             'train_rows':len(train),'test_rows':len(test),'interpretation':'same-day measurement batches, not new-date causal validation'}
            for m in ['history_shrinkage','mixed_known_store','mixed_features_only']]
    pd.DataFrame(scores).to_csv(OUT/'phase_holdout_scores.csv',index=False,encoding='utf-8-sig')
    return scores,fit['diagnostic']


def main():
    hashes={n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in INPUTS}
    all_data,primary=prepare_data()
    specs=[('primary_general',primary,1,False),('prior_sd2',primary,2,False),
           ('store_intercept_only',primary,1,True),
           ('legacy_reference_only',primary[primary.identity_status.eq('legacy_source_checked_not_current')],1,False),
           ('secondary_all_queries',all_data,1,False)]
    effects=[]; diagnostics=[]; fits={}
    for label,df,prior,store_only in specs:
        fit=fit_mixed(df,label,prior,store_only)
        effects+=effect_rows(fit,label)
        diagnostics.append(fit['diagnostic']);fits[label]=fit
    pd.DataFrame(effects).to_csv(OUT/'effect_estimates.csv',index=False,encoding='utf-8-sig')
    # One alternate start checks that this optimizer result is not seed-dependent.
    refit=fit_mixed(primary,'primary_alternate_start',seed=SEED+1)
    max_delta=float(np.max(np.abs(refit['result'].fe_mean-fits['primary_general']['result'].fe_mean)))
    assert max_delta<.01, max_delta
    diagnostics.append(refit['diagnostic'])
    comparison,cv_diag=benchmark(primary)
    phase_scores,phase_diag=phase_validation(primary)
    diagnostics+=cv_diag+[phase_diag]
    # Full-data EBM terms explain this pilot fit; held-out scores remain separate.
    ebm=fit_ebm(primary)
    term_rows=[]
    for term,name in enumerate(ebm.term_names_):
        grid=ebm.bins_[term][0]
        if isinstance(grid,dict):
            labels={idx:str(cat) for cat,idx in grid.items()}
        else:
            labels={i:str(cut) for i,cut in enumerate(grid,start=1)}
        for i,value in enumerate(ebm.term_scores_[term]):
            term_rows.append({'term':name,'bin_index':i,'bin_label':labels.get(i,'missing_or_boundary'),
                              'log_odds_contribution':float(value),'not_causal':1})
    pd.DataFrame(term_rows).to_csv(OUT/'ebm_terms_full_pilot.csv',index=False,encoding='utf-8-sig')
    summary={'created_at_utc':datetime.now(timezone.utc).isoformat(),'primary_stores':30,'primary_rows':len(primary),
             'primary_responses':primary.run_id.nunique(),'all_query_rows':len(all_data),
             'positive_primary_rows':int(primary.y.sum()),'restaurant_predictors':['own_website','menu_family_external'],
             'context_predictors':['prompt_id','backend'],'random_intercepts':['restaurant','response'],
             'feature_dates':'legacy website/menu snapshot and observation-era manual checks; not causal pre-treatment data',
             'input_sha256':hashes,'alternate_start_max_fe_difference':max_delta,'comparison':comparison,
             'phase_scores':phase_scores,'model_training_performed':True,'scope':'exploratory original30 pilot only; not all162',
             'causal_claim':False,'potential_limitations':['small purposively selected sample','legacy identity references',
                 'unmeasured popularity/reviews/price','conditional dependence from recommendation list competition',
                 'mean-field VB intervals can understate uncertainty','random effects assumed independent of covariates']}
    for n,sha in hashes.items():assert hashlib.sha256((BASE/n).read_bytes()).hexdigest()==sha
    packages=['numpy','pandas','scipy','statsmodels','scikit-learn','matplotlib','xgboost','interpret-core']
    environment={p:importlib.metadata.version(p) for p in packages}
    save_json('environment.json',environment)
    (OUT/'requirements-models.txt').write_text('\n'.join(p+'=='+v for p,v in environment.items())+'\n',encoding='utf-8')
    save_json('model_diagnostics.json',diagnostics)
    save_json('summary.json',summary)
    save_json('validation.json',{'passed':True,'primary_rows':len(primary),'independent_stores':30,
        'cv_brand_overlap':0,'input_files_unchanged':True,'all_predictions_finite':True,
        'alternate_start_fe_difference':max_delta,'feature_leakage_allowlist':MODEL_COLUMNS,
        'pipeline_training_folds_only':True,'model_training_performed':True,'causal_validation':False})
    emit({'completed':True,'directory':str(OUT),'comparison':comparison})


if __name__=='__main__':
    with threadpool_limits(limits=2):main()
