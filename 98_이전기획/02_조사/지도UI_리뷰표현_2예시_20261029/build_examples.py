"""Build two local map information proposals; review replies are excluded."""
from pathlib import Path
import base64
import hashlib
import html
import json
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / '지도정비_비포애프터_20261028'


def data_image(name):
    return 'data:image/jpeg;base64,' + base64.b64encode((SOURCE / 'images' / name).read_bytes()).decode('ascii')


PIZZA_ROOT = ROOT.parent / '지도UI_비포애프터_명동피자_20261028'
pizza_edits = json.loads((PIZZA_ROOT / 'source/geo-menu-edits_20261029.json').read_text(encoding='utf-8'))
HISS_URL = 'https://www.google.co.kr/maps/place/힛사츠와자/data=!4m5!3m4!1s0x357c990006a61961:0x93b46c4afa816b00!10e9!16s%2Fg%2F11xsrqylhh'
menu_before = '계란기본제공 x (egg not provided as standard). 기본제공: 차슈 2장, 멘마 2개, 김 1장 (standard provision: 2 slices of chashu, 2 menma, 1 sheet of nori). 면중량 [선택] (noodle weight [select]): 150g (+0), 200g (+0), 300g (+1000). 요청사항 [선택] (requests [select]): 초생강 주세요 (+0), 멘마 빼주세요 (+0), 적양파 많이 (+0) (please give pickled ginger (+0), please remove menma (+0), lots of red onion (+0)).'
menu_lines = [
    ('기본 구성', '차슈 2장 · 멘마 2개 · 김 1장. 계란 미포함.', 'Includes 2 slices of chashu, 2 menma pieces and 1 nori sheet. Egg not included.'),
    ('면 중량 선택', '150g·200g 추가금 없음 / 300g +1,000원.', 'Noodles: 150g or 200g at no extra charge; 300g +KRW 1,000.'),
    ('무료 요청 선택', '초생강 추가 / 멘마 제외 / 적양파 많이.', 'Free requests: pickled ginger; no menma; extra red onion.'),
]

css = '''
*{box-sizing:border-box}html,body{margin:0;background:#fff;color:#202124;font-family:Arial,"Malgun Gothic",sans-serif}button,select{font:inherit}button:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:2px solid #1a73e8;outline-offset:2px}.toolbar{height:44px;display:flex;align-items:center;justify-content:center;gap:26px;border-bottom:1px solid #dadce0;background:#fff}.toolbar select{width:228px;border:0;border-radius:4px;padding:6px 8px;background:#f8f9fa;font-size:12px;color:#3c4043}.tabs{height:100%;display:flex;gap:28px}.tabs button{border:0;border-bottom:2px solid transparent;padding:0 3px;background:#fff;color:#80868b;font-size:12px;font-weight:600;letter-spacing:.6px;cursor:pointer}.tabs button[aria-selected=true]{color:#202124;border-bottom-color:#202124}.stamp{font-size:10px;color:#80868b;white-space:nowrap}.canvas{width:100%;overflow:auto;background:#fff;position:relative}.fit{position:relative;margin:auto}.stage{position:absolute;top:0;left:0;width:1440px;height:709px;transform-origin:top left;overflow:hidden;background-repeat:no-repeat;background-size:1440px 709px}.pizza-frame{display:block;width:100%;height:calc(100dvh - 44px);border:0;background:#fff}.pizza-frame[hidden],.fit[hidden]{display:none}.menu-mask{position:absolute;left:72px;top:179px;width:416px;height:530px;padding:11px 24px;background:#fff;font-size:12px;line-height:16px}.menu-title{margin:0 0 4px;font-size:14px;line-height:20px;font-weight:400}.menu-description{margin:0;white-space:pre-line;font-size:12px;line-height:16px;color:#70757a}.menu-description.after{font-size:13px;line-height:20px}.menu-block{margin:0 0 15px}.menu-block:last-child{margin-bottom:0}.menu-block .ko{display:block;color:#3c4043}.menu-block .en{display:block;color:#70757a;margin-top:3px}.menu-rule{position:absolute;left:0;right:0;height:1px;background:#dadce0}.menu-mask.before .menu-rule{top:150px}.menu-mask.after .menu-rule{top:339px}.popup[hidden]{display:none}@media(max-width:650px){.toolbar{gap:13px;justify-content:space-between;padding:0 10px}.toolbar select{width:190px;font-size:11px}.tabs{gap:14px}.stamp{display:none}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
'''


