"""Save only our already-observed public browser capture messages from this chat log."""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MARK='GEO20261103_CAPTURE '
SESSION=Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')

def main():
    out=ROOT/'browser_observed.jsonl'
    existing=[json.loads(l) for l in out.read_text(encoding='utf-8').splitlines()] if out.exists() else []
    keys={hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest() for r in existing}
    new=[]
    with SESSION.open(encoding='utf-8') as handle:
        for line in handle:
            if MARK not in line or 'function_call_output' not in line:continue
            try:r=json.loads(line)
            except ValueError:continue
            p=r.get('payload',{})
            if r.get('type')!='response_item' or p.get('type')!='function_call_output':continue
            output=p.get('output','')
            if isinstance(output,list):output='\n'.join(x.get('text','') for x in output if isinstance(x,dict))
            if not isinstance(output,str):continue
            for match in re.finditer(re.escape(MARK),output):
                try:record=json.JSONDecoder().raw_decode(output[match.end():])[0]
                except ValueError:continue
                if not isinstance(record,dict) or not record.get('platform'):continue
                key=hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                if key not in keys:new.append(record);keys.add(key)
    with out.open('a',encoding='utf-8') as f:
        for r in new:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(json.dumps({'new_capture_records':len(new),'total_capture_records':len(existing)+len(new)},ensure_ascii=False))

if __name__=='__main__':main()
