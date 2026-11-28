"""Map-requested Korean CLI pilot. Never writes earlier experiment files."""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
EMPTY = Path(r'C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\cli_map_empty_20261016')
OLD = ROOT.parent / 'ai-visibility-experiment' / 'cli_한국어_탐색'
sys.path.insert(0, str(OLD))
from run_cli import extract_response

MODELS = {'codex': 'gpt-6.1-sol', 'agy': 'Gemini 3.8 Flash (Low)'}
MAPS = {'naver': '네이버 지도', 'kakao': '카카오맵', 'google': '구글 지도'}
AREAS = {'MD': '서울 명동', 'SS': '서울 성수동', 'MW': '서울 망원동과 망원시장 주변'}
LOCK = Lock()
SUFFIX = '''
지금 실제로 웹 검색해서 답해줘. 지점이 여러 개면 구분하고, 각 식당을 선정할 때 실제 사용한 출처 URL을 남겨줘.
지정 지도의 상세 페이지를 직접 읽었는지, 검색 결과에 표시된 지도 정보만 봤는지, 다른 사이트로 판단했는지 구분해줘.
지도 접근이 안 되면 그 사실을 명시해줘. 지도에 없거나 읽지 않은 소개문을 지어내지 말고, 상호를 넣은 지도 검색 링크를 직접 본 상세 페이지인 것처럼 쓰지 마.
확인된 식당이 부족하면 억지로 5곳으로 채우지 않아도 돼. 주소나 필드를 확인 못 했으면 null로 표시해줘.
최종 출력은 코드 블록 없이 아래 JSON 구조만 작성해줘. source_level은 direct_detail/search_snippet/other_sources/unverified 중 선택해줘.
{"access_note":"접근 상황","restaurants":[{"rank":1,"name":"상호","branch":null,"address":null,"reason":"선정 근거","map_url":null,"sources":["실제 근거 URL"],"source_level":"unverified","map_fields_read":["실제 확인한 필드명"],"map_text_excerpt":null}]}
로컬 파일·과거 대화·실험 자료는 읽거나 수정하지 말고 웹 검색과 공개 페이지 열람만 사용해줘. 다른 에이전트를 호출하지 마.
'''


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)


def initialize():
    EMPTY.mkdir(parents=True, exist_ok=True)
    prompts = []
    for map_id, map_label in MAPS.items():
        for area, area_label in AREAS.items():
            text = f'{map_label} 기준으로 {area_label}에서 한 끼 식사할 식당 5곳을 추천해줘. 디저트만 판매하는 카페는 제외해줘.' + SUFFIX
            prompts.append({'prompt_id': map_id + '_' + area, 'map_id': map_id, 'map_label': map_label,
                            'area_id': area, 'area_label': area_label, 'intent': 'general_meal', 'prompt': text})
    path = ROOT / 'prompts.json'
    payload = json.dumps(prompts, ensure_ascii=False, indent=2)
    if path.exists():
        assert path.read_text(encoding='utf-8') == payload, 'Frozen prompts changed'
    else:
        path.write_text(payload, encoding='utf-8')
    manifest = [{'run_id': f'MAP-20261016-{backend.upper()}-{p["prompt_id"]}-R1',
                 'backend': backend, 'requested_model': MODELS[backend], 'prompt_id': p['prompt_id'],
                 'map_id': p['map_id'], 'area_id': p['area_id'], 'repeat': 1, 'phase': 'access_pilot'}
                for backend in MODELS for p in prompts]
    random.Random(20261016).shuffle(manifest)
    write_csv(ROOT / 'run_manifest.csv', manifest)
    frozen = {'as_of_date': '2026-10-16', 'study_version': 'map-requested-cli-v1',
              'prompts_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pilot_cells': len(manifest),
              'candidate_names_given_to_model': False, 'old_experiment_results_combined': False,
              'empty_working_directory': str(EMPTY), 'models_requested': MODELS,
              'interpretation': 'Map-requested is not proof of map-body access; self-report is unverified'}
    (ROOT / 'design_freeze.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    return prompts, manifest


def build_command(backend, prompt):
    if backend == 'codex':
        return [shutil.which('codex') or 'codex', 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                '--sandbox', 'read-only', '--model', MODELS[backend], '-c', 'web_search="live"',
                '-c', 'model_reasoning_effort="low"', '-c', 'project_doc_max_bytes=0', '--json', prompt]
    return [shutil.which('agy') or 'agy', '--model', MODELS[backend], '--mode', 'plan',
            '--disable-slash-commands', '--output-format', 'stream-json', '-p', prompt]


def decode_json(text):
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    try:
        parsed = json.loads(text)
    except ValueError:
        match = re.search(r'\{[\s\S]*\}', text)
        try:
            parsed = json.loads(match[0]) if match else None
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) and isinstance(parsed.get('restaurants'), list) else None


