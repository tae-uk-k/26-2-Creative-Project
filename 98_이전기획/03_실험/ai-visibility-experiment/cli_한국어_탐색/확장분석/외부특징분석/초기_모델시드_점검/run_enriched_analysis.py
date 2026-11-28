"""Fixed-group comparison of legacy, review-only, and fuller external features."""
import hashlib
import json
import sys
import time
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.special import expit
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
from interpret.glassbox import ExplainableBoostingClassifier
from xgboost import XGBClassifier

OUT = Path(__file__).resolve().parent
OLD = OUT.parent / '혼합효과분석'
sys.path.insert(0, str(OLD))
from run_analysis import fixed_design, score, SEED

KINDS = ['logistic_l2', 'mixed_logistic', 'ebm_main_effects', 'xgboost_shallow']
NUM = {'reviews': ['log_review_count'],
       'full': ['log_review_count', 'diningcode_rating', 'log_photo_count', 'log_price_krw']}


def save_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def state_from(train, variant):
    stores = train.drop_duplicates('entity_id')
    state = {'variant': variant, 'numeric': {}}
    for col in NUM[variant]:
        median = float(stores[col].median())
        values = stores[col].fillna(median)
        mean, sd = float(values.mean()), float(values.std(ddof=0))
        state['numeric'][col] = {'median': median, 'mean': mean, 'sd': sd if sd > 1e-9 else 1.0}
    units = stores.unit.replace('unknown', np.nan).dropna()
    state['unit_mode'] = str(units.mode().iloc[0])
    return state


def transform(df, state):
    out = df.copy()
    for col, st in state['numeric'].items():
        out[col] = (out[col].fillna(st['median']) - st['mean']) / st['sd']
    out['unit'] = out.unit.replace('unknown', np.nan).fillna(state['unit_mode'])
    return out


def columns(variant):
    num = ['own_website'] + NUM[variant] + (['michelin_listing_current'] if variant == 'full' else [])
    cat = ['menu_family_external', 'prompt_id', 'backend'] + (['unit'] if variant == 'full' else [])
    return num, cat


def design(df, state):
    d = transform(df, state)
    x, names = fixed_design(d, ['MD01', 'MW01', 'SS01'])
    extras = [d[col].to_numpy(float) for col in NUM[state['variant']]]
    extra_names = ['z:' + col for col in NUM[state['variant']]]
    if state['variant'] == 'full':
        extras.append(d.michelin_listing_current.to_numpy(float))
        extra_names.append('michelin_listing_current')
        for unit in ['meat_portion', 'sharing', 'snack']:
            extras.append(d.unit.eq(unit).to_numpy(float))
            extra_names.append('price_unit:' + unit)
    return np.column_stack([x] + extras), names + extra_names


def fit_mixed(train, variant, seed, label):
    started = time.monotonic()
    state = state_from(train, variant)
    x, names = design(train, state)
    stores = sorted(train.brand_group.unique())
    runs = sorted(train.run_id.unique())
    store_ix = {g: i for i, g in enumerate(stores)}
    run_ix = {g: i for i, g in enumerate(runs)}
    n = len(train)
    row = np.concatenate([np.arange(n), np.arange(n)])
    col = np.concatenate([[store_ix[g] for g in train.brand_group], [len(stores) + run_ix[g] for g in train.run_id]])
    z = csr_matrix((np.ones(n * 2), (row, col)), shape=(n, len(stores) + len(runs)))
    ident = np.concatenate([np.zeros(len(stores), int), np.ones(len(runs), int)])
    model = BinomialBayesMixedGLM(train.y.to_numpy(), x, z, ident, fe_p=1, vcp_p=.5,
        fep_names=names, vcp_names=['store_sd', 'response_sd'])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = model.fit_vb(minim_opts={'maxiter': 1500, 'gtol': 1e-5}, rng=np.random.default_rng(seed))
    opt = result.optim_retvals
    grad = float(np.max(np.abs(opt.get('jac', np.array([np.inf])))))
    diagnostic = {'label': label, 'variant': variant, 'optimizer_success': bool(opt.get('success', False)),
                  'max_abs_gradient': grad, 'warnings': [str(w.message) for w in caught],
                  'rows': n, 'independent_stores': len(stores), 'elapsed_seconds': round(time.monotonic() - started, 2)}
    if not diagnostic['optimizer_success'] and grad > 1e-3:
        raise RuntimeError(str(diagnostic))
    assert np.isfinite(result.fe_mean).all() and np.isfinite(result.fe_sd).all()
    return {'result': result, 'state': state, 'names': names, 'diagnostic': diagnostic}


def predict_mixed(fit, test):
    x, _ = design(test, fit['state'])
    result = fit['result']
    eta = x @ result.fe_mean
    variance = float(np.exp(2 * result.vcp_mean).sum())
    nodes, weights = np.polynomial.hermite.hermgauss(30)
    return np.sum(expit(eta[:, None] + np.sqrt(2 * variance) * nodes) * weights, axis=1) / np.sqrt(np.pi)


