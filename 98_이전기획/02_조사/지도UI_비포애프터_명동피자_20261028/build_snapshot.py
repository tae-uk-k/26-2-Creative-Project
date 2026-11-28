from pathlib import Path
from urllib.parse import urljoin
import html
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
snapshot = json.loads((ROOT / 'source/dom.json').read_text(encoding='utf-8'))
bundle = json.loads((ROOT / 'source/bundle.json').read_text(encoding='utf-8'))
assets = ROOT / 'assets'
assets.mkdir(exist_ok=True)
paths = {}
for asset in bundle['assets']:
    source = Path(asset['path'])
    name = asset['id'] + source.suffix
    paths[asset['url']] = name
    target = assets / name
    if source.is_file():
        shutil.copy2(source, target)
    elif not target.is_file():
        raise FileNotFoundError(f'보존한 원본 자산이 없습니다: {name}')


def local_urls(text, prefix):
    for url, name in sorted(paths.items(), key=lambda pair: -len(pair[0])):
        for variant in (url, url.removeprefix('https:'), html.escape(url, quote=True), html.escape(url.removeprefix('https:'), quote=True)):
            text = text.replace(variant, prefix + name)
    return text


for asset in bundle['assets']:
    if asset['kind'] != 'stylesheet':
        continue
    source_css = Path(asset['path'])
    if not source_css.is_file():
        continue
    css = source_css.read_text(encoding='utf-8')

    def resolve(match):
        value = match.group(1).strip().strip('\"\'')
        if value.startswith('data:'):
            return match.group(0)
        absolute = urljoin(asset['url'], value)
        return 'url("' + paths[absolute] + '")' if absolute in paths else 'none'

    css = re.sub(r'url\(([^)]+)\)', resolve, css)
    (assets / paths[asset['url']]).write_text(css, encoding='utf-8')

body = local_urls(snapshot['html'], 'assets/')
body = re.sub(r'<script\b[^>]*>.*?</script>', '', body, flags=re.S | re.I)
body = re.sub(r'<iframe\b[^>]*>.*?</iframe>', '', body, flags=re.S | re.I)
body = re.sub(r'\s+on\w+="[^"]*"', '', body, flags=re.I)
edits = json.loads((ROOT / 'source/geo-menu-edits_20261029.json').read_text(encoding='utf-8'))['edits']
after_body = body
for edit in edits:
    old_name = '<strong class="tit_item">' + html.escape(edit['name']) + '</strong>'
    new_name = '<strong class="tit_item">' + html.escape(edit['proposedName']) + '</strong>'
    old_description = '<p class="desc_item2">' + html.escape(edit['originalDescription']) + '</p>'
    new_description = '<p class="desc_item2">' + '<br>'.join(html.escape(line) for line in edit['proposedDescription']) + '</p>'
    candidates = [match.group(0) for match in re.finditer(r'<li(?:\s[^>]*)?>.*?</li>', after_body, re.S) if old_name in match.group(0) and old_description in match.group(0)]
    assert len(candidates) == 1, f"수정 대상 메뉴는 한 곳이어야 합니다: {edit['name']}"
    original_item = candidates[0]
    updated_item = original_item.replace(old_name, new_name, 1).replace(old_description, new_description, 1)
    after_body = after_body.replace(original_item, updated_item, 1)
    after_body = after_body.replace(old_name, new_name)
styles = ''.join('<link rel="stylesheet" href="assets/' + paths[url] + '">' for url in snapshot['styles'] if url in paths)
styles += ''.join('<style>' + local_urls(css, 'assets/') + '</style>' for css in snapshot['inlineStyles'])
script = '''<script>
history.scrollRestoration='manual';
function initialPosition(){window.scrollTo(0,INITIAL_SCROLL);}
window.addEventListener('load',()=>requestAnimationFrame(initialPosition),{once:true});
window.addEventListener('message',event=>{if(event.source===parent&&event.data&&event.data.type==='seelo-scroll')window.scrollTo(0,event.data.top);});
window.addEventListener('scroll',()=>{if(parent!==window)parent.postMessage({type:'seelo-position',top:window.scrollY},'*');},{passive:true});
document.addEventListener('click',event=>{const link=event.target.closest('a');if(link)event.preventDefault();});
</script>'''.replace('INITIAL_SCROLL', str(snapshot['scrollY']))
for state in ('before', 'after'):
    content = body if state == 'before' else after_body
    page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + state.upper() + ' · 명동피자 명동본점</title>' + styles + '</head><body>' + content + script + '</body></html>'
    (ROOT / (state + '.html')).write_text(page, encoding='utf-8')

index = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BEFORE / AFTER · 명동피자 명동본점</title>
<style>
*{box-sizing:border-box}html,body{height:100%;margin:0;background:#fff}body{display:flex;flex-direction:column;font-family:Arial,"Malgun Gothic",sans-serif}.switch{height:40px;min-height:40px;display:flex;justify-content:center;align-items:stretch;gap:28px;border-bottom:1px solid #dedede;background:#fff}.switch button{padding:0 5px;border:0;border-bottom:2px solid transparent;background:none;color:#888;font-size:12px;font-weight:600;letter-spacing:.7px;cursor:pointer}.switch button[aria-selected=true]{border-bottom-color:#202020;color:#202020}.switch button:focus-visible{outline:2px solid #222;outline-offset:-3px}.pages{position:relative;flex:1;min-height:0}.pages iframe{border:0;display:block;position:absolute;inset:0;width:100%;height:100%;background:#fff}.pages iframe[hidden]{display:none}
</style></head><body>
<nav class="switch" role="tablist"><button type="button" id="before-tab" role="tab" aria-selected="true" aria-controls="before-page">BEFORE</button><button type="button" id="after-tab" role="tab" aria-selected="false" aria-controls="after-page">AFTER</button></nav>
<main class="pages"><iframe src="before.html" title="BEFORE" id="before-page" role="tabpanel"></iframe><iframe src="after.html" title="AFTER" id="after-page" role="tabpanel" hidden></iframe></main>
<script>
const tabs=[...document.querySelectorAll('[role=tab]')];
let current=0,position=949.5;
window.addEventListener('message',event=>{const active=document.getElementById(tabs[current].getAttribute('aria-controls'));if(event.source===active.contentWindow&&event.data&&event.data.type==='seelo-position')position=event.data.top;});
function select(index){let next=document.getElementById(tabs[index].getAttribute('aria-controls'));tabs.forEach((tab,i)=>tab.setAttribute('aria-selected',String(i===index)));document.querySelectorAll('iframe').forEach(frame=>frame.hidden=frame!==next);current=index;requestAnimationFrame(()=>next.contentWindow.postMessage({type:'seelo-scroll',top:position},'*'));}
tabs.forEach((tab,index)=>{tab.addEventListener('click',()=>select(index));tab.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();const i=1-current;select(i);tabs[i].focus();}})});
</script></body></html>'''
(ROOT / 'index.html').write_text(index, encoding='utf-8')
(ROOT / 'geo_20261029.html').write_text(index, encoding='utf-8')
print(json.dumps({'html': str(ROOT / 'index.html'), 'assets': len(paths), 'changed_menus': len(edits), 'changed_fields': len(edits) + sum(body.count('<strong class="tit_item">' + html.escape(edit['name']) + '</strong>') for edit in edits)}, ensure_ascii=False))