def run_one(item, prompt, timeout):
    backend = item['backend']
    raw = ROOT / 'raw' / backend
    raw.mkdir(parents=True, exist_ok=True)
    attempt = 1
    stem = item['run_id']
    while (raw / (stem + '.jsonl')).exists():
        attempt += 1
        stem = item['run_id'] + f'-A{attempt}'
    stdout_file, stderr_file = raw / (stem + '.jsonl'), raw / (stem + '.stderr.txt')
    started = utc_now()
    tick = time.monotonic()
    timed_out = False
    helper_terminated = False
    with stdout_file.open('w', encoding='utf-8') as out, stderr_file.open('w', encoding='utf-8') as err:
        proc = subprocess.Popen(build_command(backend, prompt['prompt']), cwd=EMPTY, stdout=out, stderr=err,
                                env={**os.environ, 'NO_COLOR': '1'})
        while proc.poll() is None:
            partial = stdout_file.read_text(encoding='utf-8', errors='replace')
            terminal = False
            for line in partial.splitlines()[-5:]:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                terminal |= event.get('type') in ['turn.completed', 'turn.failed'] or event.get('event') == 'result'
            if terminal:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    helper_terminated = True
                    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=10)
                break
            if time.monotonic() - tick >= timeout:
                timed_out = True
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=10)
                break
            time.sleep(.5)
        proc.wait(timeout=15)
    stdout = stdout_file.read_text(encoding='utf-8', errors='replace')
    stderr = stderr_file.read_text(encoding='utf-8', errors='replace')
    response, events, searched, models = extract_response(stdout, backend)
    parsed = decode_json(response)
    restaurants = parsed.get('restaurants', []) if parsed else []
    completion = any(e.get('type') == 'turn.completed' for e in events) if backend == 'codex' else any(
        e.get('event') == 'result' and e.get('result', {}).get('status') == 'SUCCESS' for e in events)
    denied_actions = [a for e in events if isinstance(e.get('result'), dict) for a in e['result'].get('denied_actions', [])]
    status = 'completed' if completion and parsed is not None else 'tool_permission_denied' if denied_actions else 'format_error' if completion else 'technical_failure'
    if timed_out and not completion:
        status = 'timeout'
    result = {**item, 'attempt': attempt, 'study_version': 'map-requested-cli-v1', 'requested_model': MODELS[backend],
        'reported_models': models, 'prompt_text': prompt['prompt'], 'started_at_utc': started, 'finished_at_utc': utc_now(),
        'elapsed_seconds': round(time.monotonic() - tick, 1), 'return_code': proc.returncode,
        'provider_completed': completion, 'web_search_observed': searched, 'status': status, 'denied_actions': denied_actions,
        'recommendation_count': len(restaurants), 'parsed_answer': parsed, 'response': response,
        'raw_path': str(stdout_file), 'stderr_path': str(stderr_file), 'helper_terminated_after_completion': helper_terminated,
        'map_body_access_verified': False, 'map_access_status_requires_audit': True,
        'consumer_result': False, 'environment': 'current_cli_no_location_control', 'language': 'ko'}
    (raw / (stem + '.md')).write_text(response, encoding='utf-8')
    with LOCK:
        with (ROOT / 'attempts.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(json.dumps({k: result[k] for k in ['run_id', 'attempt', 'status', 'recommendation_count', 'web_search_observed', 'elapsed_seconds']}, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize-only', action='store_true')
    parser.add_argument('--skip-attempted', action='store_true')
    parser.add_argument('--backend', choices=['codex', 'agy', 'both'], default='both')
    parser.add_argument('--area', choices=list(AREAS))
    parser.add_argument('--map', choices=list(MAPS))
    parser.add_argument('--limit', type=int, default=18)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    prompts, manifest = initialize()
    if args.initialize_only:
        print(json.dumps({'pilot_cells': len(manifest), 'initialized': True}))
        return
    prior = [json.loads(l) for l in (ROOT / 'attempts.jsonl').read_text(encoding='utf-8').splitlines()] if (ROOT / 'attempts.jsonl').exists() else []
    completed = {r['run_id'] for r in prior if r['status'] == 'completed' or args.skip_attempted}
    tasks = [r for r in manifest if r['run_id'] not in completed and (args.backend == 'both' or r['backend'] == args.backend)
             and (not args.area or r['area_id'] == args.area) and (not args.map or r['map_id'] == args.map)][:args.limit]
    lookup = {p['prompt_id']: p for p in prompts}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(run_one, r, lookup[r['prompt_id']], args.timeout) for r in tasks]
        for job in as_completed(jobs):
            job.result()


if __name__ == '__main__':
    main()
