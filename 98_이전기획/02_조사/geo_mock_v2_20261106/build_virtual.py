"""가상 원자료만으로 지도 정비 예시 생성. 실제 매장 자료·가격으로 사용하지 않는다."""
from pathlib import Path
import html
import json
import re
import shutil
import textwrap
from PIL import Image

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / '지도UI_실제정비_2예시_20261106'
DATA = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))
(ROOT / 'case_data.js').write_text('const caseData=' + json.dumps(DATA, ensure_ascii=False) + ';', encoding='utf-8')
for folder in ('assets', 'sources', 'images'):
    (ROOT / folder).mkdir(exist_ok=True)
for src in (PREVIOUS / 'assets').iterdir():
    if src.suffix in ('.css', '.svg'):
        shutil.copy2(src, ROOT / 'assets' / src.name)
# 지도 UI 틀만 재사용. 원래 실제 가게 이름이 들어간 왼쪽 패널은 전부 덮는다.
Image.open(PREVIOUS / 'images/google_original.png').crop((0,0,600,765)).save(ROOT / 'assets/google_shell.png')

def esc(text):
    return html.escape(text, quote=True)

def board(platform, page):
    c = DATA[platform]
    src = c['sources'][2 + page]
    lines = []
    for paragraph in src['quote'].split('. '):
        lines.extend(textwrap.wrap(paragraph, width=29, break_long_words=True))
        lines.append('')
    content = ''.join(f'<text x="64" y="{230+i*42}" font-size="25" fill="#342d26">{esc(line)}</text>' for i,line in enumerate(lines))
    height = max(1000, 300 + len(lines)*42)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}" viewBox="0 0 800 {height}"><rect width="800" height="{height}" fill="#ede6db"/><rect x="25" y="25" width="750" height="{height-50}" fill="#fffdf7" stroke="#b8ac98"/><g font-family="Malgun Gothic,Arial,sans-serif"><text x="64" y="102" font-size="37" font-weight="700" fill="#342d26">{esc(c['name'])}</text><text x="64" y="153" font-size="23" fill="#776c5d">{esc('메뉴' if page == 0 else '주문 안내')} · {page+1}</text><path d="M64 180H736" stroke="#b8ac98"/>{content}<text x="64" y="{height-62}" font-size="19" fill="#8c8274">정비 예시용 가상 메뉴판</text></g></svg>'''
    path = f'sources/{platform}_board_{page+1}.svg'
    (ROOT / path).write_text(svg, encoding='utf-8')
    return path

BOARDS = {p: [board(p,0), board(p,1)] for p in ('kakao','google')}

old = (PREVIOUS / 'kakao_before.html').read_text(encoding='utf-8')
k_styles = '\n'.join(re.findall(r'<link\b[^>]*rel="stylesheet"[^>]*>', old))
k_header = re.search(r'<header\b.*?</header>', old, re.S)[0].replace('파르코 서울숲점', DATA['kakao']['name'])

