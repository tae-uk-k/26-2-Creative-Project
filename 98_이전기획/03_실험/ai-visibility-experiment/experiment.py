from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_PATH = BASE_DIR / "prompts.csv"
RESTAURANTS_PATH = BASE_DIR / "restaurants.csv"
MANIFEST_PATH = DATA_DIR / "run_manifest.csv"
PILOT_MANIFEST_PATH = DATA_DIR / "pilot_manifest.csv"
AGY_RESULTS_PATH = DATA_DIR / "agy_pilot.jsonl"
AGY_SUMMARY_PATH = DATA_DIR / "agy_pilot_summary.csv"

STUDY_VERSION = "baseline-v1-2026-10-07"
SEED = 20261007
REPEATS = 5
PLATFORMS = ("chatgpt_consumer", "gemini_consumer")
SCENARIOS = ("pre_trip_us", "in_korea")
AREAS = ("myeongdong", "seongsu", "mangwon")
AGY_DEFAULT = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
AGY_SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    prompts = read_csv(PROMPTS_PATH)
    restaurants = read_csv(RESTAURANTS_PATH)
    errors: list[str] = []

    prompt_ids = [row.get("prompt_id", "").strip() for row in prompts]
    if len(prompts) != 12:
        errors.append(f"prompts.csv must contain 12 rows, found {len(prompts)}")
    if len(set(prompt_ids)) != len(prompt_ids):
        errors.append("prompt_id values must be unique")

    prompts_by_area = Counter(row.get("area", "").strip() for row in prompts)
    for area in AREAS:
        if prompts_by_area[area] != 4:
            errors.append(f"{area} must have 4 prompts, found {prompts_by_area[area]}")
    for row in prompts:
        for scenario in SCENARIOS:
            if not row.get(scenario, "").strip():
                errors.append(f"{row.get('prompt_id')}: missing {scenario} text")

    restaurant_ids = [row.get("restaurant_id", "").strip() for row in restaurants]
    if len(restaurants) != 30:
        errors.append(f"restaurants.csv must contain 30 rows, found {len(restaurants)}")
    if len(set(restaurant_ids)) != len(restaurant_ids):
        errors.append("restaurant_id values must be unique")
    restaurants_by_area = Counter(row.get("area", "").strip() for row in restaurants)
    for area in AREAS:
        if restaurants_by_area[area] != 10:
            errors.append(
                f"{area} must have 10 restaurants, found {restaurants_by_area[area]}"
            )
    for row in restaurants:
        if not row.get("canonical_name_en", "").strip():
            errors.append(f"{row.get('restaurant_id')}: missing canonical_name_en")
        if row.get("prior_visibility_stratum") not in {"high", "mid", "low"}:
            errors.append(
                f"{row.get('restaurant_id')}: invalid prior_visibility_stratum"
            )

    if errors:
        raise ValueError("\n".join(f"- {error}" for error in errors))
    return prompts, restaurants


def build_manifest(
    output: Path = MANIFEST_PATH,
    repeats: int = REPEATS,
    phase_code: str = "B1",
) -> int:
    prompts, _ = validate_inputs()
    if repeats < 1 or repeats > REPEATS:
        raise ValueError(f"repeats must be between 1 and {REPEATS}")
    rows: list[dict[str, str | int]] = []
    platform_code = {"chatgpt_consumer": "CG", "gemini_consumer": "GM"}
    scenario_code = {"pre_trip_us": "PRE", "in_korea": "KOR"}

    for platform in PLATFORMS:
        for scenario in SCENARIOS:
            for prompt in prompts:
                for repeat in range(1, repeats + 1):
                    run_id = "-".join(
                        (
                            "HANOON",
                            phase_code,
                            platform_code[platform],
                            scenario_code[scenario],
                            prompt["prompt_id"],
                            f"R{repeat}",
                        )
                    )
                    rows.append(
                        {
                            "run_id": run_id,
                            "study_version": STUDY_VERSION,
                            "platform": platform,
                            "scenario": scenario,
                            "prompt_id": prompt["prompt_id"],
                            "area": prompt["area"],
                            "intent": prompt["intent"],
                            "repeat": repeat,
                            "prompt_text": prompt[scenario],
                            "random_order": 0,
                            "collected_at_iso": "",
                            "model_label": "",
                            "account_mode": "clean_unpersonalized",
                            "ip_country": "US" if scenario == "pre_trip_us" else "KR",
                            "location_permission": "off" if scenario == "pre_trip_us" else "on",
                            "raw_response_path": "",
                            "search_used": "",
                            "recommended_names": "",
                            "recommended_ranks": "",
                            "cited_urls": "",
                            "accuracy_status": "",
                            "notes": "",
                        }
                    )

    random.Random(SEED).shuffle(rows)
    for order, row in enumerate(rows, start=1):
        row["random_order"] = order

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def find_prompt(prompt_id: str, scenario: str) -> dict[str, str]:
    prompts = read_csv(PROMPTS_PATH)
    for prompt in prompts:
        if prompt["prompt_id"] == prompt_id:
            if scenario not in SCENARIOS:
                raise ValueError(f"Unsupported scenario: {scenario}")
            return prompt
    raise ValueError(f"Unknown prompt_id: {prompt_id}")


def ensure_ai_credit_overage_is_off(settings_path: Path = AGY_SETTINGS) -> None:
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot verify Antigravity credit setting: {exc}") from exc
    if settings.get("useG1Credits") is True:
        raise ValueError(
            "Antigravity AI credit overage is enabled. Turn it off before this pilot."
        )


