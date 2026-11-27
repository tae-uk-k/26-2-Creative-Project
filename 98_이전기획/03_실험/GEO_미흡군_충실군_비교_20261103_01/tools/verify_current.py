"""Verify actual current state, source hashes and the closed measurement gate."""
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
checks=[]

def check(name,passed,detail):
    checks.append(dict(name=name,passed=bool(passed),detail=detail))

with (ROOT/'90셀_실행계획.csv').open(encoding='utf-8-sig',newline='') as f:
    schedule=list(csv.DictReader(f))
check('고유 측정 셀90개',len(schedule)==90 and len({r['cell_id'] for r in schedule})==90,'실행 계획이며 실제 호출 수와 구분')
check('질문에 표본·분류 미포함',all('미흡군' not in r['prompt'] and '충실군' not in r['prompt'] and 'GEO' not in r['prompt'] for r in schedule),'9개 자연어 질문, 반복10')
check('실제 식당 원문 없음',not list((ROOT/'raw').iterdir()),'추천 세션 미시작')
guard=subprocess.run([sys.executable,str(ROOT/'tools'/'study.py'),'measure'],capture_output=True,text=True,encoding='utf-8')
check('집단 미확정 측정 차단',guard.returncode!=0 and '확정 매장 집단 없음' in guard.stderr and not list((ROOT/'raw').iterdir()),'측정 전 검증에서 중단, 가짜 호출·실패 없음')
ready=[]
for manifest_path in sorted((ROOT/'readiness').glob('*.manifest.json')):
    m=json.loads(manifest_path.read_text(encoding='utf-8'))
    raw=ROOT/m['raw_path']
    check('준비성 원문 무변경 '+m['attempt_id'],hashlib.sha256(raw.read_bytes()).hexdigest()==m['raw_sha256'],'원문 SHA256')
    events=[json.loads(l) for l in raw.read_text(encoding='utf-8').splitlines()]
    errors=[e for e in events if e.get('type') in ['error','turn.failed']]
    finals=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    ready.append(dict(attempt_id=m['attempt_id'],started_at=m['started_at'],ended_at=m['ended_at'],returncode=m['returncode'],
        model_requested=m['model_requested'],model_snapshot=None,raw_file=m['raw_path'],
        status='model_capacity_failure' if errors else 'process_completed_map_access_failed',
        final_response=finals[-1] if finals else '',included_in_restaurant_measurement=False))
check('준비성 점검 실제2회',len(ready)==2,'첫 호출 용량 오류, 두 번째 프로세스 정상 종료이나 지도 접근 실패')
latest=ready[-1] if ready else {}
check('실제 지도 접근 성공으로 오인하지 않음',latest.get('returncode')==0 and '접근 실패' in latest.get('final_response',''),'프로세스 성공과 지도 접근 성공을 구분')
old=ROOT.parent/'GEO_두집단_지도비교_20261103'
preserved=0;changed=[]
with (old/'산출물_목록_해시.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        p=old/r['path']
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']:preserved+=1
        else:changed.append(r['path'])
check('기존 실험 보존',not changed and preserved>0,dict(unchanged_files=preserved,changed_files=changed))
arithmetic=subprocess.run([sys.executable,str(ROOT/'tools'/'analyze.py'),'--selfcheck'],capture_output=True,text=True,encoding='utf-8')
check('등장률 계산 검증',arithmetic.returncode==0,arithmetic.stdout.strip())
status=json.loads((ROOT/'analysis'/'현재상태'/'분석상태.json').read_text(encoding='utf-8'))
check('실측 미완료·분모0 유지',status['actual_attempts']==0 and status['unstarted_cells']==90 and status['exposure_A_pct'] is None and status['exposure_B_pct'] is None,'미실행90을 실패90 또는 노출0%로 표시하지 않음')
result=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),checks=checks,
    readiness=ready,research_completed=False,blocking_condition='Work local browser disabled; both map detail access unavailable through web tool; CLI readiness also reported both map access failures.')
with (ROOT/'analysis'/'현재상태'/'근거_실행검수.json').open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(passed=result['passed'],checks=len(checks),old_files_preserved=preserved,
    readiness_attempts=len(ready),actual_restaurant_attempts=0,research_completed=False),ensure_ascii=False))
if not result['passed']:raise SystemExit(1)
