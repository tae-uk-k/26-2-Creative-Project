"""Korean CLI observation; consumer experiment files are never modified."""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAVE_LOCK = Lock()
EMPTY = Path(r"C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\cli_empty")
QUESTIONS = [
    ("MD01", "myeongdong", "서울 명동에서 현재 운영 중인 식당 5곳을 추천해줘. 음식 종류, 1인 예상 가격과 추천 이유를 알려줘."),
    ("MD02", "myeongdong", "명동에서 국제적인 체인점보다 현지 한식을 먹고 싶어. 1인 2만 5천 원 이하로 먹을 수 있는 현재 운영 중인 식당 5곳과 대표 메뉴, 가격을 추천해줘."),
    ("MD03", "myeongdong", "명동에서 평일 저녁에 혼자 밥을 먹으려고 해. 혼자 이용하기 편한 현재 운영 중인 식당 5곳과 음식 종류, 가격대를 추천해줘."),
    ("MD04", "myeongdong", "명동에서 국수, 만두, 국밥, 고기구이, 한정식 같은 전통 한식을 먹을 식당 5곳을 추천해줘. 현재 운영 중인 곳의 대표 메뉴와 예상 가격을 알려줘."),
    ("SS01", "seongsu", "서울 성수동에서 식사하기 좋은 현재 운영 중인 식당 5곳을 추천해줘. 디저트 카페만 하는 곳은 제외하고 음식 종류, 1인 예상 가격과 추천 이유를 알려줘."),
    ("SS02", "seongsu", "성수동에서 1인 2만 5천 원 이하로 한식 점심을 먹을 수 있는 현재 운영 중인 식당 5곳과 대표 메뉴, 가격을 추천해줘."),
    ("SS03", "seongsu", "성수동에서 저녁을 먹고 싶어. 한식이나 현대적인 요리 중 동네의 개성이 느껴지는 현재 운영 중인 식당 5곳과 음식 종류, 가격대를 추천해줘."),
    ("SS04", "seongsu", "성수동에서 혼자 식사하기 편하고 메뉴, 가격, 위치 정보를 확인하기 쉬운 현재 운영 중인 식당 5곳을 추천해줘."),
    ("MW01", "mangwon", "망원시장과 주변 망원동에서 제대로 된 한 끼나 든든한 시장 음식을 먹을 수 있는 현재 운영 중인 가게 5곳과 음식 종류, 가격을 추천해줘."),
    ("MW02", "mangwon", "망원시장 주변에서 1인 1만 5천 원 이하로 현지 음식을 먹을 수 있는 현재 운영 중인 가게 5곳과 주문할 메뉴, 가격을 추천해줘."),
    ("MW03", "mangwon", "망원시장 주변에서 튀김, 만두, 국수, 호떡 같은 한국 시장 음식을 먹기 좋은 현재 운영 중인 가게 5곳과 대표 메뉴, 가격을 추천해줘."),
    ("MW04", "mangwon", "망원동에서 간식 말고 앉아서 점심이나 저녁 한 끼를 먹을 수 있는 현재 운영 중인 식당 5곳과 음식 종류, 가격대를 추천해줘."),
]
SUFFIX = '''
최신 웹 정보를 실제로 검색해서 답해줘. 가게나 정보를 지어내지 말고 지점이 여러 개면 지점을 구분해줘. 각 추천을 뒷받침하는 실제 출처 URL을 포함해줘. 확인되지 않는 주소나 가격은 null로 표시해줘.
최종 답은 설명이나 코드 블록 없이 다음 구조의 JSON만 작성해줘:
{"restaurants":[{"rank":1,"name":"상호","branch":"지점 또는 null","address":"주소 또는 null","cuisine":"음식 종류","price":"1인 가격 또는 null","reason":"추천 이유","sources":["https://출처"]}]}
로컬 파일과 과거 대화는 읽거나 수정하지 말고 웹 검색만 사용해줘. 다른 에이전트를 호출하지 마.
'''
MODELS = {"codex": "gpt-6.1-sol", "gemini": "gemini-3-flash-preview", "agy": "Gemini 3.8 Flash (Low)"}


