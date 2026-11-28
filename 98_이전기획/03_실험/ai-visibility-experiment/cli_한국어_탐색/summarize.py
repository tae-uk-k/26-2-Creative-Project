"""Produce descriptive CSVs from saved responses, never from agent reasoning."""
from __future__ import annotations

import csv
import json
import re
from itertools import combinations
from statistics import mean
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent


ADDRESS_SIGNATURES = {
    'MD-R01': '명동10길29', 'MD-R02': '명동9길12', 'MD-R03': '명동8가길26', 'MD-R04': '삼일대로299', 'MD-R05': '명동10길3519', 'MD-R06': '명동길2511', 'MD-R07': '명동길66', 'MD-R08': '명동8나길47', 'MD-R09': '명동9길21', 'MD-R10': '명동10길1910',
    'SS-R01': '연무장길45', 'SS-R02': '아차산로7길7', 'SS-R03': '뚝섬로9길20', 'SS-R04': '연무장5길916', 'SS-R05': '왕십리로5길3', 'SS-R06': '아차산로137', 'SS-R07': '왕십리로10길6', 'SS-R08': '서울숲2길4412', 'SS-R09': '아차산로1길11', 'SS-R10': '아차산로7길36',
    'MW-R01': '포은로8길22', 'MW-R02': '망원로8길27', 'MW-R04': '포은로6길25', 'MW-R05': '포은로67', 'MW-R06': '망원로97', 'MW-R07': '망원로8길29', 'MW-R08': '방울내로82', 'MW-R09': '월드컵로13길9', 'MW-R10': '동교로83',
}


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", value.lower())


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (ROOT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(runs, slots, visibility, overview, consistency, cross_model, manifest) -> None:
    success_count = len(runs)
    pending = sum(row['status'] != 'success' for row in manifest)
    lines = ['# 한국어 CLI 식당 추천 특징 탐색', '', f'2026-10-13 · 성공 {success_count}/120회 · 미완료 {pending}회 · 상태: ' + ('실행 완료' if pending == 0 else '진행 중'), '', '## 실행 조건', '', '- 명동·성수·망원 각 4개 한국어 질문, 모델별 질문당 5회, 매번 새 세션.', '- VPN·국적·여행 시나리오를 통제하지 않은 현재 CLI 환경. 질문에 식당 목록이나 이름을 제공하지 않음.', '- Codex 요청 모델: `gpt-6.1-sol` / Antigravity 표시 모델: `Gemini 3.8 Flash (Low)`.', '- 실제 검색 호출 로그와 응답 원문을 저장. 표본 밖 추천도 모두 보존.', '- Gemini CLI 자체는 `UNSUPPORTED_CLIENT` 오류로 실행 불가. Gemini 측정은 Antigravity로 분리하며, 기존 소비자 웹 결과와 합산하지 않음.', '', '## 실행 현황', '', '| 도구 | 성공 | 시간 초과 | 기타 실패 |', '|---|---:|---:|---:|']
    for row in overview:
        lines.append(f"| {row['backend']} | {row['successful_unique_runs']} | {row['timeouts']} | {row['technical_failures'] + row['response_format_errors']} |")
    lines += ['', '응답이 없는 오류·시간 초과는 추천 미노출로 집계하지 않음. 단, 원문에 공급자의 완료 표식(Codex turn.completed / Antigravity result SUCCESS)과 5개 추천 JSON이 확인된 경우는 응답 성공과 CLI 종료 오류를 구분해 응답을 사용한다. 원본 실행 상태와 재판정은 response_review.csv에 보존하며, 응답 성공과 프로세스 시간 초과 숫자는 겹칠 수 있다.', '', '## 주요 식당의 등장 횟수', '', '분모는 해당 지역의 성공한 질문 수. 일반·예산·혼밥·메뉴 질문이 섞인 탐색 지표이며, 상호 기준 등장과 기존 표본 주소 일치 등장을 별도로 기록했다. 아래 표는 상호 기준이며, 기존 표본 주소가 함께 표시된 횟수는 sample_visibility.csv의 appeared_runs_original_address_match 열에 기록했다. 주소 일치는 응답과 기존 표본의 대조이며 실제 영업·이전 여부를 검증한 판정이 아니다.', '', '| 지역 | 식당 | Codex | Gemini / Antigravity |', '|---|---|---:|---:|']
    selected = ['MD-R01', 'MD-R02', 'MD-R05', 'MD-R06', 'MD-R08', 'MD-R09', 'SS-R01', 'SS-R02', 'SS-R08', 'MW-R01', 'MW-R07', 'MW-R10']
    lookup = {(row['backend'], row['restaurant_id']): row for row in visibility}
    area_names = {'myeongdong': '명동', 'seongsu': '성수', 'mangwon': '망원'}
    for rid in selected:
        a, b = lookup.get(('codex', rid), {}), lookup.get(('agy', rid), {})
        base = a or b
        av = f"{a.get('appeared_runs_name_match', 0)}/{a.get('regional_successful_runs', 0)}"
        bv = f"{b.get('appeared_runs_name_match', 0)}/{b.get('regional_successful_runs', 0)}"
        lines.append(f"| {area_names.get(base.get('area'), '')} | {base.get('name_ko', rid)} | {av} | {bv} |")
    matched_slots = sum(bool(slot['restaurant_id_name_match']) for slot in slots)
    lines += ['', f'전체 추천 {len(slots)}개 슬롯 중 기존 30곳과 상호가 매칭된 슬롯은 {matched_slots}개. 나머지는 표본 밖 또는 미매칭으로 별도 보존.', '', '## 이번에 검토할 특징', '', '1. **대표 메뉴와 축적된 외부 소개 정보**: 자주 등장하는 명동교자·하동관은 미쉐린의 개별 소개 페이지에서 대표 메뉴와 오랜 운영 이력을 확인했다. 소문난성수감자탕·우이락도 관광기관 자료에 가게별 특징이 구체적으로 공개되어 있다. 추천 원인이라고 확정하지 않고 다음 비교 가설로 사용한다.', '2. **홈페이지·가격표 공개만으로는 충분하지 않은 사례**: 하수오곰탕·고시레는 자체 사이트, 주소, 메뉴 가격을 직접 확인했다. 이들의 실제 등장 횟수는 위 표와 CSV에 기록했다. 사이트 보유 효과 전체를 부정하거나 외부 소개 효과를 증명한 결과는 아니다.', '3. **질문 조건별 차이**: 예산·혼밥·시장 음식 등 요구에 따라 후보가 달라짐. 특징 비교에는 조건이 적은 일반 질문의 등장률도 별도 제공한다.', '', '## 반복 측정과 모델 차이', '']
    for backend in ('codex', 'agy'):
        valid = [row for row in consistency if row['backend'] == backend and row['pair_count']]
        weights = sum(row['pair_count'] for row in valid)
        overlap = sum(row['mean_common_restaurants_out_of_5'] * row['pair_count'] for row in valid) / weights if weights else 0
        lines.append(f'- {backend}: 같은 질문의 두 응답을 비교할 때 평균 {overlap:.2f}/5곳이 겹침. 현재 {weights}개 응답 쌍 기준.')
    paired = sum(row['paired_repeats'] for row in cross_model)
    if paired:
        overlap = sum(row['mean_common_restaurants_out_of_5'] * row['paired_repeats'] for row in cross_model if row['paired_repeats']) / paired
        lines.append(f'- 같은 질문·반복 번호로 두 모델을 비교하면 평균 {overlap:.2f}/5곳이 겹침. 현재 {paired}쌍 기준.')
    lines += ['', '## 해석 범위와 검수', '', '- 30곳은 기존에 선정한 표본이며 지역 전체 식당의 전수 목록이 아니다. 표본 밖 추천은 제외하지 않는다.', '- 5회 반복은 추천 변동을 관찰하기 위한 반복이며, 동일 식당을 독립 표본 5개로 부풀려 통계 검정하지 않는다.', '- 홈페이지 보유 여부 비교 CSV는 기존 목록의 조사 시점 값이다. 이번에 직접 확인한 특징은 `feature_checks.csv`에 구분했다.', '- 리뷰 수·별점·사진 수의 효과는 아직 측정하지 않았으므로 주장하지 않는다.', '- 상호 매칭과 실제 지점·현재 영업·가격 정확도는 별개다. 출처 전체의 내용 검증을 완료한 상태가 아니며, 일부 접근 오류는 죽은 링크라고 단정하지 않는다.', '- `page_source_count`는 URL 경로 유무를 세는 기계적 검사로, 페이지가 식당 정보를 뒷받침한다는 판정이 아니다.', '- 기존 표본의 MW-R04는 흥흥호떡으로 적혀 있으나 응답의 훈훈호떡과 Hoon-Hoon Hotteok 자료를 주소 기준으로 대조하는 항목이다. 원본 표본은 변경하지 않았다.', '', '## 확인한 공개 자료', '', '- [명동교자: 메뉴·운영 이력](https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/myeongdong-kyoja)', '- [하동관: 메뉴·운영 이력](https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/hadongkwan)', '- [소문난성수감자탕: 혼밥·운영 정보](https://stage-kr.visitseoul.net/restaurants/SeongsuGamjatang/KOPlceoxk)', '- [우이락: 대표 메뉴·주소](https://english.visitkorea.or.kr/svc/thingsToDo/foodTrip/special_view.do?vcontsId=187836)', '- [하수오곰탕 메뉴](https://www.myeongdong-restaurant.com/ko/menu)', '- [고시레 메뉴·주소](https://www.myeongdongkoreanbbq.kr/ko)', '', '## 파일과 재실행', '', '- `prompts_ko.csv`: 실제 질문 원문 / `run_manifest.csv`: 120회 실행 상태.', '- `results_codex.jsonl`, `results_agy.jsonl`, `raw/`: 원문과 실행 로그.', '- `sample_visibility.csv`: 표본 30곳의 모델별 노출률과 일반 질문 노출률.', '- `recommendations.csv`: 표본 밖을 포함한 전체 추천 / `sources.csv`: 모델 반환 출처.', '- `repeat_consistency.csv`, `cross_model_overlap.csv`: 반복 변동과 모델 간 공통 추천.', '- `feature_checks.csv`, `source_checks.csv`: 직접 확인한 특징과 출처 접근 기록.', '', '```powershell', "& '.\\04_MVP\\hanoon-mvp\\.venv\\Scripts\\python.exe' '.\\03_실험\\ai-visibility-experiment\\cli_한국어_탐색\\run_cli.py' --backend codex --repeats 5 --workers 2", "& '.\\04_MVP\\hanoon-mvp\\.venv\\Scripts\\python.exe' '.\\03_실험\\ai-visibility-experiment\\cli_한국어_탐색\\run_cli.py' --backend agy --repeats 5 --workers 1 --timeout 300", "& '.\\04_MVP\\hanoon-mvp\\.venv\\Scripts\\python.exe' '.\\03_실험\\ai-visibility-experiment\\cli_한국어_탐색\\summarize.py'", '```', '', '재실행 시 성공한 실행 ID는 건너뛰고 미완료만 수행한다. 로그인된 계정의 사용량을 사용한다.']
    (ROOT / '결과_요약.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def reviewed_response(row: dict) -> dict:
    row = dict(row)
    row['process_status'] = row.get('process_status', row['status'])
    row['completion_recovered_from_raw'] = row['status'] == 'success' and row['process_status'] != 'success'
    if row['status'] == 'success':
        return row
    if len(row.get('recommendations', [])) != 5 or not row.get('web_search_observed'):
        return row
    completed = False
    for line in Path(row['raw_path']).read_text(encoding='utf-8').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if row['backend'] == 'codex' and event.get('type') == 'turn.completed':
            completed = True
        if row['backend'] == 'agy' and event.get('event') == 'result' and event.get('result', {}).get('status') == 'SUCCESS':
            completed = True
    if completed:
        row['status'] = 'success'
        row['completion_recovered_from_raw'] = True
    return row


def main() -> None:
    with (ROOT.parent / "restaurants.csv").open(encoding="utf-8-sig", newline="") as handle:
        sample = list(csv.DictReader(handle))
    runs = []
    attempts = []
    for file in ROOT.glob("results_*.jsonl"):
        for line in file.read_text(encoding="utf-8").splitlines():
            row = reviewed_response(json.loads(line))
            attempts.append(row)
            if row["status"] == "success":
                runs.append(row)
    deduplicated = {row["run_id"]: row for row in runs}
    runs = list(deduplicated.values())
    latest_attempts = {row["run_id"]: row for row in attempts}
    manifest = []
    prompt_ids = ["MD01", "MD02", "MD03", "MD04", "SS01", "SS02", "SS03", "SS04", "MW01", "MW02", "MW03", "MW04"]
    for backend in ("codex", "agy"):
        for prompt_id in prompt_ids:
            for repeat in range(1, 6):
                run_id = f"CLI-KO-{backend.upper()}-{prompt_id}-R{repeat}"
                latest = latest_attempts.get(run_id, {})
                manifest.append({"run_id": run_id, "backend": backend, "prompt_id": prompt_id, "repeat": repeat, "status": "success" if run_id in deduplicated else latest.get("status", "not_attempted"), "raw_path": deduplicated.get(run_id, latest).get("raw_path", "")})
    write_csv("run_manifest.csv", manifest)
    slots, source_rows = [], []
    for run in runs:
        for rec in run["recommendations"]:
            candidates = []
            name = normalized(str(rec.get("name", "")))
            for restaurant in sample:
                if restaurant["area"] != run["area"]:
                    continue
                aliases = [restaurant["name_ko"], restaurant["canonical_name_en"]] + restaurant["aliases"].split("|")
                short_name = re.sub(r"(명동본점|망원본점|성수본점|성수직영점|서울숲점|성수점|명동점|망원시장점|망원점|본점)$", "", normalized(restaurant["name_ko"]))
                if short_name:
                    aliases.append(short_name)
                # Preserve the original sample; this spelling is audited separately.
                if restaurant["restaurant_id"] == "MW-R04":
                    aliases.append("훈훈호떡")
                if any(name == normalized(alias) or (len(normalized(alias)) >= 3 and name.startswith(normalized(alias))) for alias in aliases):
                    candidates.append(restaurant["restaurant_id"])
            rid = candidates[0] if len(candidates) == 1 else ""
            address = normalized(str(rec.get("address") or ""))
            signature = ADDRESS_SIGNATURES.get(rid, "")
            address_match = bool(signature and signature in address)
            source_branch_status = "matches_original_address" if address_match else ("address_conflict_or_missing" if rid and address else "not_verifiable")
            sources = rec.get("sources") or []
            if not isinstance(sources, list):
                sources = [str(sources)]
            page_sources = [url for url in sources if urlparse(str(url)).scheme in ("http", "https") and urlparse(str(url)).path.strip("/")]
            slots.append({"run_id": run["run_id"], "backend": run["backend"], "prompt_id": run["prompt_id"], "area": run["area"], "repeat": run["repeat"], "rank": rec.get("rank"), "name": rec.get("name"), "branch": rec.get("branch"), "address": rec.get("address"), "cuisine": rec.get("cuisine"), "price": rec.get("price"), "reason": rec.get("reason"), "restaurant_id_name_match": rid, "original_address_match": address_match, "branch_address_status": source_branch_status, "match_status": "name_match_branch_unverified" if rid else ("ambiguous" if candidates else "outside_sample_or_unmatched"), "sources": "|".join(map(str, sources)), "source_count": len(sources), "page_source_count": len(page_sources), "web_search_observed": run["web_search_observed"]})
            for url in sources:
                parsed = urlparse(str(url))
                source_rows.append({"run_id": run["run_id"], "backend": run["backend"], "name": rec.get("name"), "restaurant_id_name_match": rid, "url": url, "domain": parsed.netloc, "url_has_path": bool(parsed.path.strip("/")), "verified_supports_claim": "not_yet_checked"})
    visibility = []
    for backend in sorted({run["backend"] for run in runs}):
        for restaurant in sample:
            area_runs = [run for run in runs if run["backend"] == backend and run["area"] == restaurant["area"]]
            matched = [slot for slot in slots if slot["backend"] == backend and slot["restaurant_id_name_match"] == restaurant["restaurant_id"]]
            unique = {slot["run_id"]: slot for slot in matched}
            general_prompt = {"myeongdong": "MD01", "seongsu": "SS01", "mangwon": "MW01"}[restaurant["area"]]
            general_runs = [run for run in area_runs if run["prompt_id"] == general_prompt]
            general_matches = [slot for slot in unique.values() if slot["prompt_id"] == general_prompt]
            denom = len(area_runs)
            ranks = [int(slot["rank"]) for slot in unique.values() if str(slot["rank"]).isdigit()]
            visibility.append({"backend": backend, "restaurant_id": restaurant["restaurant_id"], "area": restaurant["area"], "name_ko": restaurant["name_ko"], "regional_successful_runs": denom, "appeared_runs_name_match": len(unique), "appeared_runs_original_address_match": len({slot["run_id"] for slot in matched if slot["original_address_match"]}), "regional_appearance_rate": round(len(unique) / denom, 4) if denom else "", "general_prompt_runs": len(general_runs), "general_prompt_appeared_runs": len(general_matches), "general_prompt_appearance_rate": round(len(general_matches) / len(general_runs), 4) if general_runs else "", "top3_runs": sum(rank <= 3 for rank in ranks), "mean_reciprocal_rank_including_nonappearance": round(sum(1 / rank for rank in ranks if rank > 0) / denom, 4) if denom else "", "own_website_prior_snapshot": restaurant["own_website"], "prior_stratum_not_outcome": restaurant["prior_visibility_stratum"], "branch_review": "pending", "scope": "selected_30_restaurants_only"})
    write_csv("response_review.csv", [{"run_id": row["run_id"], "raw_path": row["raw_path"], "original_process_status": row["process_status"], "analysis_response_status": row["status"], "completion_recovered_from_raw": row["completion_recovered_from_raw"], "selected_for_analysis": row["run_id"] in deduplicated and row["raw_path"] == deduplicated[row["run_id"]]["raw_path"]} for row in attempts])
    attempt_counts = Counter((row["backend"], row["process_status"]) for row in attempts)
    overview = [{"backend": backend, "attempts": sum(count for (b, _), count in attempt_counts.items() if b == backend), "successful_unique_runs": sum(run["backend"] == backend for run in runs), "technical_failures": attempt_counts[backend, "technical_failure"], "timeouts": attempt_counts[backend, "timeout"], "response_format_errors": attempt_counts[backend, "response_format_error"], "responses_used_after_process_error": sum(run["backend"] == backend and run["completion_recovered_from_raw"] for run in runs), "search_observed_successful_runs": sum(run["backend"] == backend and run["web_search_observed"] for run in runs)} for backend in sorted({row["backend"] for row in attempts})]
    canonical_names = {restaurant["restaurant_id"]: restaurant["name_ko"] for restaurant in sample}
    grouped = defaultdict(lambda: {"count": 0, "runs": set(), "backends": set(), "areas": set(), "display_name": ""})
    for slot in slots:
        key = slot["restaurant_id_name_match"] or (slot["area"] + ":" + normalized(str(slot["name"])))
        entry = grouped[key]
        entry["display_name"] = canonical_names.get(slot["restaurant_id_name_match"], slot["name"])
        entry["count"] += 1
        entry["runs"].add(slot["run_id"])
        entry["backends"].add(slot["backend"])
        entry["areas"].add(slot["area"])
    all_names = [{"name": info["display_name"], "recommendation_slots": info["count"], "distinct_runs": len(info["runs"]), "backends": "|".join(sorted(info["backends"])), "areas": "|".join(sorted(info["areas"]))} for name, info in sorted(grouped.items(), key=lambda item: (-item[1]["count"], item[0]))]
    slot_sets = defaultdict(set)
    for slot in slots:
        slot_sets[slot["run_id"]].add(slot["restaurant_id_name_match"] or (slot["area"] + ":" + normalized(str(slot["name"]))))
    consistency = []
    for backend in sorted({run["backend"] for run in runs}):
        for prompt_id in sorted({run["prompt_id"] for run in runs}):
            group = [run for run in runs if run["backend"] == backend and run["prompt_id"] == prompt_id]
            sets = [slot_sets[run["run_id"]] for run in group]
            pairs = list(combinations(sets, 2))
            consistency.append({"backend": backend, "prompt_id": prompt_id, "successful_repeats": len(group), "pair_count": len(pairs), "mean_common_restaurants_out_of_5": round(mean(len(a & b) for a, b in pairs), 3) if pairs else "", "mean_jaccard": round(mean(len(a & b) / len(a | b) for a, b in pairs), 4) if pairs else ""})
    cross_model = []
    lookup = {(run["backend"], run["prompt_id"], run["repeat"]): run for run in runs}
    for prompt_id in sorted({run["prompt_id"] for run in runs}):
        common_counts, jaccards = [], []
        for repeat in range(1, 6):
            a = lookup.get(("codex", prompt_id, repeat))
            b = lookup.get(("agy", prompt_id, repeat))
            if a and b:
                aset = slot_sets[a["run_id"]]
                bset = slot_sets[b["run_id"]]
                common_counts.append(len(aset & bset))
                jaccards.append(len(aset & bset) / len(aset | bset))
        cross_model.append({"prompt_id": prompt_id, "paired_repeats": len(common_counts), "mean_common_restaurants_out_of_5": round(mean(common_counts), 3) if common_counts else "", "mean_jaccard": round(mean(jaccards), 4) if jaccards else ""})
    feature_comparison = []
    for backend in sorted({run["backend"] for run in runs}):
        for area in sorted({row["area"] for row in visibility}):
            for website in ("yes", "no"):
                group = [row for row in visibility if row["backend"] == backend and row["area"] == area and row["own_website_prior_snapshot"] == website and row["regional_successful_runs"] > 0]
                rates = [row["regional_appearance_rate"] for row in group]
                feature_comparison.append({"backend": backend, "area": area, "own_website_prior_snapshot": website, "restaurant_count": len(group), "mean_regional_appearance_rate": round(mean(rates), 4) if rates else "", "mean_general_prompt_appearance_rate": round(mean(row["general_prompt_appearance_rate"] for row in group if row["general_prompt_runs"]), 4) if any(row["general_prompt_runs"] for row in group) else "", "restaurants_with_at_least_one_name_match": sum(row["appeared_runs_name_match"] > 0 for row in group), "interpretation": "descriptive_prior_snapshot_not_causal"})
    write_csv("repeat_consistency.csv", consistency)
    write_csv("cross_model_overlap.csv", cross_model)
    write_csv("feature_comparison.csv", feature_comparison)
    write_csv("recommendations.csv", slots)
    write_csv("sample_visibility.csv", visibility)
    write_csv("sources.csv", source_rows)
    write_csv("run_summary.csv", overview)
    write_csv("all_recommended_names.csv", all_names)
    write_report(runs, slots, visibility, overview, consistency, cross_model, manifest)
    print(json.dumps({"runs": overview, "slots": len(slots), "name_matched_slots": sum(bool(slot["restaurant_id_name_match"]) for slot in slots), "top_names": all_names[:12]}, ensure_ascii=False))


if __name__ == "__main__":
    expanded = ROOT / "확장분석"
    if (expanded / "frame_freeze.json").exists():
        import subprocess
        import sys
        # Keep the fixed baseline files intact; render the expanded study instead.
        for script in ("analyze.py", "train_models.py", "validate.py", "write_report.py"):
            subprocess.run([sys.executable, str(expanded / script)], check=True)
    else:
        main()