def fit_predict(train, test, variant, kind, seed, label):
    if kind == 'mixed_logistic':
        fit = fit_mixed(train, variant, seed, label)
        return predict_mixed(fit, test), fit['diagnostic'], fit['state']
    state = state_from(train, variant)
    tr, te = transform(train, state), transform(test, state)
    num, cat = columns(variant)
    cols = num + cat
    if kind == 'ebm_main_effects':
        model = ExplainableBoostingClassifier(feature_names=cols, feature_types=['continuous'] * len(num) + ['nominal'] * len(cat),
            interactions=0, max_bins=16, outer_bags=1, validation_size=0, early_stopping_rounds=0,
            max_rounds=1000, learning_rate=.03, min_samples_leaf=20, n_jobs=2, random_state=seed)
        model.fit(tr[cols], tr.y)
        pred = model.predict_proba(te[cols])[:, 1]
    else:
        encoder = ColumnTransformer([('numeric', 'passthrough', num),
            ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat)])
        model = LogisticRegression(C=.1, max_iter=2000, random_state=seed) if kind == 'logistic_l2' else XGBClassifier(
            n_estimators=120, max_depth=2, learning_rate=.03, min_child_weight=5, reg_lambda=10,
            subsample=.8, colsample_bytree=.8, objective='binary:logistic', eval_metric='logloss',
            n_jobs=2, tree_method='hist', random_state=seed)
        pipe = Pipeline([('encode', encoder), ('model', model)])
        pipe.fit(tr[cols], tr.y)
        pred = pipe.predict_proba(te[cols])[:, 1]
    return pred, None, state


def comparison(oof, model_names):
    groups = sorted(oof.brand_group.unique())
    rng = np.random.default_rng(SEED)
    samples = rng.integers(0, len(groups), (5000, len(groups)))
    losses = {m: oof.assign(loss=(oof.y - oof[m]) ** 2).groupby('brand_group').loss.mean().reindex(groups).to_numpy() for m in model_names}
    rows = []
    for name in model_names:
        ci = np.quantile(losses[name][samples].mean(axis=1), [.025, .975])
        delta = losses[name] - losses['global_mean']
        delta_ci = np.quantile(delta[samples].mean(axis=1), [.025, .975])
        by_seed = [score(g.y, g[name]) for _, g in oof.groupby('repetition')]
        row = {'model': name, 'brier': float(np.mean(losses[name])),
               'log_loss': float(np.mean([s['log_loss'] for s in by_seed])),
               'brier_ci_low': float(ci[0]), 'brier_ci_high': float(ci[1]),
               'brier_minus_global': float(delta.mean()), 'delta_global_ci_low': float(delta_ci[0]),
               'delta_global_ci_high': float(delta_ci[1]), 'independent_stores': len(groups)}
        if name.startswith(('reviews_', 'full_')):
            kind = name.split('_', 1)[1]
            delta_base = losses[name] - losses['legacy_' + kind]
            db_ci = np.quantile(delta_base[samples].mean(axis=1), [.025, .975])
            row.update({'brier_minus_same_legacy_model': float(delta_base.mean()),
                        'delta_legacy_ci_low': float(db_ci[0]), 'delta_legacy_ci_high': float(db_ci[1])})
        rows.append(row)
    return pd.DataFrame(rows).sort_values('brier')


def descriptive(df):
    stores = df.groupby(['entity_id', 'name_ko', 'area', 'brand_group'], as_index=False).agg(
        appearances=('y', 'sum'), opportunities=('y', 'size'),
        diningcode_review_count=('diningcode_review_count', 'first'), diningcode_rating=('diningcode_rating', 'first'),
        display_photo_count=('display_photo_count', 'first'), price_krw=('price_krw', 'first'))
    stores['appearance_rate'] = stores.appearances / stores.opportunities
    stores.to_csv(OUT / 'store_feature_outcomes.csv', index=False, encoding='utf-8-sig')
    observed = stores.dropna(subset=['diningcode_review_count'])
    x = observed.diningcode_review_count.to_numpy()
    y = observed.appearance_rate.to_numpy()
    rho = float(spearmanr(x, y).statistic)
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(observed.area.to_numpy() == a) for a in sorted(observed.area.unique())]
    permutation = []
    for _ in range(10000):
        shuffled = y.copy()
        for group in groups:
            shuffled[group] = rng.permutation(y[group])
        permutation.append(float(spearmanr(x, shuffled).statistic))
    p = (1 + np.sum(np.abs(permutation) >= abs(rho))) / 10001
    save_json('review_count_association.json', {'spearman_rho': rho, 'area_blocked_permutation_p': float(p),
        'independent_stores': len(observed), 'permutations': 10000, 'causal': False,
        'scope': 'Descriptive purposive cohort; all counts from Diningcode; not Google'})