def command(backend: str, prompt: str) -> list[str]:
    if backend == "codex":
        return [shutil.which("codex") or "codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--model", MODELS[backend], "-c", 'web_search="live"', "-c", 'model_reasoning_effort="low"', "-c", "project_doc_max_bytes=0", "--json", prompt]
    if backend == "gemini":
        bundle = Path(os.environ["APPDATA"]) / "npm/node_modules/@google/gemini-cli/bundle/gemini.js"
        return [shutil.which("node") or "node", str(bundle), "--model", MODELS[backend], "--prompt", prompt, "--output-format", "stream-json", "--policy", str(ROOT / "web_only.toml"), "--extensions", "none"]
    return [shutil.which("agy") or "agy", "--model", MODELS[backend], "--mode", "plan", "--disable-slash-commands", "--output-format", "stream-json", "-p", prompt]


def extract_response(stdout: str, backend: str) -> tuple[str, list[dict], bool, list[str]]:
    events, chunks, search_used, actual_models = [], [], False, set()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)
        if backend == "codex":
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                chunks.append(item.get("text", ""))
            if item.get("type") == "web_search":
                search_used = True
        elif backend == "gemini":
            if event.get("type") == "message" and event.get("role") == "assistant":
                chunks.append(event.get("content", ""))
            if event.get("type") == "tool_use" and event.get("tool_name") == "google_web_search":
                search_used = True
            if event.get("type") == "init" and event.get("model"):
                actual_models.add(event["model"])
            models = event.get("stats", {}).get("models", {})
            actual_models.update(models)
        else:
            if event.get("event") == "result" and isinstance(event.get("result"), dict):
                result = event["result"]
                if isinstance(result.get("response"), str):
                    chunks.append(result["response"])
            if event.get("type") == "result" and isinstance(event.get("result"), str):
                chunks.append(event["result"])
            if event.get("event") == "init" and event.get("init", {}).get("model"):
                actual_models.add(event["init"]["model"])
            step = event.get("step_update", {})
            if event.get("event") == "step_update" and step.get("step_type") == "tool":
                serialized = json.dumps(step, ensure_ascii=False)
                if "search_web" in serialized or "web_search" in serialized:
                    search_used = True
    return "\n".join(chunks).strip(), events, search_used, sorted(actual_models)


