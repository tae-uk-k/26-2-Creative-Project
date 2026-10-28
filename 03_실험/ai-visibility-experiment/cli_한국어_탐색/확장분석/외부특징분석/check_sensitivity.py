"""Complete-profile and identity sensitivity, plus restaurant resampling."""
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from run_enriched_analysis import OUT, OLD, SEED, fit_mixed, fit_predict, save_json
from run_analysis import feature_pipeline, fit_mixed as fit_legacy_mixed, predict_mixed as predict_legacy_mixed, score


def sensitivity(df):
    folds = pd.read_csv(OLD / 'robust_cv_store_folds.csv')
    results, diagnostics, effects = [], [], []
    subsets = {'complete_profiles_28': df.log_review_count.notna(),
               'identity_checked_26': df.log_review_count.notna() & df.identity_sensitivity_exclude.eq(0)}
    methods = ['global_mean', 'legacy_logistic_l2', 'legacy_mixed_logistic', 'reviews_logistic_l2', 'reviews_mixed_logistic',
               'full_logistic_l2', 'full_mixed_logistic', 'reviews_xgboost_shallow', 'full_xgboost_shallow']
    for subset, mask in subsets.items():
        d = df.loc[mask].copy()
        fit = fit_mixed(d, 'reviews', SEED, subset + '_effect')
        diagnostics.append(fit['diagnostic'])
        pos = fit['names'].index('z:log_review_count')
        beta, sd = float(fit['result'].fe_mean[pos]), float(fit['result'].fe_sd[pos])
        rho = float(spearmanr(d.groupby('entity_id').diningcode_review_count.first(), d.groupby('entity_id').y.mean()).statistic)
        effects.append({'subset': subset, 'independent_stores': d.entity_id.nunique(), 'review_log_sd': fit['state']['numeric']['log_review_count']['sd'],
                       'review_beta_standardized': beta, 'review_odds_ratio': np.exp(beta),
                       'vb95_low': np.exp(beta - 1.96 * sd), 'vb95_high': np.exp(beta + 1.96 * sd), 'spearman_rho': rho})
        for repetition in range(5):
            mapping = folds[folds.repetition.eq(repetition)].set_index('entity_id').fold
            ids = d.entity_id.map(mapping)
            predictions = {m: np.empty(len(d)) for m in methods}
            for fold in range(5):
                tri, tei = np.flatnonzero(ids.to_numpy() != fold), np.flatnonzero(ids.to_numpy() == fold)
                train, test = d.iloc[tri], d.iloc[tei]
                assert not set(train.brand_group) & set(test.brand_group)
                predictions['global_mean'][tei] = train.y.mean()
                pipe = feature_pipeline('logistic_l2')
                oldcols = ['own_website', 'menu_family_external', 'prompt_id', 'backend']
                pipe.fit(train[oldcols], train.y)
                predictions['legacy_logistic_l2'][tei] = pipe.predict_proba(test[oldcols])[:, 1]
                old = fit_legacy_mixed(train, subset + f'_legacy_{repetition}_{fold}', seed=SEED + repetition)
                predictions['legacy_mixed_logistic'][tei] = predict_legacy_mixed(old, test)
                diagnostics.append(old['diagnostic'])
                for variant in ['reviews', 'full']:
                    for kind in ['logistic_l2', 'mixed_logistic', 'xgboost_shallow']:
                        pred, diag, _ = fit_predict(train, test, variant, kind, SEED + repetition, subset + f'_{repetition}_{fold}_{variant}')
                        predictions[variant + '_' + kind][tei] = pred
                        if diag:
                            diagnostics.append(diag)
            for method, pred in predictions.items():
                results.append({'subset': subset, 'repetition': repetition, 'model': method,
                                'independent_stores': d.entity_id.nunique(), 'rows': len(d), **score(d.y, pred)})
            print(json.dumps({'sensitivity': subset, 'repetition': repetition}), flush=True)
    table = pd.DataFrame(results)
    table.to_csv(OUT / 'sensitivity_by_seed.csv', index=False, encoding='utf-8-sig')
    table.groupby(['subset', 'model', 'independent_stores', 'rows'], as_index=False).agg(
        brier=('brier', 'mean'), brier_seed_sd=('brier', 'std'), log_loss=('log_loss', 'mean')).to_csv(
        OUT / 'sensitivity_model_comparison.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(effects).to_csv(OUT / 'sensitivity_review_effects.csv', index=False, encoding='utf-8-sig')
    save_json('sensitivity_diagnostics.json', diagnostics)


def bootstrap(df):
    rng = np.random.default_rng(SEED)
    stores = df[['entity_id', 'area']].drop_duplicates()
    groups = {e: g for e, g in df.groupby('entity_id')}
    rows, draws, diagnostics = [], [], []
    for replication in range(200):
        parts = []
        for area, items in stores.groupby('area'):
            chosen = rng.choice(items.entity_id.to_numpy(), len(items), replace=True)
            for index, entity_id in enumerate(chosen):
                copy = groups[entity_id].copy()
                label = f'boot_{area}_{index}'
                copy['entity_id'] = label
                copy['brand_group'] = label
                parts.append(copy)
                draws.append({'replication': replication, 'bootstrap_group': label, 'original_entity_id': entity_id})
        sampled = pd.concat(parts, ignore_index=True)
        fit = fit_mixed(sampled, 'reviews', SEED + replication, f'bootstrap_reviews_{replication}')
        diagnostics.append(fit['diagnostic'])
        pos = fit['names'].index('z:log_review_count')
        beta = float(fit['result'].fe_mean[pos])
        raw_sd = fit['state']['numeric']['log_review_count']['sd']
        raw_beta = beta / raw_sd
        rows.append({'replication': replication, 'beta_per_natural_log1p_unit': raw_beta,
                     'or_per_doubling_of_review_count_plus_one': np.exp(raw_beta * np.log(2)),
                     'optimizer_success': fit['diagnostic']['optimizer_success']})
        if replication % 25 == 24:
            print(json.dumps({'bootstrap_completed': replication + 1}), flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(OUT / 'review_effect_bootstrap.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(draws).to_csv(OUT / 'bootstrap_store_draws.csv', index=False, encoding='utf-8-sig')
    values = table.or_per_doubling_of_review_count_plus_one
    save_json('bootstrap_summary.json', {'resamples': len(table), 'independent_stores': 30,
        'all_optimizer_success': all(d['optimizer_success'] for d in diagnostics),
        'or_doubling_median': float(values.median()), 'or_doubling_percentile95': values.quantile([.025, .975]).tolist(),
        'resampling': 'stores within area; duplicated stores get fresh IDs; whole response repeats preserved',
        'scope': 'sampling sensitivity in a purposive cohort, not population or causal confidence'})
    save_json('bootstrap_diagnostics.json', diagnostics)


if __name__ == '__main__':
    data = pd.read_csv(OUT / 'analysis_data_general.csv')
    sensitivity(data)
    bootstrap(data)
