from pathlib import Path
from PIL import Image
import base64, io, json

ROOT=Path(__file__).resolve().parent
LOG=Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')
MARKER='VIRTUAL_GEO_20261106 '
count=0
for line in LOG.open(encoding='utf-8'):
 row=json.loads(line);p=row.get('payload',{})
 if row.get('type')!='response_item' or p.get('type')!='function_call_output' or not isinstance(p.get('output'),list):continue
 output=p['output'];shots=[]
 for b in output:
  if b.get('type')!='input_text':continue
  text=b.get('text','');pos=0
  while (pos:=text.find(MARKER,pos))>=0:
   pos+=len(MARKER)
   try:r,_=json.JSONDecoder().raw_decode(text[pos:])
   except json.JSONDecodeError:continue
   shots.append(r)
 for shot,block in zip(shots,[b for b in output if b.get('type')=='input_image']):
  dest=ROOT/'images'/(shot['name']+'.png')
  if dest.exists():continue
  url=block['image_url'];url=url['url'] if isinstance(url,dict) else url
  im=Image.open(io.BytesIO(base64.b64decode(url.split(',',1)[1]))).convert('RGB')
  im.save(dest);count+=1
print(json.dumps({'new_renders':count},ensure_ascii=False))
