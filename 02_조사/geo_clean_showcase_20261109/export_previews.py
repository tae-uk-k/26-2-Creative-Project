"""Save unmodified browser screenshots from this chat's own tool output."""
from pathlib import Path
import base64
import json
import re

ROOT = Path(__file__).resolve().parent
SESSION = Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')
NAMES = ['kakao-page-final', 'google-page-final', 'comparison-final']
images = None
prompts = {}
for line in SESSION.open(encoding='utf-8'):
    if not any(key in line for key in ('GEO_CLEAN_20261109 comparison-final', 'kakao_photo', 'google_photo')):
        continue
    payload = json.loads(line).get('payload', {})
    code = payload.get('arguments', '') or payload.get('input', '')
    if isinstance(code, str):
        for key, quoted in re.findall(r'\{key:"(kakao_photo|google_photo)",prompt:("(?:[^"\\]|\\.)*")\}', code):
            prompts[key] = json.loads(quoted)
    output = payload.get('output')
    if payload.get('type') != 'function_call_output' or not isinstance(output, list):
        continue
    text = '\n'.join(x.get('text', '') for x in output if x.get('type') == 'input_text')
    if 'GEO_CLEAN_20261109 comparison-final' in text:
        images = [x['image_url'] for x in output if x.get('type') == 'input_image']

assert images and len(images) == len(NAMES), 'Expected three final browser screenshots.'
(ROOT / 'images').mkdir(exist_ok=True)
files = []
for name, url in zip(NAMES, images):
    mime, encoded = url.split(',', 1)
    suffix = '.png' if 'image/png' in mime else '.jpg'
    file = ROOT / 'images' / (name + suffix)
    file.write_bytes(base64.b64decode(encoded))
    files.append(str(file.relative_to(ROOT)))

# A single-file preview remains viewable when iframes are restricted by a file viewer.
preview = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>구글·카카오 지도 정비 완성 예시</title><style>body{margin:0;background:#f2f3f2;font-family:Arial,"Malgun Gothic",sans-serif}nav{padding:14px 22px;display:flex;gap:22px;background:#fff;border-bottom:1px solid #ddd;font-size:13px}a{color:#314e43;text-decoration:none}img{display:block;max-width:1265px;width:100%;height:auto;margin:0 auto}</style><nav><a href="index.html">두 지도 비교</a><a href="google.html">Google 페이지</a><a href="kakao.html">카카오 페이지</a></nav><img alt="가상 식당 구글·카카오 지도 정비 예시 브라우저 검수 화면" src="' + images[-1] + '"></html>'
(ROOT / 'preview.html').write_text(preview, encoding='utf-8')
(ROOT / 'image_prompts.json').write_text(json.dumps({'mode': 'built-in image_gen', 'prompts': prompts}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'screenshots': files, 'prompts_saved': len(prompts), 'preview': 'preview.html'}, ensure_ascii=False))
