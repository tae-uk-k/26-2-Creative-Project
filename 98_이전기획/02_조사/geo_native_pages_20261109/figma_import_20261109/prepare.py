"""Package the two existing map pages as self-contained, editable Figma input."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
import base64
import hashlib
import json
import mimetypes
import re
import uuid

from lxml import html, etree
from PIL import Image

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent
CACHE = OUT / 'resources'
CACHE.mkdir(exist_ok=True)
URL = re.compile(r'url\(\s*([\"\']?)(.*?)\1\s*\)', re.S)
EMPTY = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='
resources = {}
missing = []


def resource(url, base):
    if url.startswith(('data:', '#')):
        return url
    if url.startswith('//'):
        url = 'https:' + url
    if url.startswith('http'):
        path = CACHE / hashlib.sha256(url.encode()).hexdigest()
        if not path.exists():
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20) as response:
                data = response.read()
                mime = response.headers.get_content_type()
            path.write_bytes(data)
            path.with_suffix('.mime').write_text(mime)
        data = path.read_bytes()
        mime = path.with_suffix('.mime').read_text()
    else:
        path = (base / url.split('#')[0].split('?')[0]).resolve()
        if not path.is_file():
            missing.append(str(path))
            return EMPTY
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode()


def font_used(block, chars):
    match = re.search(r'unicode-range\s*:\s*([^;}]+)', block)
    if not match:
        return True
    for start, end in re.findall(r'U\+([\dA-F?]+)(?:-([\dA-F]+))?', match[1], re.I):
        lo = int(start.replace('?', '0'), 16)
        hi = int(end or start.replace('?', 'F'), 16)
        if any(lo <= c <= hi for c in chars):
            return True
    return False


def prepare(name, height):
    document = html.parse(str(SOURCE / (name + '.html')))
    body = document.find('body')
    for node in document.xpath('//script|//aside[contains(@class,"example-label")]'):
        node.getparent().remove(node)
    title = '카카오맵 · 온담식탁 성수점' if name == 'kakao' else 'Google 지도 · 소담면가 망원점'
    chars = set(map(ord, body.text_content())) | set(range(32, 127))
    styles = []
    for href in document.xpath('//link[@rel="stylesheet"]/@href'):
        path = SOURCE / href
        css = path.read_text(encoding='utf-8')
        css = re.sub(r'@font-face\s*\{[^}]*\}', lambda m: m[0] if font_used(m[0], chars) else '', css)
        styles.append((css, path.parent))

    # Only geographic map imagery is raster. The profile, navigation and controls stay editable.
    if name == 'google':
        map_image = Image.open(SOURCE / 'assets/google-map-background.jpg')
        map_image.crop((488, 0, 1440, 765)).save(OUT / 'geographic-map.jpg', quality=97)
        styles = [(s.replace('url(assets/google-map-background.jpg)', 'url(figma_import_20261109/geographic-map.jpg)'), b) for s, b in styles]
        nav = html.fromstring('''<nav class="figma-google-nav"><div>☰</div><div>▯<small>저장됨</small></div><div>◴<small>최근 항목</small></div><hr></nav>''')
        body.insert(1, nav)
        styles.append(('''.native-map{left:488px!important;background-position:0 0!important;background-size:952px 765px!important}.native-map:after{display:none!important}.figma-google-nav{position:absolute;left:0;top:0;width:72px;height:765px;background:#f5fafc;text-align:center;color:#62686b;font:22px/28px Arial;box-sizing:border-box;padding:20px 8px;z-index:1}.figma-google-nav div{margin-bottom:28px}.figma-google-nav small{display:block;font:12px/20px Arial,"Noto Sans KR",sans-serif;margin-top:4px}.figma-google-nav hr{border:0;border-top:1px solid #e4e9ec}''', SOURCE))

    # Resolve resources once, then reuse the embedded bytes; preserve all source files.
    urls = {(m[2], base) for css, base in styles for m in URL.finditer(css)}
    urls |= {(e.get('src'), SOURCE) for e in body.xpath('.//img[@src]')}
    urls |= {(m[2], SOURCE) for e in body.xpath('.//*[@style]') for m in URL.finditer(e.get('style'))}
    def load(item):
        url, base = item
        try:
            return item, resource(url, base)
        except Exception as error:
            missing.append(url + ': ' + str(error))
            return item, EMPTY
    with ThreadPoolExecutor(max_workers=12) as pool:
        for key, value in pool.map(load, urls):
            resources[key] = value
    def inline(css, base):
        return URL.sub(lambda m: 'url("' + resources[(m[2], base)] + '")', css)
    for img in body.xpath('.//img[@src]'):
        img.set('src', resources[(img.get('src'), SOURCE)])
    for element in body.xpath('.//*[@style]'):
        element.set('style', inline(element.get('style'), SOURCE))
    css = '\n'.join(inline(s, base) for s, base in styles)
    css += f'\nhtml,body{{margin:0!important;width:1280px!important;height:{height}px!important;min-height:{height}px!important;overflow:hidden!important}}#figma-map-page{{position:relative;width:1280px;height:{height}px;overflow:hidden}}'
    wrapper = etree.Element('div', id='figma-map-page')
    for child in list(body):
        wrapper.append(child)
    result = '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>' + title + '</title><style>' + css + '</style></head><body>' + html.tostring(wrapper, encoding='unicode') + '</body></html>'
    target = OUT / (name + '-self-contained.html')
    target.write_text(result, encoding='utf-8')
    assert len(result.encode()) < 50 * 1024 * 1024
    assert not re.search(r'<script|<link', result)
    return {'name': name, 'path': str(target), 'bytes': target.stat().st_size, 'width': 1280, 'height': height}


if __name__ == '__main__':
    files = [prepare('kakao', 1522), prepare('google', 765)]
    manifest = {'promptId': str(uuid.uuid4()), 'files': files, 'missing_resources': sorted(set(missing))}
    (OUT / 'input-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