def normalize_entity(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def restaurant_aliases(restaurant: dict[str, str]) -> list[str]:
    values = [restaurant.get("canonical_name_en", ""), restaurant.get("name_ko", "")]
    values.extend(restaurant.get("aliases", "").split("|"))
    return [normalized for value in values if (normalized := normalize_entity(value))]


def summarize_agy_pilot(input_path: Path, output_path: Path) -> int:
    prompts, restaurants = validate_inputs()
    prompt_areas = {prompt["prompt_id"]: prompt["area"] for prompt in prompts}
    if not input_path.exists():
        raise FileNotFoundError(f"Pilot result not found: {input_path}")

    records = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary_rows: list[dict[str, str | int | bool]] = []
    for record in records:
        area = prompt_areas.get(record["prompt_id"], "")
        response = record.get("raw_response", "")
        normalized_response = normalize_entity(response)
        matched: list[str] = []
        for restaurant in restaurants:
            if restaurant["area"] != area:
                continue
            if any(alias in normalized_response for alias in restaurant_aliases(restaurant)):
                matched.append(restaurant["restaurant_id"])
        summary_rows.append(
            {
                "prompt_id": record["prompt_id"],
                "scenario": record["scenario"],
                "repeat": record["repeat"],
                "area": area,
                "return_code": record["return_code"],
                "response_chars": len(response),
                "url_count": len(re.findall(r"https?://", response)),
                "sample_match_count": len(matched),
                "matched_restaurant_ids": "|".join(matched),
                "eligible_for_primary_visibility_analysis": False,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if summary_rows:
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
    return len(summary_rows)


def run_agy_pilot(
    prompt_id: str,
    scenario: str,
    repeats: int,
    model: str,
    executable: Path,
    output: Path = AGY_RESULTS_PATH,
) -> int:
    prompt_row = find_prompt(prompt_id, scenario)
    if not executable.exists():
        raise FileNotFoundError(f"Antigravity CLI not found: {executable}")
    if repeats < 1 or repeats > 5:
        raise ValueError("--repeats must be between 1 and 5")
    ensure_ai_credit_overage_is_off()

    prompt = (
        prompt_row[scenario]
        + "\n\nReturn only the answer. Do not create, edit, or delete any files."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with output.open("a", encoding="utf-8") as handle:
        for repeat in range(1, repeats + 1):
            started_at = datetime.now(timezone.utc).isoformat()
            process = subprocess.run(
                [str(executable), "--model", model, "-p", prompt],
                cwd=BASE_DIR.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            record = {
                "study_version": STUDY_VERSION,
                "backend": "antigravity_cli_engineering_pilot",
                "eligible_for_primary_visibility_analysis": False,
                "prompt_id": prompt_id,
                "scenario": scenario,
                "repeat": repeat,
                "model": model,
                "started_at_utc": started_at,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "return_code": process.returncode,
                "prompt_text": prompt_row[scenario],
                "raw_response": process.stdout.strip(),
                "stderr": process.stderr.strip(),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            if process.returncode != 0:
                raise RuntimeError(
                    f"Antigravity call failed on repeat {repeat}: {process.stderr.strip()}"
                )
            completed += 1
    return completed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="한눈 AI 노출 관찰실험 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="표본·질문 파일을 검증합니다.")

    manifest_parser = subparsers.add_parser(
        "build-manifest", help="240회 소비자 앱 실행표를 생성합니다."
    )
    manifest_parser.add_argument("--output", type=Path, default=MANIFEST_PATH)

    pilot_manifest_parser = subparsers.add_parser(
        "build-pilot-manifest", help="48회 소비자 앱 파일럿 실행표를 생성합니다."
    )
    pilot_manifest_parser.add_argument(
        "--output", type=Path, default=PILOT_MANIFEST_PATH
    )

    agy_parser = subparsers.add_parser(
        "agy-pilot", help="Antigravity로 공학 파일럿을 실행합니다."
    )
    agy_parser.add_argument(
        "--prompt-id",
        action="append",
        required=True,
        help="반복 지정 가능: --prompt-id MD01 --prompt-id SS01",
    )
    agy_parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    agy_parser.add_argument("--repeats", type=int, default=1)
    agy_parser.add_argument("--model", default="Gemini 3.8 Flash (Low)")
    agy_parser.add_argument(
        "--executable",
        type=Path,
        default=Path(os.environ.get("AGY_EXE", AGY_DEFAULT)),
    )
    agy_parser.add_argument("--output", type=Path, default=AGY_RESULTS_PATH)

    summary_parser = subparsers.add_parser(
        "summarize-agy", help="Antigravity 공학 파일럿의 표본 매칭을 요약합니다."
    )
    summary_parser.add_argument("--input", type=Path, default=AGY_RESULTS_PATH)
    summary_parser.add_argument("--output", type=Path, default=AGY_SUMMARY_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate":
            prompts, restaurants = validate_inputs()
            print(
                f"VALID prompts={len(prompts)} restaurants={len(restaurants)} "
                f"planned_runs={len(PLATFORMS) * len(SCENARIOS) * len(prompts) * REPEATS}"
            )
            return 0
        if args.command == "build-manifest":
            count = build_manifest(args.output)
            print(f"CREATED {args.output} rows={count}")
            return 0
        if args.command == "build-pilot-manifest":
            count = build_manifest(args.output, repeats=1, phase_code="P1")
            print(f"CREATED {args.output} rows={count}")
            return 0
        if args.command == "agy-pilot":
            count = 0
            for prompt_id in args.prompt_id:
                count += run_agy_pilot(
                    prompt_id=prompt_id,
                    scenario=args.scenario,
                    repeats=args.repeats,
                    model=args.model,
                    executable=args.executable,
                    output=args.output,
                )
            print(f"COMPLETED agy_pilot_runs={count} output={args.output}")
            return 0
        if args.command == "summarize-agy":
            count = summarize_agy_pilot(args.input, args.output)
            print(f"CREATED {args.output} rows={count}")
            return 0
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

