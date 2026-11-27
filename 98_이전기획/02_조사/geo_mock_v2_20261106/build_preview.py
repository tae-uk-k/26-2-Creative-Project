from pathlib import Path
from html import escape
from base64 import b64encode
import json

ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
cards=[]
stories=['# 더 미흡한 가상 식당의 지도 정비 예시 v2','',DATA['notice'],'']
for p,title in [('kakao','카카오맵'),('google','Google 지도')]:
 c=DATA[p]
 jpg=ROOT/f'images/{p}_v2.jpg'
 data='data:image/jpeg;base64,'+b64encode(jpg.read_bytes()).decode('ascii')
 facts=''.join('<li>'+escape(x['quote'])+'</li>' for x in c['sources'][2:])
 changes=''.join('<tr><td>'+escape(m['before'])+'<br><span>'+escape(m['before_description'])+'</span></td><td>'+escape(m['after'])+'<br><span>'+escape(m['description']).replace('\n','<br>')+'</span></td></tr>' for m in c['menus'])
 cards.append(f'''<section id="{p}"><div class="heading"><div><small>가상 식당 정비 예시</small><h1>{title} · {escape(c['name'])}</h1></div><a href="images/{p}_v2.jpg" target="_blank">비교 JPG 열기 ↗</a></div><p class="explain">비포는 반복 키워드·감성적인 문구·모호한 메뉴 설명으로 구성했습니다. 애프터는 같은 원자료에서 음식 특징·인분·구성·조건을 추출해 연결했습니다.</p><img class="comparison" src="{data}" alt="{title} 가상 식당 소개와 메뉴 정비 전후 비교" width="1248" height="1308"><details><summary>어떤 자료로 무엇을 고쳤나</summary><p>가상 메뉴판 두 장에서 다음 사실을 읽었다는 설정입니다.</p><ul>{facts}</ul><table><thead><tr><th>BEFORE · 연결이 부실한 정보</th><th>AFTER · 사실과 조건 연결</th></tr></thead><tbody>{changes}</tbody></table><p>추가하지 않은 정보: {escape(' · '.join(c['unresolved']))}</p><p><a href="{p}_intro_before.html">소개 BEFORE HTML</a> · <a href="{p}_intro_after.html">소개 AFTER HTML</a> · <a href="{p}_menu_before.html">메뉴 BEFORE HTML</a> · <a href="{p}_menu_after.html">메뉴 AFTER HTML</a></p></details></section>''')
 stories+=['## '+title+' — '+c['name'],'','### 원래 상태','','소개: '+c['intro_before'],'']
 stories+=['- '+m['before']+' '+m['price']+' / '+m['before_description'] for m in c['menus']]
 stories+=['','### 활용한 가상 정보','']+['- '+s['id']+': '+s['quote'] for s in c['sources'][2:]]
 stories+=['','### 정비 후','','소개: '+c['intro_after'],'']+['- '+m['after']+' '+m['price']+' / '+m['description'].replace('\n',' / ') for m in c['menus']]
 stories+=['','이전 버전보다 비포를 더 미흡하게 구성했으나, 가격과 가상 원자료는 유지했다.','']
page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>지도 정비 비교 v2 · 카카오·Google 가상 식당</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f6;color:#202124;font:14px Arial,"Malgun Gothic",sans-serif}header{padding:18px 24px;background:white;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;gap:20px;align-items:center}header strong{font-size:18px}header p{font-size:12px;color:#777;margin:8px 0 0}nav{display:flex;gap:18px}a{color:#3c555f;text-decoration:none}a:hover{text-decoration:underline}main{max-width:1296px;margin:auto;padding:22px}section{margin-bottom:38px}.heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.heading h1{margin:6px 0;font-size:21px}.heading small{font-size:11px;color:#80868b}.heading a{font-size:12px}.explain{line-height:1.8;color:#5f6368;font-size:13px}.comparison{display:block;width:100%;height:auto;border:1px solid #dadce0;background:white}details{padding:16px 20px;background:white;border:1px solid #dadce0;border-top:0;font-size:13px;line-height:1.9}summary{cursor:pointer;font-weight:bold}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{padding:13px;text-align:left;border:1px solid #ddd;vertical-align:top}td span{font-size:12px;color:#666}footer{padding:0 0 24px;color:#777;font-size:12px}@media(max-width:700px){header{display:block}nav{margin-top:14px}main{padding:12px}.heading{align-items:flex-start}.heading h1{font-size:17px}}</style></head><body><header><div><strong>같은 가게, 흩어진 정보를 정리하면</strong><p>v2 · 소개와 설명이 더 미흡한 가상 식당 · 모든 상호·가격·메뉴판은 가상 설정</p></div><nav><a href="#kakao">카카오맵</a><a href="#google">Google 지도</a></nav></header><main>'''+''.join(cards)+'''<footer>이미지를 HTML 안에 포함해 CSS·iframe·서버 없이도 볼 수 있습니다. 기존 버전은 보존했습니다.</footer></main></body></html>'''
(ROOT/'index.html').write_text(page,encoding='utf-8')
(ROOT/'story.md').write_text('\n'.join(stories),encoding='utf-8')
print(json.dumps({'embedded_jpgs':2,'iframe_count':page.count('<iframe'),'html_bytes':len(page.encode('utf-8'))},ensure_ascii=False))