def decode_answer(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    left, right = text.find("{"), text.rfind("}")
    if left < 0:
        return []
    try:
        data = json.loads(text[left:right + 1])
    except ValueError:
        return []
    rows = data.get("restaurants", [])
    return rows if isinstance(rows, list) and all(isinstance(row, dict) for row in rows) else []


def run_one(backend: str, question: tuple, repeat: int, timeout: int) -> dict:
    prompt_id, area, question_text = question
    prompt = question_text + SUFFIX
    run_id = f"CLI-KO-{backend.upper()}-{prompt_id}-R{repeat}"
    rawdir = ROOT / "raw" / backend
    rawdir.mkdir(parents=True, exist_ok=True)
    attempt = 1
    raw_id = run_id
    while (rawdir / f"{raw_id}.jsonl").exists():
        attempt += 1
        raw_id = f"{run_id}-A{attempt}"
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    stdout_path = rawdir / f"{raw_id}.jsonl"
    stderr_path = rawdir / f"{raw_id}.stderr.txt"
    timed_out, helper_terminated_after_completion = False, False
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(command(backend, prompt), cwd=EMPTY, stdout=stdout_handle, stderr=stderr_handle, env={**os.environ, "NO_COLOR": "1"})
        while process.poll() is None:
            elapsed = time.monotonic() - tick
            partial = stdout_path.read_text(encoding="utf-8", errors="replace")
            terminal = False
            for line in partial.splitlines()[-4:]:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                terminal = terminal or event.get("type") in ("turn.completed", "turn.failed") or event.get("event") == "result"
            if terminal:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    helper_terminated_after_completion = True
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
                break
            if elapsed >= timeout:
                timed_out = True
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
                break
            time.sleep(0.5)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    response, events, search_used, actual_models = extract_response(stdout, backend)
    (rawdir / f"{raw_id}.md").write_text(response, encoding="utf-8")
    recommendations = decode_answer(response)
    status = "success" if process.returncode == 0 and len(recommendations) == 5 else "response_format_error"
    if process.returncode != 0:
        status = "technical_failure"
    if timed_out:
        status = "timeout"
    if helper_terminated_after_completion:
        status = "completed_output_helper_terminated"
    process_status = status
    provider_completed = any(event.get("type") == "turn.completed" for event in events) if backend == "codex" else any(event.get("event") == "result" and event.get("result", {}).get("status") == "SUCCESS" for event in events)
    if provider_completed and len(recommendations) == 5 and search_used:
        status = "success"
    record = {"study_version": "cli-ko-exploratory-v1", "run_id": run_id, "attempt": attempt, "backend": backend, "requested_model": MODELS[backend], "reported_models": actual_models, "prompt_id": prompt_id, "area": area, "repeat": repeat, "prompt_text": prompt, "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic() - tick, 1), "return_code": process.returncode, "status": status, "process_status": process_status, "provider_completed": provider_completed, "web_search_observed": search_used, "recommendations": recommendations, "response": response, "raw_path": str(rawdir / f"{raw_id}.jsonl"), "error_excerpt": stderr[-2500:] if process.returncode else "", "event_count": len(events), "environment": "current_cli_not_location_controlled", "language": "ko", "consumer_result": False}
    with SAVE_LOCK:
        with (ROOT / f"results_{backend}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({k: record[k] for k in ("run_id", "status", "web_search_observed", "elapsed_seconds")}, ensure_ascii=False), flush=True)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=list(MODELS), required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--only", help="Comma-separated prompt IDs")
    parser.add_argument("--min-repeat", type=int, default=1)
    parser.add_argument("--batch", default="extension-2026-10-13")
    args = parser.parse_args()
    EMPTY.mkdir(parents=True, exist_ok=True)
    with (ROOT / "prompts_ko.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["prompt_id", "area", "prompt_text"])
        writer.writerows((pid, area, text + SUFFIX) for pid, area, text in QUESTIONS)
    result_path = ROOT / f"results_{args.backend}.jsonl"
    done = set()
    if result_path.exists():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            from summarize import reviewed_response
            row = reviewed_response(json.loads(line))
            if row["status"] == "success":
                done.add((row["prompt_id"], row["repeat"]))
    jobs = [(q, repeat) for repeat in range(args.min_repeat, args.repeats + 1) for q in QUESTIONS if (q[0], repeat) not in done and (not args.only or q[0] in args.only.split(","))]
    random.Random(20261013).shuffle(jobs)
    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_jobs = {pool.submit(run_one, args.backend, question, repeat, args.timeout): (question, repeat) for question, repeat in jobs[:args.limit]}
            failures = 0
            for future in as_completed(future_jobs):
                row = future.result()
                failures = failures + 1 if row["status"] != "success" else 0
                if failures >= 3:
                    for pending in future_jobs:
                        pending.cancel()
                    print("STOPPED_AFTER_THREE_CONSECUTIVE_FAILURES", flush=True)
                    break
        return
    failures = 0
    for question, repeat in jobs[:args.limit]:
        row = run_one(args.backend, question, repeat, args.timeout)
        failures = failures + 1 if row["status"] != "success" else 0
        if failures >= 3:
            print("STOPPED_AFTER_THREE_CONSECUTIVE_FAILURES", flush=True)
            break


if __name__ == "__main__":
    main()
