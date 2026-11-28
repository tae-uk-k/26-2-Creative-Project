"""Validate real study artifacts, including failure exclusion and consumer isolation."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from prepare import ROOT, STUDY, completed_runs, freeze_registry, load_csv, normalize


def validate(require_complete=False):
    live_runs, attempts = completed_runs()
    snapshot_ids = {r["run_id"] for r in load_csv(ROOT / "runs_clean.csv")}
    runs = [r for r in live_runs if r["run_id"] in snapshot_ids]
    assert len(runs) == len(snapshot_ids), "CSV snapshot contains an unknown/incomplete response"
    registry = freeze_registry()
    trials = load_csv(ROOT / "exposure_trials.csv")
    recs = load_csv(ROOT / "recommendations_clean.csv")
    folds = load_csv(ROOT / "group_folds.csv")
    features = load_csv(ROOT / "restaurant_features.csv")
    by_cell = Counter((r["backend"], r["prompt_id"]) for r in runs)
    assert len({r["run_id"] for r in runs}) == len(runs)
    assert len(recs) == len(runs) * 5
    assert all(r["status"] == "success" and r["web_search_observed"] for r in runs)
    assert all(sorted(int(x["rank"]) for x in r["recommendations"]) == [1,2,3,4,5] for r in runs)
    assert all(Path(r["raw_path"]).is_file() for r in runs)
    assert len({(r["run_id"], r["entity_id"]) for r in trials}) == len(trials)
    area_counts = Counter(r["area"] for r in registry)
    assert len(trials) == sum(area_counts[r["area"]] for r in runs)
    assert all(r["eligible_for_feature_analysis"] == "0" for r in trials
               if r["sampling_cohort"] != "original30_preselected" and r["phase"] == "baseline")
    assert all(float(r["appearance_rate"]) >= 0 and float(r["appearance_rate"]) <= 1
               for r in load_csv(ROOT / "store_outcomes.csv"))
    group_folds = defaultdict(set)
    for r in folds: group_folds[r["brand_group"]].add(r["group_fold_5"])
    assert all(len(v) == 1 for v in group_folds.values())
    evidence = load_csv(STUDY / "feature_checks.csv") + load_csv(ROOT / "verified_features.csv")
    documented = {(r["restaurant_id"], r["feature"]) for r in evidence if r.get("source_url") and r.get("value") != ""}
    for r in features:
        for key in ("google_review_count", "naver_review_count", "google_star_rating", "photo_count"):
            if (r["entity_id"], key) not in documented:
                assert r[key] == "", (r["entity_id"], key)
            elif r[key] != "":
                assert float(r[key]) >= 0
    frame = json.loads((ROOT / "frame_freeze.json").read_text(encoding="utf-8"))
    frame_unchanged = hashlib.sha256((ROOT / "restaurant_registry.csv").read_bytes()).hexdigest() == frame["registry_sha256"]
    assert frame_unchanged
    assert all(r["started_at_utc"] >= frame["created_at_utc"] for r in runs if r["repeat"] > 5)
    expected_consumer = {
        "consumer_results.csv": "149F1BB971981F3D5F5AEC50A5F6AE466D44593C16AF790058D1CC0EA9CFBDC3",
        "consumer_failures.csv": "E2024BBD9096D269A455E38A170091AAEFBA7C998280C205D86B887411ECD80E"}
    consumer_checks = {name: hashlib.sha256((STUDY.parent / "data" / name).read_bytes()).hexdigest().upper() == sha
                       for name, sha in expected_consumer.items()}
    assert all(consumer_checks.values())
    unmatched = sum(not r["entity_id"] for r in recs)
    config = json.loads((ROOT / "model_config.json").read_text(encoding="utf-8"))
    assert not set(config["numeric_predictors"] + config["categorical_predictors"]) & set(config["forbidden_predictors"])
    complete = len(runs) == 240 and len(by_cell) == 24 and set(by_cell.values()) == {10}
    if require_complete: assert complete, dict(by_cell)
    selected_paths = {r["raw_path"] for r in runs}
    report = {"passed": True, "complete_240": complete, "runs": len(runs), "live_completed_runs": len(live_runs),
              "cells": {f"{b}:{p}":n for (b,p),n in sorted(by_cell.items())},
              "candidate_count": len(registry), "trial_rows": len(trials), "recommendation_slots": len(recs),
              "unmatched_slots": unmatched, "frame_sha256_unchanged": frame_unchanged,
              "consumer_files_unchanged": consumer_checks, "brand_groups_cross_fold": 0,
              "uncollected_review_features_still_null": True,
              "failure_attempts_excluded": sum(r["raw_path"] not in selected_paths and r["status"] != "success" for r in attempts),
              "measurement_rows_are_not_independent_restaurants": True,
              "scope": "artifact integrity, not real-world restaurant truth or model training proof"}
    (ROOT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    validate(parser.parse_args().require_complete)
