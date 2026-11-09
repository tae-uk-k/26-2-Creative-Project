"""관측 원본으로 로컬 정비 시안 생성. 실제 지도에 쓰기 동작 없음."""
from pathlib import Path
from urllib.parse import urljoin
import html
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
captured = json.loads((SOURCE / 'kakao_menu_snapshot.json').read_text(encoding='utf-8'))
bundle = captured['bundle']
paths = {}
for asset in bundle['assets']:
    if 'tracking' in asset['url'] or asset['id'] == '4544e4f2f295e3ac':
        continue
    src = Path(asset['path'])
    name = asset['id'] + (src.suffix or ('.jpg' if asset['contentType'] == 'image/jpeg' else ''))
    dest = ASSETS / name
    if src.is_file():
        shutil.copy2(src, dest)
    elif not dest.exists():
        raise FileNotFoundError(src)
    paths[asset['url']] = name

def local_urls(text, prefix):
    for url, name in sorted(paths.items(), key=lambda x: -len(x[0])):
        for value in (url, url.removeprefix('https:'), html.escape(url, quote=True), html.escape(url.removeprefix('https:'), quote=True)):
            text = text.replace(value, prefix + name)
    return text

for asset in bundle['assets']:
    if asset['kind'] != 'stylesheet':
        continue
    original = Path(asset['path']).read_text(encoding='utf-8')
    def replace_url(m):
        value = m[1].strip().strip('\"\'')
        if value.startswith('data:'):
            return m[0]
        absolute = urljoin(asset['url'], value)
        return 'url("' + paths[absolute] + '")' if absolute in paths else 'none'
    (ASSETS / paths[asset['url']]).write_text(re.sub(r'url\(([^)]+)\)', replace_url, original), encoding='utf-8')

original_html = captured['snapshot']['html']
body = re.search(r'<body\b[^>]*>(.*?)</body>', original_html, re.S)[1]
body = re.sub(r'<script\b[^>]*>.*?</script>|<iframe\b[^>]*>.*?</iframe>', '', body, flags=re.S | re.I)
body = re.sub(r'\s+on\w+="[^"]*"', '', body, flags=re.I)
body = re.sub(r'<img\b[^>]*(?:4544e4f2f295e3ac|tracking|track\.t1)[^>]*>', '', body, flags=re.I)
body = local_urls(body, 'assets/')
links = re.findall(r'<link\b[^>]*rel="stylesheet"[^>]*>', original_html)
styles = '\n'.join(local_urls(link, 'assets/') for link in links)
# 원본 페이지의 스크롤 상태에 따른 고정 헤더·탭 클래스와 스타일을 그대로 사용한다.
edits = [
    {'name': '버섯치즈 리조또', 'price': '20,800원', 'before': None, 'after': '다양한 버섯과 치즈로 맛을 낸 리조또.'},
    {'name': '바질 크레마', 'price': '20,800원', 'before': None, 'after': '갑오징어·새우·조개로 맛을 낸 바질 크림 리조또.'},
    {'name': '해산물 리조또', 'price': '20,800원', 'before': None, 'after': '갑오징어·새우·조개로 맛을 낸 리조또. 소스 선택: 토마토 / 크림 / 매콤로제.'},
]
after = body
for edit in edits:
    pattern = r'(<li>.*?<strong class="tit_item">' + re.escape(edit['name']) + r'</strong>.*?<p class="desc_item">' + re.escape(edit['price']) + r'</p></div>)(<!---->)'
    # li를 넘어가지 않는 범위로 대상 메뉴를 한 개만 수정한다.
    items = list(re.finditer(r'<li(?:\s[^>]*)?>.*?</li>', after, re.S))
    matches = [m for m in items if '<strong class="tit_item">' + edit['name'] + '</strong>' in m[0]]
    assert len(matches) == 1, edit['name']
    item = matches[0][0]
    old = '<p class="desc_item">' + edit['price'] + '</p></div>'
    assert old in item and 'desc_item2' not in item
    updated = item.replace(old, old + '<p class="desc_item2">' + html.escape(edit['after']) + '</p>', 1)
    after = after.replace(item, updated, 1)

script = '''<script>
history.scrollRestoration='manual';
window.addEventListener('load',()=>requestAnimationFrame(()=>window.scrollTo(0,433)));
document.addEventListener('click',e=>{if(e.target.closest('a'))e.preventDefault()});
window.addEventListener('message',e=>{if(e.source===parent&&e.data?.type==='position')scrollTo(0,e.data.y)});
window.addEventListener('scroll',()=>{if(parent!==window)parent.postMessage({type:'position',y:scrollY},'*')},{passive:true});
</script>'''
csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; style-src \'self\' \'unsafe-inline\'; font-src \'self\'; script-src \'unsafe-inline\'; frame-ancestors \'self\'">'
for state, content in [('before', body), ('after', after)]:
    page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>파르코 서울숲점 | 카카오맵 정비 시안 ' + state + '</title>' + csp + styles + '</head><body>' + content + script + '</body></html>'
    (ROOT / ('kakao_' + state + '.html')).write_text(page, encoding='utf-8')

