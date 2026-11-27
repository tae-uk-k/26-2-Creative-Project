"""현재 대화에서 CUA로 관측한 자료만 원본 형태로 내보낸다. 네트워크 요청 없음."""
from pathlib import Path
import base64
import io
import json
from PIL import Image

ROOT = Path(__file__).resolve().parent
LOG = Path(r'C:\Users\xodnr\.codex\sessions\2026\10\13\rollout-2026-10-13T12-58-36-01a13369-866a-7893-9bf7-f6cc462134bc.jsonl')
MARKER = 'MAP_MOCK_20261106 '
(ROOT / 'source').mkdir(exist_ok=True)
(ROOT / 'images').mkdir(exist_ok=True)
count = 0
for line in LOG.open(encoding='utf-8'):
    row = json.loads(line)
    p = row.get('payload', {})
    if row.get('type') != 'response_item' or p.get('type') != 'function_call_output':
        continue
    output = p.get('output', [])
    if not isinstance(output, list):
        continue
    records = []
    for block in output:
        if block.get('type') != 'input_text':
            continue
        text = block.get('text', '')
        for pos in [i + len(MARKER) for i in range(len(text)) if text.startswith(MARKER, i)]:
            try:
                value, _ = json.JSONDecoder().raw_decode(text[pos:])
            except json.JSONDecodeError:
                continue
            records.append(value)
            dest = ROOT / 'source' / (value['kind'] + ('_' + value['name'] if value['kind'] == 'screenshot' else '') + '.json')
            if not dest.exists():
                dest.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                count += 1
    shots = [r for r in records if r['kind'] == 'screenshot']
    images = [b for b in output if b.get('type') == 'input_image']
    for shot, imblock in zip(shots, images):
        intermediate = shot['name'] in {'kakao_comparison', 'google_comparison', 'google_comparison_final', 'google_after_render', 'google_after_menu_render'}
        folder = ROOT / 'images' / ('qa_intermediate' if intermediate else '')
        folder.mkdir(exist_ok=True)
        dest = folder / (shot['name'] + '.png')
        if imblock and not dest.exists():
            url = imblock['image_url']
            if isinstance(url, dict):
                url = url['url']
            im = Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1]))).convert('RGB')
            # Google: 개인 계정·저장 목록이 있는 바깥 영역만 제외. 공개 장소 화면은 원본 픽셀 그대로.
            if shot['name'] == 'google_original':
                im = im.crop((72, 0, 1280, im.height))
            im.save(dest)
            count += 1
print(json.dumps({'saved_new': count, 'folder': str(ROOT)}, ensure_ascii=False))