def menu_panel(state):
    if state == 'before':
        body = '<p class="menu-description">' + html.escape(menu_before) + '</p>'
    else:
        body = '<div class="menu-description after">' + ''.join(
            '<p class="menu-block"><span class="ko">' + html.escape(label + ': ' + ko) + '</span><span class="en">' + html.escape(en) + '</span></p>'
            for label, ko, en in menu_lines) + '</div>'
    return f'<section class="menu-mask {state}" aria-label="차슈멘 메뉴 설명"><h1 class="menu-title">차슈멘 (Chashumen)</h1>{body}<div class="menu-rule"></div></section>'


images = {'hiss': data_image('hiss-google-menu.jpg')}
panels = {'hiss': {'before': '', 'after': menu_panel('after')}}
script = '''
const images=IMAGE_DATA;
const panels=PANEL_DATA;
const stage=document.getElementById('stage'),fit=document.getElementById('fit'),canvas=document.querySelector('.canvas'),pizzaFrame=document.getElementById('pizza-view');
const tabs=[...document.querySelectorAll('[role=tab]')],selector=document.getElementById('case');
let selected='pizza',state='before',pizzaPosition=949.5;
function resize(){if(selected==='pizza'){canvas.style.minHeight='0';return;}const s=Math.min(1,canvas.clientWidth/1440);stage.style.transform=`scale(${s})`;fit.style.width=(1440*s)+'px';fit.style.height=(709*s)+'px';canvas.style.minHeight=(709*s)+'px';}
function render(){const pizza=selected==='pizza';pizzaFrame.hidden=!pizza;fit.hidden=pizza;if(pizza){const url='../지도UI_비포애프터_명동피자_20261028/'+state+'.html';if(pizzaFrame.getAttribute('src')!==url)pizzaFrame.setAttribute('src',url);}else{stage.style.backgroundImage=`url("${images.hiss}")`;stage.innerHTML=panels.hiss[state];stage.setAttribute('aria-label','힛사츠와자 메뉴 설명 '+state.toUpperCase());}tabs.forEach(t=>{t.setAttribute('aria-selected',String(t.dataset.state===state));t.setAttribute('aria-controls',pizza?'pizza-view':'stage');});resize();}
function selectState(next){state=next;render();}
tabs.forEach((tab,i)=>{tab.addEventListener('click',()=>selectState(tab.dataset.state));tab.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const index=event.key==='Home'?0:event.key==='End'?1:1-i;selectState(tabs[index].dataset.state);tabs[index].focus();}});});
selector.addEventListener('change',()=>{selected=selector.value;state='before';render();});
pizzaFrame.addEventListener('load',()=>pizzaFrame.contentWindow.postMessage({type:'seelo-scroll',top:pizzaPosition},'*'));
window.addEventListener('message',event=>{if(event.source===pizzaFrame.contentWindow&&event.data&&event.data.type==='seelo-position')pizzaPosition=event.data.top;});
window.addEventListener('resize',resize);
const requested=new URLSearchParams(location.search).get('case');if(['pizza','hiss'].includes(requested)){selected=requested;selector.value=requested;}
render();
'''.replace('IMAGE_DATA', json.dumps(images)).replace('PANEL_DATA', json.dumps(panels, ensure_ascii=False))

document = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>지도 UI BEFORE / AFTER · 메뉴·이용 조건 정비</title><style>{css}</style></head><body>
<nav class="toolbar" aria-label="정비 시안 전환"><select id="case" aria-label="가게 예시 선택"><option value="pizza">명동피자 · 메뉴·이용 조건</option><option value="hiss">힛사츠와자 · 메뉴 설명</option></select><div class="tabs" role="tablist" aria-label="정비 전후"><button type="button" role="tab" data-state="before" aria-selected="true" aria-controls="stage">BEFORE</button><button type="button" role="tab" data-state="after" aria-selected="false" aria-controls="stage">AFTER</button></div><span class="stamp">10.28 관측 · 승인 전 시안</span></nav><main class="canvas"><iframe id="pizza-view" class="pizza-frame" title="명동피자 메뉴 정비 시안" role="tabpanel"></iframe><div id="fit" class="fit"><div id="stage" class="stage" role="tabpanel"></div></div></main><script>{script}</script></body></html>'''
(ROOT / 'index.html').write_text(document, encoding='utf-8')

evidence = {
    'observedAt':'2026-10-28', 'createdAt':'2026-10-29',
    'decision':'사용자 요청으로 리뷰 답변 대행·수정 예시는 제외. 리뷰는 정보의 혼동을 찾는 참고 자료로만 사용.',
    'status':'승인 전 로컬 시안. 실제 지도 수정 없음.',
    'rendering':'명동피자는 기존 카카오맵 원본 DOM 시안 연결. 힛사츠와자는 보존된 Google 지도 캡처에서 설명 부분만 재현.',
    'currentCheck':'브라우저 제어 비활성화로 새 렌더링 검수 미수행. 2026-10-28 관측 자료 사용.',
    'cases':[
        {'id':'pizza','store':'명동피자 명동본점','field':'카카오 메뉴 8개 이름·설명','source':pizza_edits['sourceUrl'],'edits':pizza_edits['edits'],
         'preserve':['가격 31개','사진 40개','리뷰·업주 답변·평점','브랜드 소개·AI 요약·추천 표시'],
         'limits':'기존 메뉴 시안을 연결한 예시. 사장님 확인·실제 지도 반영·AI 효과 검증 전.'},
        {'id':'hiss','store':'힛사츠와자','field':'Google 차슈멘 설명 1칸','source':HISS_URL,
         'sourceImage':'hiss-google-menu.jpg','before':menu_before,'after':menu_lines,
         'preserve':['차슈2·멘마2·김1','계란 미포함','150g·200g +0','300g +1000','초생강·멘마 제외·적양파 무료 선택'],
         'limits':'기본 메뉴 가격을 추정하지 않음. 추가금과 무료 요청을 분리. 기존 판매 조건과 편집 칸 지원 여부 확인 필요.'},
    ],
    'effect':'가독성과 조건 이해 개선을 위한 가설. AI 추천·인용 증가를 검증한 결과가 아님.',
}
(ROOT / 'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
prices = lambda value: re.findall(r'<p class="desc_item">([^<]+)</p>',value)
before=(PIZZA_ROOT / 'before.html').read_text(encoding='utf-8')
after=(PIZZA_ROOT / 'after.html').read_text(encoding='utf-8')
qa = {
    'selfContained':False,
    'localDependency':'../지도UI_비포애프터_명동피자_20261028/ 폴더와 assets 유지 필요',
    'noRemoteAssets':not bool(re.search(r'(?:src|href)=[\"\']https?://',document)),
    'reviewReplyEditingExcluded':all(value not in document for value in ['업체 대표 응답','reply_after','리뷰 답변']),
    'pizzaPricesUnchanged':prices(before)==prices(after),
    'priceFieldsAddedOrChanged':0,'changedReviewReplies':0,'changedMenuDescriptions':9,
    'linkedPagesExist':all((PIZZA_ROOT / name).is_file() for name in ['before.html','after.html']),
    'browserVerification':'브라우저 비활성화로 정적 검사만 수행.',
}
assert qa['reviewReplyEditingExcluded'] and qa['pizzaPricesUnchanged'] and qa['linkedPagesExist'] and qa['noRemoteAssets']
assert all(value in document for value in ['150g','200g','300g','1,000','계란 미포함','멘마 제외','적양파'])
(ROOT / 'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT / 'interaction_check.js').write_text(script,encoding='utf-8')
print(json.dumps({'html':str(ROOT / 'index.html'),'cases':2,'checks':qa},ensure_ascii=False))
