"""Reproducible exposure data preparation. Missing evidence never becomes zero.

Candidate frame is frozen using baseline repeats 1..5 before repeat 6..10.
Original 30-store cohort and outcome-selected discovery cohort stay identifiable.
This script does not treat model-written recommendation reasons as store features.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
import sys

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
sys.path.insert(0, str(STUDY))
from summarize import ADDRESS_SIGNATURES, reviewed_response

AREA_NAMES = {"myeongdong": "명동", "seongsu": "성수", "mangwon": "망원"}
INTENTS = {"01": "general", "02": "budget", "03": "traditional_or_distinctive", "04": "solo_or_seated"}
ALIASES = {
    ("myeongdong", "영양센타"): "영양센터",
    ("myeongdong", "명동영양센터"): "영양센터",
    ("seongsu", "계월"): "계월곰탕",
    ("mangwon", "망원동 홍두깨손칼국수"): "홍두깨손칼국수",
}


def normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", str(value or "")).lower())


def brand_group(name: str) -> str:
    """Keep documented branch suffixes out of restaurant split groups."""
    return re.sub(r"(명동본점|망원본점|성수본점|성수직영점|서울숲점|성수점|명동점|망원시장점|망원점|본점)$", "", normalize(name))


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_csv(name: str, rows: list[dict], fields: list[str] | None = None) -> None:
    with (ROOT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]) if rows else fields or [])
        writer.writeheader()
        writer.writerows(rows)


def baseline() -> list[dict]:
    return [json.loads(line) for line in (ROOT / "baseline_runs_120.jsonl").read_text(encoding="utf-8").splitlines()]


def original_sample() -> list[dict]:
    return load_csv(STUDY.parent / "restaurants.csv")


def alias_index(registry: list[dict]) -> dict:
    index = defaultdict(set)
    for row in registry:
        for alias in [row["name_ko"]] + row["aliases"].split("|"):
            if normalize(alias):
                index[row["area"], normalize(alias)].add(row["entity_id"])
    return index


def match(rec: dict, area: str, registry: list[dict], index: dict) -> str:
    name = ALIASES.get((area, str(rec.get("name", ""))), str(rec.get("name", "")))
    name_key = normalize(name)
    ids = index.get((area, name_key), set())
    if len(ids) == 1:
        return next(iter(ids))
    ids = set()
    for row in registry:
        if row["area"] != area:
            continue
        for alias in [row["name_ko"]] + row["aliases"].split("|"):
            a = normalize(alias)
            if len(a) >= 3 and name_key.startswith(a) and name_key[len(a):] in ("본점", "성수점", "명동점", "망원점", "망원본점", "명동본점", "서울숲점"):
                ids.add(row["entity_id"])
    return next(iter(ids)) if len(ids) == 1 else ""


def freeze_registry() -> list[dict]:
    target = ROOT / "restaurant_registry.csv"
    if target.exists():
        return load_csv(target)
    registry = []
    for row in original_sample():
        short = re.sub(r"(명동본점|망원본점|성수본점|성수직영점|서울숲점|성수점|명동점|망원시장점|망원점|본점)$", "", brand_group(row["name_ko"]))
        aliases = [row["canonical_name_en"], short] + row["aliases"].split("|")
        if row["restaurant_id"] == "MW-R04":
            aliases.append("훈훈호떡")
        registry.append({"entity_id": row["restaurant_id"], "name_ko": row["name_ko"], "area": row["area"], "aliases": "|".join(dict.fromkeys(aliases)), "sampling_cohort": "original30_preselected", "selection_uses_outcome": 0, "identity_status": "legacy_source_checked_not_current" if row["verification_status"] == "verified_online" else "needs_identity_review", "address_reference": row["address_en"], "address_signature_ko": ADDRESS_SIGNATURES.get(row["restaurant_id"], ""), "source_urls": row["verification_urls"], "category_prior_external": row["category"], "own_website_prior_external": row["own_website"], "frame_frozen_at_utc": datetime.now(timezone.utc).isoformat()})
    for run in baseline():
        for rec in run["recommendations"]:
            idx = alias_index(registry)
            if match(rec, run["area"], registry, idx):
                continue
            name = ALIASES.get((run["area"], rec["name"]), rec["name"])
            key = run["area"] + ":" + normalize(name)
            rid = "DISC-" + hashlib.sha256(key.encode()).hexdigest()[:10]
            if any(row["entity_id"] == rid for row in registry):
                continue
            registry.append({"entity_id": rid, "name_ko": name, "area": run["area"], "aliases": rec["name"], "sampling_cohort": "baseline_discovery_prospective_only", "selection_uses_outcome": 1, "identity_status": "model_candidate_unverified", "address_reference": rec.get("address") or "", "address_signature_ko": "", "source_urls": "|".join(rec.get("sources") or []), "category_prior_external": "", "own_website_prior_external": "", "frame_frozen_at_utc": datetime.now(timezone.utc).isoformat()})
    save_csv("restaurant_registry.csv", registry)
    (ROOT / "frame_freeze.json").write_text(json.dumps({"created_at_utc": datetime.now(timezone.utc).isoformat(), "baseline_run_count": 120, "original_store_count": 30, "registry_count": len(registry), "registry_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "new_cohort_analysis_period": "repeat_6_to_10_only", "selection_warning": "Discovery candidates were selected from baseline recommendations; not a random population sample."}, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry


def completed_runs() -> tuple[list[dict], list[dict]]:
    baseline_rows = [reviewed_response(row) for row in baseline()]
    chosen = {r["run_id"]: r for r in baseline_rows}
    attempts = []
    for backend in ("codex", "agy"):
        for line in (STUDY / f"results_{backend}.jsonl").read_text(encoding="utf-8").splitlines():
            row = reviewed_response(json.loads(line))
            attempts.append(row)
            if row["repeat"] <= 5:
                continue
            valid = row["status"] == "success" and row.get("web_search_observed") and len(row.get("recommendations", [])) == 5 and sorted(int(r.get("rank", 0)) for r in row["recommendations"]) == [1, 2, 3, 4, 5] and len({normalize(r.get("name")) for r in row["recommendations"]}) == 5
            if valid and row["run_id"] not in chosen:
                chosen[row["run_id"]] = row
    return sorted(chosen.values(), key=lambda r: (r["backend"], r["prompt_id"], r["repeat"])), attempts


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    z = 1.95996398454
    center = (k / n + z*z / (2*n)) / (1 + z*z/n)
    half = z * math.sqrt(k/n*(1-k/n)/n + z*z/(4*n*n)) / (1+z*z/n)
    return max(0, center-half), min(1, center+half)


def features(registry: list[dict]) -> list[dict]:
    checks = load_csv(STUDY / "feature_checks.csv")
    manual = {(r["restaurant_id"], r["feature"]): r for r in checks}
    extra = load_csv(ROOT / "verified_features.csv")
    for row in extra:
        manual[row["restaurant_id"], row["feature"]] = row
    result = []
    for row in registry:
        rid = row["entity_id"]
        values = {"entity_id": rid, "name_ko": row["name_ko"], "area": row["area"], "sampling_cohort": row["sampling_cohort"], "identity_status": row["identity_status"], "category_external": row["category_prior_external"] or "", "own_website_external": {"yes": 1, "no": 0}.get(row["own_website_prior_external"], ""), "menu_price_public_external": "", "signature_price_krw_external": "", "solo_seating_external": "", "tourism_individual_page_external": "", "guide_individual_page_external": "", "established_year_external": "", "google_review_count": "", "google_star_rating": "", "naver_review_count": "", "photo_count": "", "recent_review_age_days": "", "channel_address_consistent": "", "schema_restaurant_external": "", "feature_snapshot_date": "2026-10-13", "evidence_urls": ""}
        urls = []
        mapping = {"menu_price_text": "menu_price_public_external", "solo_seating_disclosed": "solo_seating_external", "official_tourism_individual_page": "tourism_individual_page_external", "independent_guide_individual_page": "guide_individual_page_external", "established_year": "established_year_external", "own_website_accessible": "own_website_external", "category_external": "category_external"}
        for (entity_id, feature), evidence in manual.items():
            if entity_id != rid:
                continue
            urls.append(evidence["source_url"])
            if feature in mapping:
                value = evidence["value"]
                values[mapping[feature]] = value if feature == "category_external" else int(value) if value.isdigit() and feature == "established_year" else 1 if value == "yes" or value.isdigit() else 0 if value == "no" else ""
            if feature in ("google_review_count", "naver_review_count", "photo_count", "google_star_rating", "recent_review_age_days", "channel_address_consistent", "schema_restaurant_external") and evidence["value"] != "":
                value = evidence["value"]
                numeric_value = 1.0 if value == "yes" else 0.0 if value == "no" else float(value)
                assert numeric_value >= 0, (entity_id, feature, value)
                if feature == "google_star_rating":
                    assert numeric_value <= 5
                if feature in ("channel_address_consistent", "schema_restaurant_external"):
                    assert numeric_value in (0, 1)
                values[feature] = int(numeric_value) if numeric_value.is_integer() else numeric_value
            if feature == "menu_price_text" and evidence["value"].isdigit():
                values["signature_price_krw_external"] = int(evidence["value"])
        values["evidence_urls"] = "|".join(dict.fromkeys(urls))
        codebook = {r["category_external"]: r["menu_family_external"] for r in load_csv(ROOT / "category_codebook.csv")}
        values["menu_family_external"] = codebook.get(values["category_external"], "")
        for key in ("google_review_count", "naver_review_count", "photo_count"):
            values["log1p_" + key] = math.log1p(float(values[key])) if values[key] != "" else ""
        for key in list(values):
            if key.endswith("_external") or key in ("google_review_count", "google_star_rating", "naver_review_count", "photo_count", "recent_review_age_days", "channel_address_consistent"):
                values[key + "_missing"] = int(values[key] == "")
        result.append(values)
    save_csv("restaurant_features.csv", result)
    return result


def prepare() -> dict:
    registry = freeze_registry()
    runs, attempts = completed_runs()
    idx = alias_index(registry)
    lookup = {r["entity_id"]: r for r in registry}
    recs, run_rows, unmatched = [], [], []
    for run in runs:
        phase = "baseline" if run["repeat"] <= 5 else "prospective"
        run_rows.append({k: run.get(k, "") for k in ("run_id", "backend", "prompt_id", "area", "repeat", "requested_model", "started_at_utc", "finished_at_utc", "web_search_observed", "raw_path")} | {"phase": phase, "model_version_actual": "not_exposed" if run["backend"] == "codex" else "|".join(run.get("reported_models", []))})
        for rec in run["recommendations"]:
            rid = match(rec, run["area"], registry, idx)
            signature = lookup.get(rid, {}).get("address_signature_ko", "")
            address = normalize(rec.get("address"))
            branch_label = 1 if signature and signature in address else (0 if signature and address else "")
            row = {"run_id": run["run_id"], "backend": run["backend"], "prompt_id": run["prompt_id"], "area": run["area"], "repeat": run["repeat"], "phase": phase, "rank": int(rec["rank"]), "entity_id": rid, "name_raw": rec["name"], "name_canonical": lookup.get(rid, {}).get("name_ko", ""), "branch_raw": rec.get("branch") or "", "address_raw": rec.get("address") or "", "original_address_match": branch_label, "price_raw_model_do_not_train": rec.get("price") or "", "cuisine_raw_model_do_not_train": rec.get("cuisine") or "", "reason_raw_model_do_not_train": rec.get("reason") or "", "sources_raw_model_do_not_train": "|".join(rec.get("sources") or []), "match_status": "unique_alias_brand" if rid else "unmatched_or_new_candidate"}
            recs.append(row)
            if not rid:
                unmatched.append(row)
    save_csv("runs_clean.csv", run_rows)
    save_csv("recommendations_clean.csv", recs)
    save_csv("unmatched_review_queue.csv", unmatched, list(recs[0]) if recs else [])
    observed = defaultdict(dict)
    for rec in recs:
        if rec["entity_id"]:
            observed[rec["run_id"]][rec["entity_id"]] = rec
    trials = []
    for run in run_rows:
        intent = "general" if run["prompt_id"].endswith("01") else "budget" if run["prompt_id"].endswith("02") else "solo" if run["prompt_id"] in ("MD03", "SS04") else "seated_meal" if run["prompt_id"] == "MW04" else "traditional_dishes" if run["prompt_id"] == "MD04" else "market_food" if run["prompt_id"] == "MW03" else "distinctive_dinner"
        for restaurant in registry:
            if restaurant["area"] != run["area"]:
                continue
            rec = observed[run["run_id"]].get(restaurant["entity_id"])
            prospective_eligible = run["phase"] == "prospective" or restaurant["sampling_cohort"] == "original30_preselected"
            trials.append({"run_id": run["run_id"], "entity_id": restaurant["entity_id"], "brand_group": brand_group(restaurant["name_ko"]), "backend": run["backend"], "area": run["area"], "prompt_id": run["prompt_id"], "intent": intent, "repeat": run["repeat"], "phase": run["phase"], "sampling_cohort": restaurant["sampling_cohort"], "selection_uses_outcome": restaurant["selection_uses_outcome"], "eligible_for_feature_analysis": int(prospective_eligible), "eligible_original_cohort": int(restaurant["sampling_cohort"] == "original30_preselected"), "condition_eligibility": "general_meal_query" if intent == "general" else "needs_manual_review", "appeared_brand": int(rec is not None), "appeared_original_address": rec["original_address_match"] if rec else 0, "rank": rec["rank"] if rec else "", "top3": int(rec is not None and rec["rank"] <= 3), "reciprocal_rank": 1/rec["rank"] if rec else 0})
    save_csv("exposure_trials.csv", trials)
    feat = features(registry)
    feature_lookup = {row["entity_id"]: row for row in feat}
    aggregate = []
    for backend in ("codex", "agy"):
        for row in registry:
            for phase in ("baseline", "prospective", "all"):
                group = [trial for trial in trials if trial["backend"] == backend and trial["entity_id"] == row["entity_id"] and (phase == "all" or trial["phase"] == phase)]
                if not group:
                    continue
                if row["sampling_cohort"] != "original30_preselected" and phase in ("baseline", "all"):
                    continue
                generic = [trial for trial in group if trial["intent"] == "general"]
                k, n = sum(t["appeared_brand"] for t in group), len(group)
                ci = wilson(k, n)
                aggregate.append({"entity_id": row["entity_id"], "name_ko": row["name_ko"], "area": row["area"], "backend": backend, "phase": phase, "sampling_cohort": row["sampling_cohort"], "runs": n, "appearance_count": k, "appearance_rate": k/n, "general_runs": len(generic), "general_appearance_count": sum(t["appeared_brand"] for t in generic), "general_appearance_rate": mean(t["appeared_brand"] for t in generic) if generic else "", "top3_rate": mean(t["top3"] for t in group), "mean_reciprocal_rank": mean(t["reciprocal_rank"] for t in group), "wilson_low_descriptive": ci[0], "wilson_high_descriptive": ci[1], "original_address_count": sum(t["appeared_original_address"] == 1 for t in group), "address_unknown_mentions": sum(t["appeared_brand"] and t["appeared_original_address"] == "" for t in group)})
    save_csv("store_outcomes.csv", aggregate)
    query_groups = defaultdict(list)
    for trial in trials:
        if trial["eligible_for_feature_analysis"]:
            query_groups[trial["entity_id"], trial["backend"], trial["prompt_id"], trial["phase"]].append(trial)
    query_outcomes = [{"entity_id": key[0], "backend": key[1], "prompt_id": key[2], "phase": key[3], "runs": len(group), "appearance_count": sum(t["appeared_brand"] for t in group), "appearance_rate": mean(t["appeared_brand"] for t in group), "intent": group[0]["intent"], "condition_eligibility": group[0]["condition_eligibility"]} for key, group in query_groups.items()]
    save_csv("query_outcomes.csv", query_outcomes)
    numeric_predictors = ["own_website_external", "menu_price_public_external", "signature_price_krw_external", "solo_seating_external", "tourism_individual_page_external", "guide_individual_page_external", "established_year_external", "log1p_google_review_count", "google_star_rating", "log1p_naver_review_count", "log1p_photo_count", "recent_review_age_days", "channel_address_consistent", "schema_restaurant_external"]
    categorical_predictors = ["area", "menu_family_external"]
    train_rows = []
    checked_entities = {r["entity_id"] for r in load_csv(ROOT / "verified_entities.csv") if r.get("identity_reference_checked") == "1" and r.get("source_url")}
    for outcome in aggregate:
        if outcome["phase"] != "prospective":
            continue
        f = feature_lookup[outcome["entity_id"]]
        train_rows.append(outcome | {key: f.get(key, "") for key in numeric_predictors + ["category_external", "menu_family_external"]} | {"brand_group": brand_group(outcome["name_ko"]), "feature_snapshot_date": f["feature_snapshot_date"], "identity_prior_reference_checked": int(f["identity_status"] == "legacy_source_checked_not_current"), "identity_reference_checked_external": int(outcome["entity_id"] in checked_entities), "minimal_website_category_documented": int(f["own_website_external"] != "" and f["category_external"] != "")})
    save_csv("model_table_prospective.csv", train_rows)
    split = []
    keys = sorted({brand_group(row["name_ko"]) for row in registry})
    random.Random(20261013).shuffle(keys)
    folds = {key: i % 5 for i, key in enumerate(keys)}
    for row in registry:
        split.append({"entity_id": row["entity_id"], "brand_group": brand_group(row["name_ko"]), "group_fold_5": folds[brand_group(row["name_ko"])], "area_holdout": row["area"], "phase_train": "repeat_1_to_5_original_cohort_only", "phase_test": "repeat_6_to_10", "avoid_row_random_split": 1})
    save_csv("group_folds.csv", split)
    missingness = [{"column": key, "missing": sum(row.get(key, "") == "" for row in feat), "total": len(feat), "missing_rate": sum(row.get(key, "") == "" for row in feat)/len(feat), "usable_as_predictor_now": int(any(row.get(key, "") != "" for row in feat))} for key in numeric_predictors + ["category_external", "menu_family_external"]]
    save_csv("feature_missingness.csv", missingness)
    forbidden = ["entity_id", "name_ko", "brand_group", "sampling_cohort", "selection_uses_outcome", "prior_visibility_stratum", "appearance_count", "top3_rate", "mean_reciprocal_rank", "sources_raw_model_do_not_train", "reason_raw_model_do_not_train", "price_raw_model_do_not_train", "cuisine_raw_model_do_not_train", "category_external", "identity_status", "identity_prior_reference_checked", "identity_reference_checked_external", "minimal_website_category_documented", "evidence_urls"]
    config = {"unit": "one_restaurant_per_backend_in_prospective_phase", "target": "general_appearance_rate", "alternative_target": "appearance_rate", "numeric_predictors": numeric_predictors, "categorical_predictors": categorical_predictors, "context_only_predictors": ["backend"], "forbidden_predictors": forbidden, "split_group": "brand_group", "primary_cohort": "original30_preselected", "expanded_cohort": "baseline_discovery_prospective_only_requires_identity_review", "null_policy": "Unknown evidence remains null. No zero filling of missing numeric features. Fit imputation and encoders on training folds only.", "rate_denominator": "successful_runs_in_same_area_and_phase", "feature_timing": "Original listing is prior snapshot; checked feature values are observation-era data, not causal pre-treatment evidence.", "interpretation": "SHAP describes predictive model associations, not restaurant exposure causes."}
    (ROOT / "model_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    data_dictionary = [{"table": "exposure_trials.csv", "column": key, "meaning": text} for key, text in {"run_id": "Successful independent CLI question; technical failures excluded", "entity_id": "Frozen candidate brand entity within area, not guaranteed exact branch", "appeared_brand": "1 mentioned; 0 absent from completed response", "appeared_original_address": "1 same legacy address; 0 other/absent; blank address unknown; not real-world verification", "eligible_for_feature_analysis": "Discovery candidates baseline rows excluded", "condition_eligibility": "Only general queries avoid budget/cuisine/solo suitability confounding"}.items()]
    data_dictionary += [{"table": "restaurant_features.csv", "column": key, "meaning": "Externally supported feature; blank=not collected. Response-derived prices, reasons, citations not allowed predictors."} for key in numeric_predictors]
    save_csv("data_dictionary.csv", data_dictionary)
    assert len({row["entity_id"] for row in registry}) == len(registry)
    assert len({(t["run_id"], t["entity_id"]) for t in trials}) == len(trials)
    assert all(0 <= row["appearance_rate"] <= 1 for row in aggregate)
    assert not set(numeric_predictors + categorical_predictors) & set(forbidden)
    summary = {"run_count": len(runs), "baseline_runs": sum(r["repeat"] <= 5 for r in runs), "prospective_runs": sum(r["repeat"] > 5 for r in runs), "planned_run_count": 240, "candidate_registry_count": len(registry), "original_store_count": 30, "discovery_candidate_count": len(registry)-30, "registry_area_counts": dict(Counter(r["area"] for r in registry)), "trial_rows": len(trials), "recommended_slots": len(recs), "unmatched_slots": len(unmatched), "model_table_rows": len(train_rows), "stores_with_minimal_website_category": len({r["entity_id"] for r in train_rows if r["minimal_website_category_documented"]}), "raw_files_missing": sum(not Path(r["raw_path"]).exists() for r in runs), "web_search_missing": sum(not r["web_search_observed"] for r in runs), "feature_learning_not_yet_run": True}
    (ROOT / "preprocessing_validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"registry_count": len(freeze_registry())} if args.freeze_only else prepare(), ensure_ascii=False))
