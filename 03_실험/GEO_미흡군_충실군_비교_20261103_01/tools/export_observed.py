"""Export only our public GEO_RUN01_CAPTURE browser observations from this chat."""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOG=Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')
OUT=ROOT/'evidence'/'browser_observed.jsonl'
decoder=json.JSONDecoder()
known=set()
if OUT.exists():
    for line in OUT.read_text(encoding='utf-8').splitlines():
        known.add(hashlib.sha256(line.encode()).hexdigest())
count=0
with LOG.open(encoding='utf-8') as source,OUT.open('a',encoding='utf-8') as dest:
    for line in source:
        try:event=json.loads(line)
        except json.JSONDecodeError:continue
        p=event.get('payload',{})
        if event.get('type')!='response_item' or p.get('type')!='function_call_output':continue
        output=p.get('output','')
        if isinstance(output,list):output='\n'.join(b.get('text','') for b in output if isinstance(b,dict))
        if not isinstance(output,str):continue
        for marker in re.finditer('GEO_RUN01_CAPTURE ',output):
            try:record,end=decoder.raw_decode(output[marker.end():])
            except json.JSONDecodeError:continue
            if not isinstance(record,dict) or 'platform' not in record:continue
            serialized=json.dumps(record,ensure_ascii=False,separators=(',',':'),sort_keys=True)
            key=hashlib.sha256(serialized.encode()).hexdigest()
            if key not in known:
                known.add(key);dest.write(serialized+'\n');count+=1
print(json.dumps({'added':count,'total':len(known)},ensure_ascii=False))
