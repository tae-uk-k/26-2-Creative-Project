"""Package the observed browser screenshots; crop only browser UI boundaries."""
from pathlib import Path
import base64
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
names = ['google-final-home', 'kakao-final-home', 'google-final-menu', 'kakao-final-menu', 'google-final-info']
font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 19)
small = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 12)
g = Image.open(ROOT / 'images/google-final-home.jpg').convert('RGB').crop((72,0,480,720))
k = Image.open(ROOT / 'images/kakao-final-home.jpg').convert('RGB').crop((339,80,941,1335))
gm = Image.open(ROOT / 'images/google-final-menu.jpg').convert('RGB').crop((72,0,480,720))
km = Image.open(ROOT / 'images/kakao-final-menu.jpg').convert('RGB').crop((339,0,941,720))

for filename, left, right in [('native-home-comparison.jpg',g,k),('native-menu-comparison.jpg',gm,km)]:
    canvas = Image.new('RGB', (1066, max(left.height,right.height)+70), '#f4f5f6')
    draw = ImageDraw.Draw(canvas)
    draw.text((16,12),'Google 지도',fill='#34404a',font=font)
    draw.text((448,12),'카카오맵',fill='#34404a',font=font)
    draw.text((16,42),'브라우저 캡처 · 가상 매장 정보',fill='#7d858b',font=small)
    canvas.paste(left,(16,70))
    canvas.paste(right,(448,70))
    canvas.save(ROOT / 'images' / filename,quality=94)

sections = []
for name in names:
    p = ROOT / 'images' / (name + '.jpg')
    data = 'data:image/jpeg;base64,' + base64.b64encode(p.read_bytes()).decode()
    label = {'google-final-home':'Google 개요','kakao-final-home':'카카오 홈','google-final-menu':'Google 메뉴','kakao-final-menu':'카카오 메뉴','google-final-info':'Google 정보'}[name]
    sections.append(f'<section><h2>{label}</h2><img alt="{label} 실제 브라우저 검수 화면" src="{data}"></section>')
page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>실제 지도 HTML 기반 정비 예시 캡처</title><style>body{margin:0;background:#f5f5f5;font:14px Arial,"Malgun Gothic",sans-serif;color:#333}header{padding:18px 24px;background:white;border-bottom:1px solid #ddd}a{color:#245b96}section{max-width:1280px;margin:28px auto;background:white;border:1px solid #ddd}h2{font-size:16px;padding:0 20px}img{display:block;width:100%;height:auto}p{margin:8px 0;color:#777;font-size:12px}</style><header><b>실제 지도 HTML 기반 · 브라우저 검수 캡처</b><p>가상 식당 정보. 공개 원본 HTML·CSS를 사용한 상세 화면.</p><a href="index.html">작동하는 예시 열기</a> · <a href="추가입력항목_조사.md">추가 입력 항목 조사표</a></header>' + ''.join(sections) + '</html>'
(ROOT / 'preview.html').write_text(page,encoding='utf-8')
qa = json.loads((ROOT / 'qa.json').read_text(encoding='utf-8'))
qa['google_geometry_verified_in_browser'] = json.loads((ROOT / 'source/geometry-qa.json').read_text(encoding='utf-8'))
assert qa['google_geometry_verified_in_browser']['googleSource'] == qa['google_geometry_verified_in_browser']['googleExample']
qa['browser_interactions_verified']=['Google 메뉴·정보·개요 전환','Google 영업시간 펼침','카카오 메뉴 전환·해시 위치 이동','비교 화면 Google 전환']
qa['final_screenshots'] = names
(ROOT / 'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'preview':'preview.html','image':'images/native-home-comparison.jpg','five_browser_screenshots':True,'google_source_example_metrics_equal':True},ensure_ascii=False))
