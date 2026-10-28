"""Future grouped validation scaffold. Default: readiness check, no model training.

Run only after independent feature collection and entity review. The practical
sample/coverage guards are workflow settings, not statistical power guarantees.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from collections import Counter
from prepare import ROOT, load_csv, save_csv


def readiness(cohort="original", min_stores=50):
    cfg = json.loads((ROOT / "model_config.json").read_text(encoding="utf-8"))
    rows = load_csv(ROOT / "model_table_prospective.csv")
    # Discovery entities need an explicit external name/branch review record.
    reviewed = {r["entity_id"] for r in load_csv(ROOT / "verified_entities.csv")
                if r.get("identity_reference_checked") == "1" and r.get("source_url")}
    rows = [r for r in rows if r["general_runs"] and int(r["general_runs"]) > 0
            and (r["sampling_cohort"] == "original30_preselected"
                 or cohort == "reviewed-expanded" and r["entity_id"] in reviewed)]
    by_store = {r["entity_id"]: r for r in rows}
    n = len(by_store)
    numeric = [c for c in cfg["numeric_predictors"]
               if n and sum(r.get(c, "") != "" for r in by_store.values()) / n >= .8
               and len({r[c] for r in by_store.values() if r.get(c, "") != ""}) > 1]
    categorical = [c for c in cfg["categorical_predictors"]
                   if n and sum(r.get(c, "") != "" for r in by_store.values()) / n >= .8]
    if len({r.get("category_external", "") for r in by_store.values()} - {""}) > n / 2:
        # Fine menu descriptions can become identifiers in a tiny dataset.
        categorical = [c for c in categorical if c != "category_external"]
    substantive = [c for c in numeric + categorical if c != "area"]
    dependencies = {m: importlib.util.find_spec(m) is not None for m in ("numpy", "pandas", "sklearn", "xgboost", "shap")}
    reasons = []
    if n < min_stores: reasons.append(f"Only {n} independent restaurants; workflow guard is {min_stores}.")
    if len(substantive) < 3: reasons.append("Fewer than 3 varying external restaurant features reach 80% coverage; collect features first.")
    if any(int(r["general_runs"]) < 5 for r in rows): reasons.append("Prospective general-question repeats are incomplete.")
    if not all(dependencies[m] for m in ("numpy", "pandas", "sklearn", "xgboost")): reasons.append("Training runtime dependencies are unavailable.")
    report = {"cohort": cohort, "independent_restaurants": n, "restaurant_backend_rows": len(rows),
              "rows_are_not_independent_stores": True, "min_stores_workflow_setting": min_stores,
              "usable_numeric_80pct_coverage": numeric, "usable_categorical_80pct_coverage": categorical,
              "dependencies": dependencies, "ready_for_exploratory_training": not reasons,
              "blocking_reasons": reasons, "model_training_performed": False,
              "interpretation": "Prediction associations only; neither SHAP nor importance establishes causality."}
    report['readiness_scope'] = 'Original 162-candidate broad-feature pipeline; separate completed pilots below'
    if (ROOT / '혼합효과분석' / '결과_요약.md').exists():
        report['completed_pilot'] = {'restaurant_count': 30, 'restaurant_predictor_count': 2,
            'model_training_performed': True, 'report_path': str(ROOT / '혼합효과분석' / '결과_요약.md')}
    enriched = ROOT / '외부특징분석'
    if (enriched / 'report_validation.json').exists():
        verified = json.loads((enriched / 'report_validation.json').read_text(encoding='utf-8'))
        estimates = load_csv(enriched / 'model_comparison.csv')
        review_glmm = next(r for r in estimates if r['model'] == 'reviews_mixed_logistic')
        report['completed_external_feature_pilot'] = {'restaurant_count': verified['independent_stores'],
            'collected_profiles': verified['profile_features_collected'], 'restaurant_predictor_count_full': 8,
            'model_training_performed': True, 'review_glmm_brier': float(review_glmm['brier']),
            'causal_validation': False, 'report_path': str(enriched / '결과_요약.md')}
    (ROOT / "model_readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, rows, numeric, categorical


def train(rows, numeric, categorical):
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold
    from xgboost import XGBRegressor

    frame = pd.DataFrame(rows)
    for c in numeric: frame[c] = pd.to_numeric(frame[c], errors="coerce")
    for c in categorical: frame[c] = frame[c].replace("", np.nan)
    columns = numeric + categorical + ["backend"]
    assert not set(columns) & {"entity_id", "name_ko", "appearance_count", "brand_group", "sampling_cohort"}
    x = frame[columns]
    y = frame["general_appearance_rate"].astype(float).to_numpy()
    weights = frame["general_runs"].astype(float).to_numpy()
    groups = frame["brand_group"].to_numpy()
    predictions = {name: np.empty(len(y)) for name in ("training_mean", "ridge", "xgboost")}
    folds = np.empty(len(y), dtype=int)
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=5).split(x, y, groups)):
        assert not set(groups[tr]) & set(groups[te])
        folds[te] = fold
        predictions["training_mean"][te] = np.average(y[tr], weights=weights[tr])
        for name in ("ridge", "xgboost"):
            # Both encoding and imputation fit only on this training fold.
            transforms = []
            if numeric:
                num = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                                ("scale", StandardScaler())]) if name == "ridge" else "passthrough"
                transforms.append(("numeric", num, numeric))
            cat = Pipeline([("missing", SimpleImputer(strategy="constant", fill_value="unknown")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
            transforms.append(("category", cat, categorical + ["backend"]))
            estimator = Ridge(alpha=10) if name == "ridge" else XGBRegressor(
                objective="reg:squarederror", n_estimators=150, max_depth=2,
                learning_rate=.03, min_child_weight=5, subsample=.8,
                colsample_bytree=.8, reg_lambda=10, random_state=20261013,
                n_jobs=2, tree_method="hist")
            pipe = Pipeline([("preprocess", ColumnTransformer(transforms)), ("model", estimator)])
            pipe.fit(x.iloc[tr], y[tr], model__sample_weight=weights[tr])
            predictions[name][te] = np.clip(pipe.predict(x.iloc[te]), 0, 1)
    scores = []
    for name, pred in predictions.items():
        for backend in ("all", "codex", "agy"):
            mask = np.ones(len(y), dtype=bool) if backend == "all" else frame["backend"].to_numpy() == backend
            # Each restaurant/backend row contributes once, not once per repeat.
            scores.append({"model": name, "backend": backend,
                           "mae": float(np.mean(np.abs(pred[mask]-y[mask]))),
                           "rmse": float(np.sqrt(np.mean((pred[mask]-y[mask])**2))),
                           "rows": int(mask.sum()), "split": "held_out_restaurant_GroupKFold5"})
    save_csv("future_training_scores.csv", scores)
    save_csv("future_oof_predictions.csv", [{"entity_id": r["entity_id"], "backend": r["backend"],
             "fold": int(folds[i]), "observed_general_rate": y[i],
             **{name: values[i] for name, values in predictions.items()}} for i, r in enumerate(rows)])
    # Interpretation comes after held-out performance and fold stability checks.
    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Explicitly fit models after readiness passes")
    parser.add_argument("--cohort", choices=["original", "reviewed-expanded"], default="original")
    parser.add_argument("--min-stores", type=int, default=50)
    args = parser.parse_args()
    report, rows, numeric, categorical = readiness(args.cohort, args.min_stores)
    print(json.dumps(report, ensure_ascii=False))
    if args.run:
        if not report["ready_for_exploratory_training"]: raise SystemExit("NOT_TRAINED: complete the recorded readiness items first.")
        scores = train(rows, numeric, categorical)
        report["model_training_performed"] = True
        report["evaluation"] = scores
        (ROOT / "model_readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(scores, ensure_ascii=False))
