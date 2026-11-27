"""검수한 브라우저 렌더를 원본 픽셀과 결합해 비교용 PNG를 만든다."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont, ImageChops

ROOT = Path(__file__).resolve().parent
IMAGES = ROOT / 'images'
font = ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf', 17)
small = ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf', 13)

k_before = Image.open(IMAGES / 'kakao_original.png').convert('RGB')
k_render = Image.open(IMAGES / 'kakao_after_render.png').convert('RGB')
assert k_before.size == k_render.size == (1280, 720)
k_after = k_render.copy()
# 메뉴 설명과 무관한 헤더/메뉴판은 원본 캡처 픽셀을 보존한다.
k_after.paste(k_before.crop((0, 0, 1280, 295)), (0, 0))
k_after.save(IMAGES / 'kakao_after.png')

g_before = Image.open(IMAGES / 'google_original.png').convert('RGB')
g_render = Image.open(IMAGES / 'google_after_menu_final.png').convert('RGB')
assert g_before.size == (1208, 765) and g_render.size == (600, 700)
g_after = g_before.copy()
# 교체한 설명과 자연스럽게 이동한 구분선 이외의 원본 지도 픽셀은 바꾸지 않는다.
g_after.paste(g_render.crop((0, 207, 408, 342)), (0, 207))
g_after.save(IMAGES / 'google_after.png')

def compare(name, title, a, b, crop):
    a, b = a.crop(crop), b.crop(crop)
    w, h = a.size
    page = Image.new('RGB', (w * 2 + 48, h + 93), '#f3f4f5')
    draw = ImageDraw.Draw(page)
    draw.text((16, 12), title + '  ·  원본 화면 기반 정비 시안', font=font, fill='#202124')
    for i, (picture, label) in enumerate(((a, 'BEFORE · 실제 관측 화면'), (b, 'AFTER · 정비 시안'))):
        x = 16 + i * (w + 16)
        draw.rectangle((x - 1, 48, x + w, 77 + h), fill='white', outline='#dfe1e5')
        draw.text((x + 12, 54), label, font=small, fill='#3c4043')
        page.paste(picture, (x, 77))
    page.save(IMAGES / name)

compare('kakao_before_after.png', '카카오맵 · 파르코 서울숲점', k_before, k_after, (340, 0, 940, 720))
compare('google_before_after.png', 'Google 지도 · 힛사츠와자', g_before, g_after, (0, 0, 600, 470))

def equal_outside_region(a, b, region):
    delta = ImageChops.difference(a, b)
    ImageDraw.Draw(delta).rectangle((region[0], region[1], region[2]-1, region[3]-1), fill=0)
    return delta.getbbox() is None

qa = {
    'google_original_pixels_unchanged_outside_description_region': equal_outside_region(g_before, g_after, (0,207,408,342)),
    'kakao_header_and_menu_board_pixels_unchanged': ImageChops.difference(k_before.crop((0,0,1280,295)), k_after.crop((0,0,1280,295))).getbbox() is None,
    'kakao_native_before_ui_difference_bbox': ImageChops.difference(k_before, Image.open(IMAGES / 'kakao_before_render.png').convert('RGB')).getbbox(),
    'note': '카카오 DOM 재현과 원본의 작은 차이는 세 번째 메뉴판 사진 주변에 한정. 비교 PNG에서는 정비와 무관한 상단 원본 픽셀 보존.',
    'preview_files': ['images/kakao_before_after.png', 'images/google_before_after.png'],
}
assert qa['google_original_pixels_unchanged_outside_description_region'] and qa['kakao_header_and_menu_board_pixels_unchanged']
(ROOT / 'image_qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(qa, ensure_ascii=False))