def kakao_page(state, view):
    c = DATA['kakao']
    labels = ['홈','메뉴','사진','후기','블로그','랭킹']
    current = 0 if view == 'intro' else 1
    tabs = '<div class="wrap_tab tab_primary"><div class="inner_tab"><ul class="list_tab" role="tablist">' + ''.join(f'<li role="presentation"><a href="#" role="tab" aria-selected="{str(i==current).lower()}" class="link_tab" data-index="{i}">{label}</a></li>' for i,label in enumerate(labels)) + '</ul></div></div>'
    if view == 'intro':
        content = f'''<div class="box_intro box_open"><div class="inner_boxintro"><div class="view_boxintro"><strong class="tit_boxintro">{esc(c['name'])}</strong><p class="desc_boxintro">{esc(c['intro_'+state])}</p></div></div></div><div class="section_comm section_defaultinfo"><div class="default_info"><div class="unit_default"><h5 class="tit_info"><span class="ico_mapdesc ico_address">주소</span></h5><div class="detail_info"><div class="row_detail"><span class="txt_detail">서울 성동구 성수이로 00길 00 1층</span></div></div></div><div class="unit_default"><h5 class="tit_info"><span class="ico_mapdesc ico_runstate">영업정보</span></h5><div class="detail_info"><div class="row_detail"><span class="txt_detail">매일 11:00 ~ 21:00</span></div></div></div></div></div>'''
    else:
        pictures = ''.join(f'<li data-v-ea9add74=""><a data-v-ea9add74="" href="{path}" class="link_menu"><img data-v-ea9add74="" src="{path}" height="112" alt="가상 메뉴판 {i+1}" class="img_menu"></a></li>' for i,path in enumerate(BOARDS['kakao']))
        items = ''
        for m in c['menus']:
            name = m['before'] if state == 'before' else m['after']
            desc = '<p class="desc_item2">' + esc(m.get('before_description', '') if state == 'before' else m['description']).replace('\n', '<br>') + '</p>'
            items += '<li><div class="info_goods"><div class="line_info"><strong class="tit_item">' + esc(name) + '</strong></div><div class="line_info"><p class="desc_item">' + m['price'] + '</p></div>' + desc + '</div></li>'
        content = '<div class="section_comm section_product"><div class="head_section"><div class="wrap_tit"><h4 class="tit_section">메뉴</h4><div class="info_count"><span class="txt_info">3</span></div></div></div><div data-v-ea9add74="" class="wrap_menu"><ul data-v-ea9add74="" class="list_menu">' + pictures + '</ul><div data-v-ea9add74="" class="info_count"><span data-v-ea9add74="" class="num_count">2</span></div></div><div class="wrap_goods"><ul class="list_goods">' + items + '</ul></div></div>'
    # 固定 헤더·600px 본문·탭·메뉴·소개 카드의 스타일은 보존한 카카오 원본 CSS다.
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>[가상] '+esc(c['name'])+' · '+view+' '+state+'</title>'+k_styles+'<style>.doc-main{padding-top:0;margin-top:0}.main_detail{padding-top:0}.tab_primary{position:relative;top:0}.detail_cont{min-height:608px}.list_menu .img_menu{object-fit:cover;object-position:top}</style></head><body><div id="app" class="container-doc scroll_on">'+k_header+'<main class="doc-main"><article id="mainContent" class="content-article"><div class="main_detail">'+tabs+'<div class="detail_cont">'+content+'</div></div></article></main></div><script>document.querySelectorAll("a").forEach(a=>a.addEventListener("click",e=>{if(a.getAttribute("href")==="#")e.preventDefault()}))</script></body></html>'

G_STYLE = '''
*{box-sizing:border-box}html,body{margin:0;background:white;font-family:"Google Sans Text","Google Sans",Roboto,"Noto Sans KR",Arial,"Malgun Gothic",sans-serif;color:#1f1f1f}.canvas{position:relative;width:600px;height:765px;overflow:hidden}.shell{position:absolute;width:600px;height:765px;inset:0}.search{position:absolute;top:16px;left:16px;width:376px;height:48px;background:#fff;border:1px solid #e1e3e1;border-radius:25px;display:flex;align-items:center;gap:18px;padding:0 17px;box-shadow:0 1px 2px #00000012;font-size:14px}.search .name{flex:1;white-space:nowrap}.search svg{flex:none}.panel{position:absolute;left:0;top:80px;width:408px;min-height:677px;background:white;border-radius:0 0 26px 26px;overflow:hidden}.tabs{display:flex;height:49px;border-bottom:1px solid #dadce0}.tabs span{position:relative;display:flex;align-items:center;justify-content:center;width:25%;height:49px;color:#5e5e5e;font-size:14px}.tabs .active{color:#176b76;background:#e0eaeb}.tabs .active:after{content:"";position:absolute;bottom:0;left:35%;width:30%;height:3px;background:#176b76}.subtabs{display:flex;gap:8px;align-items:center;height:49px;padding:0 24px;border-bottom:1px solid #dadce0;font-size:14px;white-space:nowrap}.subtabs .active{background:#d1dcdf;padding:10px 12px;border-radius:9px}.photos{display:flex;gap:8px;padding:14px 24px 12px}.photos img{width:176px;height:98px;object-fit:cover;object-position:top;border-radius:5px}.item{padding:10px 24px;border-bottom:1px solid #dadce0}.item .name{font-size:14px;line-height:20px;letter-spacing:.1px}.item .description,.item .price{font-size:12px;line-height:16px;letter-spacing:.2px;color:#5e5e5e}.item .price{margin-top:2px}.about{padding:24px}.about h1{font-size:22px;line-height:28px;font-weight:400;margin:0 0 24px}.about h2{font-size:14px;font-weight:500;line-height:20px;margin:0 0 12px}.about p{font-size:14px;line-height:22px;margin:0}.g-rule{height:1px;background:#dadce0;margin:24px -24px}.about .base{display:flex;gap:14px;color:#5e5e5e;font-size:14px;line-height:23px;margin:14px 0}
'''

