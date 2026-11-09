"""Build local examples by changing the observed native DOM, not a redrawn UI."""
from pathlib import Path
from copy import deepcopy
from urllib.parse import urljoin
import html as escape_module
import json
import re
import shutil
from lxml import html, etree

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'source'
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
PREVIOUS = ROOT.parent / 'geo_clean_showcase_20261109'
DATA = json.loads((PREVIOUS / 'fictional_facts.json').read_text(encoding='utf-8'))
EMPTY = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='
K_MANIFEST = Path(r'C:\Users\xodnr\AppData\Local\Temp\browser-use\assets\bbb4027d-7933-4955-aff5-1fe177cbeb7a\manifest.json')
G_MANIFEST = Path(r'C:\Users\xodnr\AppData\Local\Temp\browser-use\assets\02ed6a7f-d20f-4a19-9a5e-8054c1038504\manifest.json')


def read(name):
    return json.loads((SRC / (name + '.json')).read_text(encoding='utf-8'))


def cls(node, name):
    return node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," ' + name + ' ")]')


def first(node, name):
    return cls(node, name)[0]


def text(node, value):
    for child in list(node):
        node.remove(child)
    node.text = value


def markup(node):
    return html.tostring(node, encoding='unicode')


def fragment(value):
    return html.fromstring(value)


def drop(node):
    if node.getparent() is not None:
        node.getparent().remove(node)


def clean(node):
    for el in node.xpath('.//script|.//iframe|.//social-share|.//*[@id="codex-browser-sidebar-comments-root"]'):
        drop(el)
    for el in node.iter():
        for attr in list(el.attrib):
            if attr.startswith(('on', 'js', 've-')):
                del el.attrib[attr]
        if el.tag == 'a':
            el.set('href', '#')
            el.attrib.pop('target', None)
        el.attrib.pop('crossorigin', None)
    return node


def import_assets(manifest, prefix):
    cached_manifest = SRC / f'{prefix}-asset-manifest.json'
    source = json.loads((manifest if manifest.exists() else cached_manifest).read_text(encoding='utf-8'))
    mapping = {}
    styles = []
    for asset in source['assets']:
        if asset['kind'] not in ('stylesheet', 'font', 'image'):
            continue
        if 'track?' in asset['url'] or 'gen_204' in asset['url'] or '/profile/' in asset['url']:
            continue
        path = Path(asset['path'])
        suffix = path.suffix or ('.css' if asset['kind'] == 'stylesheet' else '.bin')
        name = prefix + '-' + asset['id'] + suffix
        if path.exists():
            shutil.copy2(path, ASSETS / name)
        else:
            assert (ASSETS / name).exists(), f'Missing preserved asset: {name}'
        mapping[asset['url']] = name
        if asset['kind'] == 'stylesheet':
            styles.append(name)
    for name in styles:
        value = (ASSETS / name).read_text(encoding='utf-8')
        for url, file in mapping.items():
            value = value.replace(url, file).replace(url.removeprefix('https:'), file)
        value = re.sub(r'url\((["\']?)//', r'url(\1https://', value)
        (ASSETS / name).write_text(value, encoding='utf-8')
    cached_manifest.write_text(json.dumps({'assets': [a for a in source['assets'] if a['url'] in mapping]}, ensure_ascii=False, indent=2), encoding='utf-8')
    return mapping, styles


K_MAP, K_STYLES = import_assets(K_MANIFEST, 'k')
G_MAP, G_STYLES = import_assets(G_MANIFEST, 'g')
for p in ('kakao', 'google'):
    shutil.copy2(PREVIOUS / f'assets/{p}_photos.png', ASSETS / f'{p}_photos.png')


def localize(node, mapping):
    for el in node.iter():
        for key in ('src', 'href'):
            url = el.get(key) or ''
            absolute = 'https:' + url if url.startswith('//') else url
            if absolute in mapping:
                el.set(key, 'assets/' + mapping[absolute])
    return node


