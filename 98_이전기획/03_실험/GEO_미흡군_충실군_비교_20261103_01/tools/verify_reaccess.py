"""Validate this real checkpoint and preserve all existing checkpoint files."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'analysis'/'재접근_상세검수_20261103_01'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

checks=[]
def check(name,passed,detail=''):
    checks.append(dict(name=name,passed=bool(passed),detail=detail))

state=json.loads((DEST/'검수된_현재상태.json').read_text(encoding='utf-8'))
schedule=rows(ROOT/'90셀_실행계획.csv')
check('90 unique planned cells',len(schedule)==90 and len({r['cell_id'] for r in schedule})==90)
check('Restaurant measurements not invented',not list((ROOT/'raw').iterdir()) and state['actual_restaurant_attempts']==0 and state['restaurant_measurement_failures']==0 and state['unstarted_cells']==90)
check('Unestimable rates remain null',all(state[k] is None for k in ['exposure_A_pct','exposure_B_pct','difference_B_minus_A_pp']))
check('No finalized cohort inferred from partial review',not rows(ROOT/'매장_집단_매칭표.csv') and state['finalized_pairs']==0)
probes=json.loads((DEST/'CLI_중립점검_원시이벤트검수.json').read_text(encoding='utf-8'))
check('Four separate real neutral attempts',len(probes)==4 and len({p['attempt_id'] for p in probes})==4 and not any(p['included_in_90'] for p in probes))
check('Neutral outcomes audited from raw events',Counter(p['outcome'] for p in probes)=={'model_failure':1,'map_access_failure':3} and sum(p['internal_error_results'] for p in probes)==8)
raw_ok=True
for mpath in (ROOT/'readiness').glob('*.manifest.json'):
    m=json.loads(mpath.read_text(encoding='utf-8'))
    raw_ok &= sha(ROOT/m['raw_path'])==m['raw_sha256']
    raw_ok &= sha(ROOT/m['stderr_path'])==m['stderr_sha256']
check('All CLI response and stderr hashes unchanged',raw_ok)
details=rows(DEST/'상세_근거목록.csv')
photos=rows(DEST/'사진_근거목록.csv')
check('Archived evidence hashes intact',all(sha(ROOT/r['evidence_file'])==r['sha256'] for r in details+photos))
check('Photo storage differs from visual review',len(photos)==40 and sum(p['visually_read']=='True' for p in photos)==13)
profiles=rows(DEST/'후보_상세관측표.csv')
check('Detail scope counts',len(profiles)==13 and sum(p['google_detail']=='True' for p in profiles)==6 and len(details)==40)
frame=ROOT/'analysis'/'음식별확대_v3_사전범위적용'
cards=rows(frame/'native_cards.csv')
check('Search query coverage and windows',len(cards)==991 and len({(r['area_id'],r['query']) for r in cards})==15 and all(int(r['rank'])<=(60 if r['query'].endswith('음식점') else 30) for r in cards))
links=rows(DEST/'후보_조사표_미확정.csv')
check('Candidate links are not verified stores',len(links)==260 and len({r['candidate_id'] for r in links})==149 and all(r['identity_verified']=='False' and not r['group'] and not r['pair_id'] for r in links))
scores=rows(DEST/'GEO_항목별점수_부분검수.csv')
sums=Counter()
for r in scores:
    sums[r['store_id']]+=int(r['score'])
    source=json.loads((ROOT/r['evidence_file']).read_text(encoding='utf-8'))
    if source['section']!='menu_photo_bundle':assert r['quote'] in source['body']
check('Partial scores have evidence and total four',len(scores)==6 and list(sums.values())==[4,4] and all(r['primary_analysis_included']=='False' for r in scores))
report=ROOT/'재진행보고서_20261103_미완료.md'
text=report.read_text(encoding='utf-8')
local_links=[u for u in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text) if not u.startswith(('https://','http://'))]
check('Report local evidence links resolve',all((ROOT/u).is_file() for u in local_links),local_links)
external_links=[u for u in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text) if u.startswith(('https://','http://'))]
observed_urls={json.loads((ROOT/r['evidence_file']).read_text(encoding='utf-8'))['url'] for r in details}
check('Report external links actually observed',all(u in observed_urls for u in external_links))
old=ROOT.parent/'GEO_두집단_지도비교_20261103'
previous=rows(old/'산출물_목록_해시.csv')
check('Prior experiment manifest unchanged',len(previous)==85 and all(sha(old/r['path'])==r['sha256'] for r in previous))
result=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),checks=checks,research_completed=False)
with (DEST/'최신_정합성검수_v2.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
inventory=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts:
        inventory.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)))
with (ROOT/'산출물_목록_해시_재접근_20261103_v2.csv').open('x',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,['path','bytes','sha256']);w.writeheader();w.writerows(inventory)
print(json.dumps(dict(passed=result['passed'],checks=len(checks),inventory_files=len(inventory),failed=[c['name'] for c in checks if not c['passed']]),ensure_ascii=False))
if not result['passed']:raise SystemExit(1)
