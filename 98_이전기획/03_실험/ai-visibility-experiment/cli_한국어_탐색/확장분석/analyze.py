"""Descriptive patterns; store-level tests never count repeated runs as new stores."""
from __future__ import annotations
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from prepare import ROOT, load_csv, save_csv, normalize, prepare, AREA_NAMES, wilson


def average_ranks(values):
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    for _, group in itertools.groupby(ordered, key=lambda pair: pair[1]):
        items = list(group)
        positions = [ordered.index(item) + 1 for item in items]
        for index, _ in items:
            ranks[index] = mean(positions)
    return ranks


def corr(a, b):
    if len(a) < 3:
        return None
    aa, bb = average_ranks(a), average_ranks(b)
    ma, mb = mean(aa), mean(bb)
    denom = math.sqrt(sum((x-ma)**2 for x in aa)*sum((y-mb)**2 for y in bb))
    return sum((x-ma)*(y-mb) for x,y in zip(aa,bb))/denom if denom else None


def pattern_report():
    summary = prepare()
    registry = load_csv(ROOT / "restaurant_registry.csv")
    trials = load_csv(ROOT / "exposure_trials.csv")
    outcomes = load_csv(ROOT / "store_outcomes.csv")
    recs = load_csv(ROOT / "recommendations_clean.csv")
    runs = load_csv(ROOT / "runs_clean.csv")
    lookup = {r["entity_id"]:r for r in registry}
    trial_groups = defaultdict(list)
    for row in trials:
        trial_groups[row["entity_id"],row["phase"]].append(row)
    ranking=[]
    for restaurant in registry:
        phase="all" if restaurant["sampling_cohort"]=="original30_preselected" else "prospective"
        group = [r for r in trials if r["entity_id"]==restaurant["entity_id"] and (phase=="all" or r["phase"]==phase)]
        if not group:
            continue
        rates=[]
        for backend in ("codex","agy"):
            b=[r for r in group if r["backend"]==backend]
            rates.append(sum(int(r["appeared_brand"]) for r in b)/len(b) if b else 0)
        generic=[r for r in group if r["intent"]=="general"]
        gk=sum(int(r["appeared_brand"]) for r in generic)
        k=sum(int(r["appeared_brand"]) for r in group)
        ci=wilson(gk,len(generic))
        ranking.append({"entity_id":restaurant["entity_id"],"name_ko":restaurant["name_ko"],"area":restaurant["area"],"cohort":restaurant["sampling_cohort"],"phase":phase,"appearance_count":k,"runs":len(group),"appearance_rate":k/len(group),"codex_rate":rates[0],"gemini_rate":rates[1],"general_count":gk,"general_runs":len(generic),"general_rate":gk/len(generic) if generic else "","general_wilson_low":ci[0],"general_wilson_high":ci[1],"top3_rate":mean(int(r["top3"]) for r in group),"mrr":mean(float(r["reciprocal_rank"]) for r in group),"original_address_matches":sum(r["appeared_original_address"]=="1" for r in group)})
    ranking.sort(key=lambda r:(r["area"],r["cohort"],-r["appearance_rate"],r["name_ko"]))
    save_csv("ranking_by_cohort.csv",ranking)
    prospective_ranking=[]
    for restaurant in registry:
        group=trial_groups[restaurant["entity_id"],"prospective"]
        if group:
            prospective_ranking.append({"entity_id":restaurant["entity_id"],"name_ko":restaurant["name_ko"],"area":restaurant["area"],"cohort":restaurant["sampling_cohort"],"runs":len(group),"appearance_count":sum(int(r["appeared_brand"]) for r in group),"appearance_rate":mean(int(r["appeared_brand"]) for r in group),"general_count":sum(int(r["appeared_brand"]) for r in group if r["intent"]=="general"),"general_runs":sum(r["intent"]=="general" for r in group),"top3_rate":mean(int(r["top3"]) for r in group)})
    prospective_ranking.sort(key=lambda r:(r["area"],-r["appearance_rate"],r["name_ko"]))
    save_csv("ranking_prospective_all_candidates.csv",prospective_ranking)
    sets=defaultdict(set)
    for r in recs:
        sets[r["run_id"]].add(r["entity_id"] or r["area"]+":"+normalize(r["name_raw"]))
    consistent=[]
    for backend in ("codex","agy"):
        for pid in sorted({r["prompt_id"] for r in runs}):
            for phase in ("baseline","prospective","all"):
                rs=[r for r in runs if r["backend"]==backend and r["prompt_id"]==pid and (phase=="all" or r["phase"]==phase)]
                pairs=list(itertools.combinations([sets[r["run_id"]] for r in rs],2))
                consistent.append({"backend":backend,"prompt_id":pid,"phase":phase,"runs":len(rs),"pairs":len(pairs),"shared_mean_out_of_5":mean(len(a&b) for a,b in pairs) if pairs else "","shared_median_out_of_5":median(len(a&b) for a,b in pairs) if pairs else "","jaccard_mean":mean(len(a&b)/len(a|b) for a,b in pairs) if pairs else ""})
    save_csv("repeat_stability.csv",consistent)
    run_lookup={(r["backend"],r["prompt_id"],r["repeat"]):r for r in runs}
    model_overlap=[]
    for pid in sorted({r["prompt_id"] for r in runs}):
        for phase in ("baseline","prospective","all"):
            vals=[]
            for repeat in range(1,11):
                if (phase=="baseline" and repeat>5) or (phase=="prospective" and repeat<=5):continue
                a=run_lookup.get(("codex",pid,str(repeat)));b=run_lookup.get(("agy",pid,str(repeat)))
                if a and b:vals.append(len(sets[a["run_id"]]&sets[b["run_id"]]))
            model_overlap.append({"prompt_id":pid,"phase":phase,"paired_runs":len(vals),"shared_mean_out_of_5":mean(vals) if vals else "","shared_median_out_of_5":median(vals) if vals else ""})
    save_csv("model_overlap.csv",model_overlap)
    rank_stability=[]
    for backend in ("codex","agy"):
        for area in AREA_NAMES:
            cohort=[r for r in registry if r["area"]==area and r["sampling_cohort"]=="original30_preselected"]
            vals={}
            for phase in ("baseline","prospective"):
                vals[phase]=[]
                for restaurant in cohort:
                    group=[r for r in trials if r["backend"]==backend and r["entity_id"]==restaurant["entity_id"] and r["phase"]==phase]
                    vals[phase].append(mean(int(r["appeared_brand"]) for r in group) if group else 0)
            ever = [i for i, (a, b) in enumerate(zip(vals["baseline"], vals["prospective"])) if a > 0 or b > 0]
            rank_stability.append({"backend":backend,"area":area,"independent_store_count":len(cohort),"spearman_baseline_vs_prospective":corr(vals["baseline"],vals["prospective"]),"ever_exposed_store_count":len(ever),"spearman_among_ever_exposed":corr([vals["baseline"][i] for i in ever], [vals["prospective"][i] for i in ever]),"note":"original cohort; ties included; descriptive; also report excluding persistent zeros"})
    save_csv("rank_stability.csv",rank_stability)
    ff={row["entity_id"]:row for row in load_csv(ROOT/"restaurant_features.csv")}
    menu_groups = defaultdict(list)
    for r in ranking:
        if r["cohort"] == "original30_preselected" and r["general_runs"]:
            family = ff[r["entity_id"]].get("menu_family_external", "")
            if family:
                menu_groups[r["area"], family].append(r)
    menu_summary = [{"area": key[0], "menu_family_external": key[1], "independent_stores": len(group), "mean_general_rate": mean(r["general_rate"] for r in group), "mean_all_question_rate": mean(r["appearance_rate"] for r in group), "warning": "descriptive; small purposive groups; some n=1; not feature causal effects"} for key, group in sorted(menu_groups.items())]
    save_csv("menu_family_summary_original.csv", menu_summary)
    original_zero = [r for r in ranking if r["cohort"] == "original30_preselected" and r["appearance_count"] == 0]
    save_csv("original_zero_exposure.csv", original_zero, list(ranking[0]))
    model_diffs = [{"entity_id": r["entity_id"], "name_ko": r["name_ko"], "area": r["area"], "codex_rate": r["codex_rate"], "gemini_rate": r["gemini_rate"], "difference_codex_minus_gemini_pp": 100*(r["codex_rate"]-r["gemini_rate"])} for r in ranking if r["cohort"] == "original30_preselected"]
    model_diffs.sort(key=lambda r: -abs(r["difference_codex_minus_gemini_pp"]))
    save_csv("model_differences_original.csv", model_diffs)
    by_area=defaultdict(list)
    for r in ranking:
        if r["cohort"]=="original30_preselected" and r["general_runs"]:
            val=ff[r["entity_id"]]["own_website_external"]
            if val!="":by_area[r["area"]].append((int(val),r["general_rate"]))
    contrasts=[]
    for area,group in by_area.items():
        yes=[v for w,v in group if w==1];no=[v for w,v in group if w==0]
        contrasts.append({"area":area,"stores_yes":len(yes),"stores_no":len(no),"mean_general_rate_yes":mean(yes) if yes else "","mean_general_rate_no":mean(no) if no else "","difference_pp":100*(mean(yes)-mean(no)) if yes and no else "","interpretation":"legacy website data; general questions; descriptive not causal"})
    save_csv("website_association_original_cohort.csv",contrasts)
    usable={a:g for a,g in by_area.items() if {w for w,_ in g}=={0,1}}
    statistic=lambda groups:mean(mean(v for w,v in g if w==1)-mean(v for w,v in g if w==0) for g in groups.values()) if groups else 0
    observed=statistic(usable)
    rng=random.Random(20261013);exceed=0
    for _ in range(5000):
        randomized={}
        for a,g in usable.items():
            labels=[w for w,v in g];rng.shuffle(labels)
            randomized[a]=list(zip(labels,[v for w,v in g]))
        exceed+=abs(statistic(randomized))>=abs(observed)
    permutation={"independent_stores":sum(len(g) for g in usable.values()),"areas_with_both_website_groups":list(usable),"area_standardized_difference_pp":100*observed,"permutations":5000,"p_two_sided_exploratory":(exceed+1)/5001,"causal":False,"selection_warning":"original cohort is purposively selected, not representative"}
    (ROOT/"website_permutation.json").write_text(json.dumps(permutation,ensure_ascii=False,indent=2),encoding="utf-8")
    retention=[]
    for area in AREA_NAMES:
        cohort=[r for r in prospective_ranking if r["area"]==area and r["cohort"]!="original30_preselected"]
        retention.append({"area":area,"discovery_candidates":len(cohort),"mentioned_again_count":sum(r["appearance_count"]>0 for r in cohort),"not_mentioned_again_count":sum(r["appearance_count"]==0 for r in cohort),"warning":"identity not verified for every candidate; frozen baseline discovery frame"})
    save_csv("candidate_retention.csv",retention)
    info={"summary":summary,"original_zero_exposure_count":len(original_zero),"discovery_mentioned_again":sum(r["mentioned_again_count"] for r in retention),"discovery_not_mentioned_again":sum(r["not_mentioned_again_count"] for r in retention),"website_permutation":permutation,"mean_within_model_overlap":{b:sum(r["shared_mean_out_of_5"]*r["pairs"] for r in consistent if r["backend"]==b and r["phase"]=="all" and r["pairs"])/sum(r["pairs"] for r in consistent if r["backend"]==b and r["phase"]=="all" and r["pairs"]) for b in ("codex","agy")},"cross_model_overlap":sum(r["shared_mean_out_of_5"]*r["paired_runs"] for r in model_overlap if r["phase"]=="all" and r["paired_runs"])/sum(r["paired_runs"] for r in model_overlap if r["phase"]=="all" and r["paired_runs"])}
    (ROOT/"analysis_summary.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False))
    return info


if __name__=="__main__":
    pattern_report()