def photo(img, platform, index, hero=False):
    img.set('src', EMPTY)
    img.set('alt', ['매장 실내', '대표 메뉴', '식사 메뉴', '세트 구성'][index])
    pos = ['0 0', '100% 0', '0 100%', '100% 100%'][index]
    style = f'background-image:url(assets/{platform}_photos.png);background-size:auto 200%;background-position:{pos};background-repeat:no-repeat;'
    if hero and platform == 'google':
        style += 'position:absolute;top:50%;left:50%;width:408px;height:272px;transform:translate(-50%,-50%);background-size:200% 200%;'
    img.set('style', style)


def write_page(name, head, body, body_class='', body_style=''):
    kind = '실제 원본 대조' if '_reference' in name else '가상 매장·사진·수치 설정'
    (ROOT / name).write_text(f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>[{kind}] {name}</title>{head}<link rel="stylesheet" href="native-controls.css"></head><body class="{body_class}" style="{body_style}">{body}<aside class="example-label">{kind} · <a href="index.html">예시 목록</a></aside><script src="native-controls.js"></script></body></html>', encoding='utf-8')


def k_menu():
    template = fragment(read('kakao-intro-template')['menus'][0])
    for el in cls(template, 'badge_label') + cls(template, 'recomm_badge'):
        drop(el)
    menu = fragment('<ul class="list_goods"></ul>')
    for i, m in enumerate(DATA['kakao']['menus']):
        li = deepcopy(template)
        text(first(li, 'tit_item'), m['after'])
        text(first(li, 'desc_item'), m['price'])
        text(first(li, 'desc_item2'), '1인분 · 매장에서 반죽한 수제비와 들깨 육수\n공깃밥 포함' if i == 0 else m['showcase_description'])
        first(li, 'desc_item2').set('style', 'white-space:pre-line')
        photo(li.xpath('.//img')[0], 'kakao', i + 1)
        menu.append(li)
    return menu


def kakao():
    c = DATA['kakao']
    doc = clean(html.document_fromstring(read('kakao-home')['html']))
    localize(doc, K_MAP)
    for el in doc.xpath('.//head/*'):
        if el.tag not in ('style',):
            drop(el)
    for name in K_STYLES:
        doc.find('head').append(fragment(f'<link rel="stylesheet" href="assets/{name}">'))
    title = first(doc, 'tit_place')
    text(title, c['name'])
    text(first(doc, 'link_head'), c['name'])
    text(first(doc, 'info_cate'), '한식')
    for name in ('link_rank',):
        for el in cls(doc, name):
            drop(el.getparent().getparent())
    text(first(doc, 'num_star'), '4.6')
    first(doc, 'bar_on').set('style', 'width:92%')
    text(first(first(doc, 'link_review'), 'info_num'), '82')
    text(first(first(doc, 'link_blog'), 'info_num'), '0')
    text(first(doc, 'info_state'), '영업 마감')
    text(first(doc, 'info_runtime'), '내일 11:00 오픈')
    photos = first(doc, 'board_photo').xpath('.//img')
    for img, idx in zip(photos, [1, 0, 2, 3, 0]):
        photo(img, 'kakao', idx)
    text(first(first(doc, 'board_photo'), 'txt_more'), '4')
    detail = first(doc, 'detail_cont')
    basic = deepcopy(first(detail, 'section_defaultinfo'))
    for el in cls(basic, 'link_suggest'):
        drop(el)
    for el in cls(basic, 'unit_default'):
        label = ''.join(el.xpath('./h5//text()'))
        if label in ('URL', '인증 매장'):
            drop(el)
        elif label == '영업정보':
            for t in cls(el, 'tit_detail'):
                text(t, '영업 마감')
            for t in cls(el, 'txt_detail'):
                value = t.text_content()
                if '오픈' in value:
                    text(t, '내일 11:00 오픈')
                elif '브레이크' in value:
                    text(t, '20:30 마지막 주문')
                elif '~' in value:
                    text(t, '11:00 ~ 21:00')
        elif label == '주소':
            text(first(el, 'txt_detail'), '서울 성동구 성수이로18길 12 1층 (가상 주소)')
            for t in cls(el, 'row_detail')[1:]:
                drop(t)
            for t in cls(el, 'fold_detail'):
                drop(t)
        elif label == '전화':
            text(first(el, 'txt_detail'), '02-000-0000')
    intro = fragment(f'<div class="box_intro box_open"><div class="inner_boxintro"><div class="view_boxintro"><strong class="tit_boxintro">{c["name"]}</strong><p class="desc_boxintro">{c["showcase_intro"]}</p></div></div></div>')
    menu = deepcopy(first(detail, 'section_product'))
    for el in cls(menu, 'wrap_menu') + cls(menu, 'link_suggest') + cls(menu, 'wrap_more'):
        drop(el)
    text(first(menu, 'txt_info'), '3')
    oldlist = first(menu, 'list_goods')
    oldlist.getparent().replace(oldlist, k_menu())
    store = deepcopy(first(detail, 'section_storetaiinfo'))
    for el in cls(store, 'wrap_facilities') + cls(store, 'wrap_storeetc'):
        drop(el)
    store_info = first(store, 'default_info')
    store_info.append(fragment('<div class="wrap_storeinfo wrap_storeetc"><div class="unit_default unit_hashtag"><h5 class="tit_addinfo">태그</h5><div class="detail_info"><div class="row_detail"><a href="#none" class="link_detail">#들깨수제비</a><a href="#none" class="link_detail">#제육정식</a><a href="#none" class="link_detail">#한식</a></div></div></div></div>'))
    for child in list(detail):
        detail.remove(child)
    for child in (basic, store, menu):
        detail.append(child)
    for el in cls(doc, 'link_tab'):
        label = el.text_content().strip()
        if label in ('홈', '메뉴'):
            el.set('href', 'kakao.html' if label == '홈' else 'kakao_menu.html#menuInfo')
        else:
            el.set('href', '#')
    head = ''.join(markup(el) for el in doc.find('head'))
    body = markup(doc.find('body'))[6:-7]
    write_page('kakao.html', head, body)
    menu_doc = deepcopy(doc)
    menu_detail = first(menu_doc, 'detail_cont')
    for child in list(menu_detail):
        menu_detail.remove(child)
    menu_detail.append(deepcopy(menu))
    for el in cls(menu_doc, 'link_tab'):
        el.set('aria-selected', str(el.text_content().strip() == '메뉴').lower())
    first(menu_doc, 'main_detail').set('class', 'main_detail')
    first(menu_doc, 'main_detail').set('id', 'menuInfo')
    body = markup(menu_doc.find('body'))[6:-7]
    write_page('kakao_menu.html', head, body)
    # Baseline retains the observed UI. It is evidence, separate from the fictional example.
    reference = clean(html.document_fromstring(read('kakao-home')['html']))
    localize(reference, K_MAP)
    for el in reference.xpath('.//head/link|.//head/meta|.//head/title'):
        drop(el)
    ref_head = ''.join(f'<link rel="stylesheet" href="assets/{n}">' for n in K_STYLES)
    write_page('kakao_reference.html', ref_head, markup(reference.find('body'))[6:-7])


def g_tabs(main, active):
    tablist = main.xpath('.//*[@role="tablist"]')[0]
    for i, button in enumerate(tablist.xpath('./button')):
        button.set('data-page', ['google.html', 'google_menu.html', '', 'google_info.html'][i])
        button.set('aria-label', ['개요', '메뉴', '리뷰', '정보'][i])
        button.set('aria-selected', str(i == active).lower())
        button.set('class', 'hh2c6 G7m0Af' if i == active else 'hh2c6')


def google():
    c = DATA['google']
    capture = read('google-menu')
    home_data = read('google-home')
    inline = capture['inlineCss']
    inline = re.sub(r'\n{2,}', '\n', inline)
    inline = re.sub(r'url\((["\']?)//', r'url(\1https://', inline)
    theme = ':root{' + ';'.join(f'{k}:{v}' for k, v in home_data['theme'].items() if v.strip()) + '}'
    (ASSETS / 'google-inline.css').write_text(inline + '\n' + theme, encoding='utf-8')
    head = '<link rel="stylesheet" href="assets/google-inline.css">' + ''.join(f'<link rel="stylesheet" href="assets/{n}">' for n in G_STYLES) + '<link rel="stylesheet" href="google-layout.css">'
    search = clean(fragment(capture['search']))
    search.xpath('.//input')[0].set('value', c['name'])
    search.set('id', 'native-search')
    template_main = clean(fragment(home_data['mainTag'] + home_data['scrollTag'] + ''.join(home_data['parts']) + '</div></div>'))
    home = deepcopy(template_main)
    home.set('id', 'native-google-main')
    home.set('data-view', 'home')
    home.set('aria-label', c['name'])
    scroll = home[0]
    # Remove the missing-information prompts and personal actions from the real source.
    parts = list(scroll)
    for i in [9, 11, 14, 15, 16, 17, 28]:
        drop(parts[i])
    title = first(home, 'DUwDvf')
    text(title, c['name'])
    first(home, 'DkEaL').text = '일식당'
    for value in cls(home, 'mgr77e'):
        drop(value)
    rating = first(home, 'F7nice')
    rating_text = rating.xpath('.//span[@aria-hidden="true"]')[0]
    text(rating_text, '4.7')
    review = rating.xpath('.//*[@aria-label="리뷰 14개"]')[0]
    text(review, '(128)')
    review.set('aria-label', '리뷰 128개')
    rating.xpath('.//*[@class="ceNzKf"]')[0].set('aria-label', '별표 4.7개')
    for i, star in enumerate(cls(rating, 'rFrJzc')):
        star.set('class', 'rFrJzc' + (' UpDOYb' if i == 4 else ''))
    photo(first(home, 'aGzt2e').xpath('.//img')[0], 'google', 1, hero=True)
    first(home, 'aGzt2e').xpath('.//button')[0].set('aria-label', c['name'] + ' 사진')
    info = home.xpath('.//*[@aria-label="힛사츠와자(Hissatsuwaza) 관련 정보"]')[0]
    address = info.xpath('.//*[@data-item-id="address"]')[0]
    text(first(address, 'Io6YTe'), '서울 마포구 망원로12길 8, 1층')
    address.set('aria-label', '주소: 서울 마포구 망원로12길 8, 1층')
    for el in list(info):
        if el is not address.getparent():
            drop(el)
    hours = clean(fragment(read('google-hours-row')['html']))
    info.append(hours)
    phone = clean(fragment(read('google-pizza-overview-info')['rows'][1]))
    text(first(phone, 'Io6YTe'), '02-000-0000')
    for el in phone.iter():
        for attr in ('aria-label', 'data-value', 'href', 'data-item-id'):
            if el.get(attr):
                el.set(attr, el.get(attr).replace('02-777-8979', '02-000-0000').replace('027778979', '020000000'))
    info.append(phone)
    for img in home.xpath('.//img'):
        if not img.get('src', '').startswith('data:'):
            photo(img, 'google', 0 if 'gps-cs-s' in img.get('src', '') else 3)
    shutil.copy2(ROOT.parent / 'geo_mock_v2_20261106/sources/google_board_1.svg', ASSETS / 'google-menuboard.svg')
    food_cards = first(home, 'fp2VUc').xpath('.//img')
    for i, img in enumerate(food_cards):
        if i == 0:
            img.set('src', 'assets/google-menuboard.svg')
            img.set('style', 'height:195px;object-fit:contain;background:#ede6db')
            img.set('alt', '가상 메뉴판')
        else:
            photo(img, 'google', 1 if i == 1 else 3)
    album = home.xpath('.//*[@role="region" and contains(@aria-label," 사진")]')[0]
    album_cards = cls(album, 'ofKBgf')
    for i, card in enumerate(album_cards):
        if i not in (0, 3, 4, 5):
            drop(card)
        elif i in (0, 4, 5):
            photo(card.xpath('.//img')[0], 'google', 1 if i == 4 else 0)
        else:
            img = card.xpath('.//img')[0]
            img.set('src', 'assets/google-menuboard.svg')
            img.set('style', 'height:149px;object-fit:contain;background:#ede6db')
    # Existing native photo categories are kept; only fictional images/labels change.
    for el in home.xpath('.//*[@aria-label]'):
        el.set('aria-label', el.get('aria-label').replace('힛사츠와자(Hissatsuwaza)', c['name']))
    g_tabs(home, 0)
    menu = clean(fragment(capture['main']))
    menu.set('id', 'native-google-main')
    menu.set('data-view', 'menu')
    menu.set('aria-label', c['name'])
    g_tabs(menu, 1)
    tablists = menu.xpath('.//*[@role="tablist"]')
    for button in tablists[1].xpath('./button')[2:]:
        drop(button)
    region = menu.xpath('.//*[@role="region"]')[0]
    row_template = deepcopy(region[0])
    for child in list(region):
        region.remove(child)
    for m in c['menus']:
        row = deepcopy(row_template)
        text(first(row, 'Io6YTe'), m['after'])
        text(first(row, 'gSkmPd'), m['showcase_description'])
        first(row, 'gSkmPd').set('style', first(row, 'gSkmPd').get('style', '') + ';white-space:pre-line')
        text(first(row, 'sErS0c'), '₩' + m['price'].replace('원', ''))
        region.append(row)
    info_main = clean(fragment(read('google-info')['main']))
    info_main.set('id', 'native-google-main')
    info_main.set('data-view', 'info')
    info_main.set('aria-label', c['name'])
    g_tabs(info_main, 3)
    info_region = info_main.xpath('.//*[@role="region"]')[0]
    groups = [el for el in cls(info_region, 'iP2t7d') if first(el, 'iL3Qke').text_content() in ('서비스 옵션', '편의 시설', '결제')]
    spacing = [deepcopy(info_region[i]) for i in (0, 2, 3, 4)]
    for child in list(info_region):
        info_region.remove(child)
    info_region.append(spacing[0])
    for i, group in enumerate(groups):
        info_region.append(group)
        if i < len(groups) - 1:
            for gap in spacing[1:]:
                info_region.append(deepcopy(gap))
    description = fragment(f'<div class="iP2t7d fontBodyMedium"><h2 class="iL3Qke fontTitleSmall">비즈니스 소유자가 제공한 설명</h2><p class="fontBodyMedium">{c["showcase_intro"]}</p></div>')
    # The observed public pages did not show an owner-description block; keep its draft outside the native screen.
    chrome = '<div class="native-map"></div><div class="native-map-name">소담면가 망원점</div>'
    for name, main in [('google.html', home), ('google_menu.html', menu), ('google_info.html', info_main)]:
        for el in main.iter():
            if el.get('aria-label'):
                el.set('aria-label', el.get('aria-label').replace('힛사츠와자(Hissatsuwaza)', c['name']))
        write_page(name, head, chrome + markup(search) + markup(main), home_data['bodyClass'], home_data['bodyStyle'])
    baseline = clean(fragment(capture['main']))
    baseline.set('id', 'native-google-main')
    baseline.set('data-view', 'menu')
    write_page('google_reference.html', head, '<div class="native-map"></div>' + markup(search).replace(c['name'], '힛사츠와자(Hissatsuwaza)') + markup(baseline), home_data['bodyClass'], home_data['bodyStyle'])


kakao()
google()
print(json.dumps({'native_pages': 5, 'reference_pages': 2, 'original_css_files': len(K_STYLES) + len(G_STYLES), 'fictional_examples': True}, ensure_ascii=False))