# 재료와 선택 조건을 직접 읽은 동일 지도 메뉴판 사진을 근거로 보존한다.
photos = json.loads((SOURCE / 'kakao_menuboard_bundle.json').read_text(encoding='utf-8'))['bundle']['assets']
photo = next(a for a in photos if a['id'] == 'd84864c5598e43b7')
shutil.copy2(photo['path'], ROOT / 'images/kakao_menuboard.jpg')
google = json.loads((SOURCE / 'google_menu_evidence.json').read_text(encoding='utf-8'))
g_after = [
    '기본 구성: 차슈 2장 · 멘마 2개 · 김 1장. 계란 미포함.',
    '면 중량 선택: 150g·200g 추가금 없음 / 300g +1,000원.',
    '무료 요청 선택: 초생강 추가 / 멘마 제외 / 적양파 많이.',
]
# Google의 실제 캡처 픽셀을 배경으로 유지하고 설명 한 칸만 원본 서체 속성으로 교체한다.
# 좌측 개인 저장 목록과 우측 계정 영역을 제외한 crop=(72,0,1280,765).
g_css = '''
html,body{margin:0;background:#fff} .canvas{position:relative;width:1208px;height:765px;overflow:hidden}
.original{display:block;width:1208px;height:765px}
.erase{position:absolute;left:0;top:207px;width:408px;height:135px;background:#fff}\n.edit{position:absolute;left:0;top:207px;width:408px;background:#fff;box-sizing:border-box;padding:0 24px 10px;border-bottom:1px solid #d2d2d2}
.description{font-family:"Google Sans Text","Google Sans",Roboto,"Noto Sans KR",Arial,sans-serif;font-size:12px;font-weight:400;line-height:16px;letter-spacing:.2px;color:rgb(94,94,94);white-space:pre-line}
'''
for state in ('before', 'after'):
    change = '' if state == 'before' else '<div class="erase"></div><div class="edit"><div class="description">' + html.escape('\n\n'.join(g_after)) + '</div></div>'
    page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>힛사츠와자 | Google 지도 정비 시안 ' + state + '</title><style>' + g_css + '</style></head><body><div class="canvas"><img class="original" src="images/google_original.png" alt="Google 지도 원본 장소 화면">' + change + '</div></body></html>'
    (ROOT / ('google_' + state + '.html')).write_text(page, encoding='utf-8')

evidence = {
    'created_at': '2026-11-06', 'status': '로컬 정비 시안. 실제 지도 정보 수정 없음.',
    'kakao': {'store': '파르코 서울숲점', 'address': '서울 성동구 서울숲2길 44 1층', 'url': captured['url'], 'observed_at': captured['observed_at'], 'issue': '텍스트 메뉴 19개에 이름과 가격이 있지만 설명 없음. 메뉴판 사진에 재료와 소스 선택 조건이 존재함.', 'edits': edits, 'source_photo': {'local': 'images/kakao_menuboard.jpg', 'url': photo['url'], 'quote': ['다양한 버섯과 치즈로 맛을 낸 리조또', '갑오징어, 새우, 조개로 맛을 낸 바질 크림 리조또', '갑오징어, 새우, 조개로 맛을 낸 리조또 (세 가지 중 주문하실 수 있습니다.) 토마토 소스 / 크림 소스 / 매콤로제 소스']}, 'design': '당일 실제 DOM, CSS, 사진, 아이콘 보존. 기존 desc_item2 설명 클래스만 추가.', 'not_inferred': ['1인분 인원·중량', '최소 주문', '점심 판매 시간', '공식 작성자 여부']},
    'google': {'store': '힛사츠와자(Hissatsuwaza)', 'address': '서울특별시 마포구 망원동 410-26', 'url': google['url'], 'observed_at': google['observed_at'], 'before': google['menu'], 'after': g_after, 'issue': '기본 구성·계란 제외·중량별 추가금·무료 요청이 한영 혼합 한 문단에 연결돼 있음.', 'design': '당일 원본 캡처 픽셀 유지. 설명 한 칸만 12px/16px, 자간 0.2px, 색상 rgb(94,94,94)로 교체.', 'preserved_facts': ['차슈 2장·멘마 2개·김 1장', '계란 기본 제공 안 함', '150g·200g 추가금 0', '300g 추가금 1000원', '초생강·멘마 제외·적양파 많이 요청 +0'], 'not_inferred': ['차슈멘 기본 가격', '영업시간', '전화번호'], 'access': 'IAB 제한 보기에는 메뉴 미노출. 별도 Chrome 탭에서 실제 메뉴 상세 확인. 옛 캡처를 현재 근거로 대체하지 않음.', 'language_change': '동일 사실을 반복한 영문은 이 한국어 시안에서 정리하고 한국어 3개 문단으로 표시.'},
}
(ROOT / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
qa = {
    'kakao_menu_names_same': re.findall(r'<strong class="tit_item">(.*?)</strong>', body) == re.findall(r'<strong class="tit_item">(.*?)</strong>', after),
    'kakao_prices_same': re.findall(r'<p class="desc_item">(.*?)</p>', body) == re.findall(r'<p class="desc_item">(.*?)</p>', after),
    'kakao_price_count': len(re.findall(r'<p class="desc_item">', body)),
    'kakao_added_descriptions': after.count('class="desc_item2"') - body.count('class="desc_item2"'),
    'live_map_write': False,
    'google_base_price_invented': False,
}
assert all(qa[k] for k in ('kakao_menu_names_same', 'kakao_prices_same'))
assert qa['kakao_price_count'] == 19 and qa['kakao_added_descriptions'] == 3
(ROOT / 'static_qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'folder': str(ROOT), 'qa': qa}, ensure_ascii=False))
