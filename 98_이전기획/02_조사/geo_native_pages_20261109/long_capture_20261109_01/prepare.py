"""Create capture-only copies. Preserve the original map example pages."""
from pathlib import Path
from copy import deepcopy
from lxml import html, etree
import json

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent
BASE = 'http://127.0.0.1:8879/'


def read(name):
    return html.parse(str(SOURCE / name))


def save(doc, name, css, js):
    for node in doc.xpath('//aside[contains(@class,"example-label")]|//script'):
        node.getparent().remove(node)
    head = doc.find('head')
    head.insert(0, etree.Element('base', href=BASE))
    style = etree.SubElement(head, 'style')
    style.text = css
    script = etree.SubElement(doc.find('body'), 'script')
    script.text = js
    path = OUT / name
    path.write_text('<!doctype html>' + html.tostring(doc, encoding='unicode'), encoding='utf-8')
    return path


kakao = read('kakao.html')
save(kakao, 'kakao-long.html', '''
.example-label{display:none!important}
#mainContent .desc_item2{display:block!important;-webkit-line-clamp:unset!important;max-height:none!important;height:auto!important;overflow:visible!important;white-space:pre-line!important}
.info_operation .fold_detail{display:block!important}
#mainContent .info_operation{overflow:visible!important;height:auto!important;max-height:none!important}
html,body{scroll-behavior:auto!important}
''', '''
document.querySelectorAll('.info_operation').forEach(n=>{let p=n;for(let i=0;i<4&&p;i++,p=p.parentElement)p.classList.add('fold_open')});
''')

google = read('google.html')
body = google.find('body')
main = google.xpath('//*[@id="native-google-main"]')[0]
search = google.xpath('//*[@id="native-search"]')[0]
wrapper = etree.Element('div', id='capture-google')
main.set('class', main.get('class') + ' long-part')
main.set('id', 'long-overview')
wrapper.append(main)
for filename, label in [('google_menu.html', 'menu'), ('google_info.html', 'info')]:
    part = deepcopy(read(filename).xpath('//*[@id="native-google-main"]')[0])
    part.set('id', 'long-' + label)
    part.set('class', part.get('class') + ' long-part')
    wrapper.append(part)
for child in list(body):
    body.remove(child)
body.append(wrapper)
body.append(search)
save(google, 'google-long.html', '''
html,body{margin:0!important;background:#f4f5f6!important;overflow:visible!important;height:auto!important;scroll-behavior:auto!important}
#capture-google{position:relative;margin:8px 0 24px 72px;width:408px;background:white;border-radius:24px;overflow:hidden}
.long-part{position:relative!important;left:auto!important;top:auto!important;width:408px!important;height:auto!important;max-height:none!important;overflow:visible!important;background:white!important;border-radius:0!important;display:block!important}
.long-part>.DxyBCb,.long-part [role=region].DxyBCb{height:auto!important;max-height:none!important;overflow:visible!important;flex:none!important}
.long-part .iP2t7d>p{white-space:normal;line-height:20px}
#long-menu,#long-info{border-top:8px solid #f3f4f5}
#native-search{position:absolute!important;left:88px!important;top:16px!important;z-index:30}
#native-search .SxXeRb{display:none!important}
.OqCZI .t39EBf{display:block!important;max-height:none!important;height:auto!important}
''', '''
document.querySelectorAll('.OMl5r').forEach(n=>{n.setAttribute('aria-expanded','true');n.parentElement.classList.add('VrynGf')});
''')

manifest = [
    {'name':'kakao','url':BASE+'long_capture_20261109_01/kakao-long.html','selector':'#mainContent'},
    {'name':'google','url':BASE+'long_capture_20261109_01/google-long.html','selector':'#capture-google'}
]
(OUT/'inputs.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
