"""Provider/tool readiness check; no study restaurant names, regions, or hypotheses."""
import json
import os
import shutil
import subprocess
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EMPTY=Path(r'C:\Users\xodnr\.codex\visualizations\2026\10\13\01a13369-866a-7893-9bf7-f6cc462134bc\geo_groups_20261103_empty')
MODEL='gpt-6.1-sol'

def main():
    EMPTY.mkdir(parents=True,exist_ok=True)
    directory=ROOT/'readiness'
    directory.mkdir(exist_ok=True)
    stem=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    command=[shutil.which('codex'),'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
             '--sandbox','read-only','--model',MODEL,'-c','web_search="live"','-c','model_reasoning_effort="low"',
             '-c','project_doc_max_bytes=0','--json',
             '웹 검색으로 카카오맵 서비스의 공식 홈페이지 URL 한 개를 확인해줘. 가게를 검색하지 마. 로컬 파일·터미널·과거 대화·다른 에이전트를 사용하지 마. 최종 답변은 {"url":"https://..."} JSON만 써줘.']
    with (directory/(stem+'.jsonl')).open('w',encoding='utf-8') as out,(directory/(stem+'.stderr.txt')).open('w',encoding='utf-8') as err:
        proc=subprocess.run(command,cwd=EMPTY,stdout=out,stderr=err,timeout=240,env={**os.environ,'NO_COLOR':'1'})
    print(json.dumps({'returncode':proc.returncode,'model_requested':MODEL,'readiness_raw':str(directory/(stem+'.jsonl'))}))

if __name__=='__main__':main()