def google_page(state, view):
    c = DATA['google']
    active = 3 if view == 'intro' else 1
    tabs = '<div class="tabs">'+''.join(f'<span class="{"active" if i==active else ""}">{t}</span>' for i,t in enumerate(['개요','메뉴','리뷰','정보']))+'</div>'
    if view == 'intro':
        main = f'<div class="about"><h1>{esc(c["name"])} 정보</h1><h2>비즈니스 소유자가 제공한 설명</h2><p>{esc(c["intro_"+state])}</p><div class="g-rule"></div><div class="base">⌖ <span>서울 마포구 망원로 00길 00</span></div><div class="base">◷ <span>매일 11:00~21:00</span></div></div>'
    else:
        main = '<div class="subtabs"><span>개요</span><span class="active">메뉴</span><span>음료</span></div><div class="photos">'+''.join(f'<img src="{path}" alt="가상 메뉴판 {i+1}">' for i,path in enumerate(BOARDS['google']))+'</div>'
        for m in c['menus']:
            name = m['before'] if state == 'before' else m['after']
            desc = '<div class="description">'+esc(m.get('before_description', '') if state == 'before' else m['description']).replace('\n', '<br>')+'</div>'
            main += '<div class="item"><div class="name">'+esc(name)+'</div>'+desc+'<div class="price">'+m['price']+'</div></div>'
    search = '<div class="search"><svg width="18" height="18" viewBox="0 0 24 24"><path d="M20 12H4m7-7-7 7 7 7" fill="none" stroke="#5e5e5e" stroke-width="2"/></svg><span class="name">'+esc(c['name'])+'</span><svg width="20" height="20" viewBox="0 0 24 24"><circle cx="10" cy="10" r="6" stroke="#5e5e5e" stroke-width="2" fill="none"/><path d="m15 15 6 6" stroke="#5e5e5e" stroke-width="2"/></svg><svg width="20" height="20" viewBox="0 0 24 24"><path d="m5 5 14 14M19 5 5 19" stroke="#5e5e5e" stroke-width="2"/></svg></div>'
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>[가상] '+esc(c['name'])+' · '+view+' '+state+'</title><style>'+G_STYLE+'</style></head><body><div class="canvas"><img src="assets/google_shell.png" class="shell" alt="지도 UI 배경">'+search+'<div class="panel">'+tabs+main+'</div></div></body></html>'

for p, make in [('kakao',kakao_page),('google',google_page)]:
    for view in ('intro','menu'):
        for state in ('before','after'):
            (ROOT / f'{p}_{view}_{state}.html').write_text(make(state,view), encoding='utf-8')

# 자료 → 문장 대응을 따로 기록해 가상 사실이 정비 과정에서 새로 생기지 않도록 한다.
ledger = {'fictional':True,'cases':{}}
for p in ('kakao','google'):
    c=DATA[p]
    ledger['cases'][p]={'intro':{'before':c['intro_before'],'after':c['intro_after'],'source_ids':[s['id'] for s in c['sources']]},'menus':c['menus'],'unresolved_not_published':c['unresolved']}
(ROOT/'fact_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
qa={'fictional_label':True,'live_map_write':False,'source_board_count':4,'views_created':8,'prices_preserved':{p:[m['price'] for m in DATA[p]['menus']] for p in ('kakao','google')}}
for p in ('kakao','google'):
    for state in ('before','after'):
        content=(ROOT/f'{p}_menu_{state}.html').read_text(encoding='utf-8')
        for price in qa['prices_preserved'][p]: assert content.count(price)==1
        assert '파르코' not in content and '힛사츠와자' not in content
(ROOT/'static_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(qa,ensure_ascii=False))
