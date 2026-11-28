"""Export this chat's observed browser DOM and screenshots; no network requests."""
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSION = Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')
SOURCE = ROOT / 'source'
SOURCE.mkdir(exist_ok=True)
(ROOT / 'images').mkdir(exist_ok=True)
count = {}
for line in SESSION.open(encoding='utf-8'):
    if 'NATIVE_DATA ' not in line and 'NATIVE_MAPS_20261109 ' not in line:
        continue
    d = json.loads(line).get('payload', {})
    if d.get('type') != 'function_call_output' or not isinstance(d.get('output'), list):
        continue
    blocks = d['output']
    text = '\n'.join(x.get('text', '') for x in blocks if x.get('type') == 'input_text')
    for match in re.finditer(r'NATIVE_DATA ([a-z0-9-]+) ', text):
        name = match.group(1)
        value = text[match.end():]
        try:
            obj, end = json.JSONDecoder().raw_decode(value)
            value = value[:end]
        except json.JSONDecodeError:
            continue
        (SOURCE / f'{name}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        if obj.get('html'):
            (SOURCE / f'{name}.html').write_text(obj['html'], encoding='utf-8')
        if obj.get('main'):
            (SOURCE / f'{name}.html').write_text(obj['main'], encoding='utf-8')
        count[name] = len(value)
    markers = re.findall(r'NATIVE_MAPS_20261109 ([a-z0-9-]+)', text)
    images = [x['image_url'] for x in blocks if x.get('type') == 'input_image']
    if len(markers) == len(images):
        for name, url in zip(markers, images):
            mime, data = url.split(',', 1)
            suffix = '.png' if 'image/png' in mime else '.jpg'
            (ROOT / 'images' / (name + suffix)).write_bytes(base64.b64decode(data))
            count[name] = 'screenshot'
print(json.dumps(count, ensure_ascii=False))