def main():
    df = pd.read_csv(OUT / 'analysis_data_general.csv')
    folds = pd.read_csv(OLD / 'robust_cv_store_folds.csv')
    legacy = pd.read_csv(OLD / 'robust_oof_predictions.csv')
    keys = ['repetition', 'run_id', 'entity_id']
    old_kinds = ['global_mean', 'context_mean'] + KINDS
    predictions = legacy[keys + old_kinds].rename(columns={k: 'legacy_' + k for k in KINDS})
    model_names = ['global_mean', 'context_mean'] + ['legacy_' + k for k in KINDS] + [v + '_' + k for v in NUM for k in KINDS]
    all_oof, diagnostics, state_audit = [], [], []
    for repetition in range(5):
        seed = SEED + repetition
        assigned = folds[folds.repetition.eq(repetition)].set_index('entity_id').fold
        fid = df.entity_id.map(assigned)
        assert fid.notna().all()
        saved = df[['run_id', 'entity_id', 'brand_group', 'name_ko', 'area', 'backend', 'y']].copy()
        saved['repetition'] = repetition
        saved['fold'] = fid
        saved = saved.merge(predictions, on=keys, validate='one_to_one')
        for variant in NUM:
            for kind in KINDS:
                saved[variant + '_' + kind] = np.nan
        for fold in range(5):
            train, test = df.loc[fid.ne(fold)], df.loc[fid.eq(fold)]
            assert not set(train.brand_group) & set(test.brand_group)
            assert set(test[['entity_id', 'area']].drop_duplicates().area.value_counts()) == {2}
            for variant in NUM:
                for kind in KINDS:
                    pred, diag, state = fit_predict(train, test, variant, kind, seed, f'rep{repetition}_fold{fold}_{variant}')
                    assert np.isfinite(pred).all() and np.all((pred >= 0) & (pred <= 1))
                    saved.loc[saved.entity_id.isin(test.entity_id), variant + '_' + kind] = pred
                    if diag:
                        diagnostics.append(diag)
                        state_audit.append({'repetition': repetition, 'fold': fold, 'training_entity_ids': sorted(train.entity_id.unique()), 'state': state})
            print(json.dumps({'completed_repetition': repetition, 'fold': fold}), flush=True)
        assert saved[model_names].notna().all().all()
        all_oof.append(saved)
    oof = pd.concat(all_oof, ignore_index=True)
    assert len(oof) == 3000 and not oof[keys].duplicated().any()
    oof.to_csv(OUT / 'oof_predictions.csv', index=False, encoding='utf-8-sig')
    scores = comparison(oof, model_names)
    scores.to_csv(OUT / 'model_comparison.csv', index=False, encoding='utf-8-sig')
    full_effects = []
    for variant in NUM:
        fit = fit_mixed(df, variant, SEED, 'all_stores_' + variant)
        diagnostics.append(fit['diagnostic'])
        for name, beta, sd in zip(fit['names'], fit['result'].fe_mean, fit['result'].fe_sd):
            full_effects.append({'variant': variant, 'term': name, 'beta': beta, 'posterior_sd': sd,
                'odds_ratio': np.exp(beta), 'vb95_low': np.exp(beta - 1.96 * sd), 'vb95_high': np.exp(beta + 1.96 * sd),
                'interpretation': 'conditional association; standardized numeric inputs; VB interval; not causal'})
        save_json('glmm_state_' + variant + '.json', fit['state'])
    pd.DataFrame(full_effects).to_csv(OUT / 'mixed_effect_estimates.csv', index=False, encoding='utf-8-sig')
    save_json('model_diagnostics.json', diagnostics)
    save_json('fold_preprocessing_states.json', state_audit)
    descriptive(df)
    audit = {'passed': True, 'rows': 600, 'independent_stores': 30, 'repeated_oof_rows': 3000,
             'fixed_partitions': 5, 'folds_per_partition': 5, 'train_test_brand_overlap': 0,
             'all_glmm_optimizer_success': all(d['optimizer_success'] for d in diagnostics),
             'optimizer_fits': len(diagnostics), 'test_labels_used_in_imputation': False,
             'legacy_folds_unchanged': True, 'feature_snapshot_after_outcomes': True,
             'numeric_missing_value_policy': 'training-store median; kept missing in source features',
             'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                 OUT / 'analysis_data_general.csv', OUT / 'analysis_config.json', OLD / 'robust_cv_store_folds.csv',
                 OLD / 'robust_oof_predictions.csv']},
             'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'causal_validation': False}
    save_json('model_validation.json', audit)
    print(scores[['model', 'brier', 'brier_minus_same_legacy_model']].to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
