"""보존한 지도 UI 틀과 가상 문구로 정적 비교 자료 생성. 브라우저 실행 없음."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / '지도UI_가상식당_정비스토리_20261106' / 'images'
OUT = ROOT / 'images'
OUT.mkdir(exist_ok=True)
DATA = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))
S = 2

def font(size, bold=False):
    return ImageFont.truetype(str(Path('C:/Windows/Fonts') / ('malgunbd.ttf' if bold else 'malgun.ttf')), round(size*S))

def wrap(text, f, width):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for ch in paragraph:
            if f.getlength(line+ch)>width*S and line:
                lines.append(line.rstrip()); line=ch.lstrip()
            else: line+=ch
        lines.append(line)
    return lines

def write(im, text, x, y, width, size=14, line=20, color='#777', bold=False):
    d=ImageDraw.Draw(im);f=font(size,bold)
    for part in wrap(text,f,width):
        d.text((x*S,y*S),part,font=f,fill=color,anchor='lt');y+=line
    return y

def rect(im,box,fill,outline=None,radius=None):
    b=tuple(round(x*S) for x in box);d=ImageDraw.Draw(im)
    if radius is None:d.rectangle(b,fill=fill,outline=outline,width=S)
    else:d.rounded_rectangle(b,radius*S,fill=fill,outline=outline,width=S)

def icon(im, kind, x, y):
    d=ImageDraw.Draw(im);c='#999999'
    if kind=='pin':
        d.ellipse((x*S,y*S,(x+11)*S,(y+11)*S),fill=c)
        d.polygon([((x+2)*S,(y+8)*S),((x+5.5)*S,(y+16)*S),((x+9)*S,(y+8)*S)],fill=c)
        d.ellipse(((x+4)*S,(y+4)*S,(x+7)*S,(y+7)*S),fill='white')
    else:
        d.ellipse((x*S,y*S,(x+13)*S,(y+13)*S),fill=c)
        d.line([((x+6)*S,(y+2)*S),((x+6)*S,(y+7)*S),((x+10)*S,(y+9)*S)],fill='white',width=S)

def base(platform,view,state):
    path=OLD/f'{platform}_{view}_before_final.png'
    im=Image.open(path).convert('RGB')
    if platform=='kakao':im=im.crop((340,0,940,720))
    if im.height<720:
        bigger=Image.new('RGB',(600,720),'white');bigger.paste(im,(0,0));im=bigger
    return im.resize((1200,1440),Image.Resampling.LANCZOS)

qa=[]
def render(platform,view,state):
    c=DATA[platform];im=base(platform,view,state)
    if view=='intro':
        text=c['intro_'+state]
        if platform=='kakao':
            rect(im,(1,107,599,650),'white')
            lines=wrap(text,font(14),520);bottom=171+len(lines)*20+16
            rect(im,(24,126,576,bottom),'#f7f7f7',radius=12)
            write(im,c['name'],40,143,520,16,20,'#202124',True)
            write(im,text,40,174,520,14,20,'#444')
            y=bottom+30
            icon(im,'pin',26,y);write(im,'서울 성동구 성수이로 00길 00 1층',54,y,520,14,20,'#555')
            rect(im,(1,y+30,599,y+30),'#ededed')
            icon(im,'clock',26,y+45);write(im,'매일 11:00 ~ 21:00',54,y+45,520,14,20,'#555')
        else:
            rect(im,(0,129,407,718),'white')
            write(im,c['name']+' 정보',24,159,360,22,28,'#1f1f1f')
            write(im,'비즈니스 소유자가 제공한 설명',24,211,360,14,20,'#202124',True)
            end=write(im,text,24,246,360,14,22,'#333')
            y=end+24;rect(im,(0,y,407,y),'#dadce0')
            icon(im,'pin',25,y+30);write(im,'서울 마포구 망원로 00길 00',52,y+30,330,14,22,'#5e5e5e')
            icon(im,'clock',25,y+68);write(im,'매일 11:00~21:00',52,y+68,330,14,22,'#5e5e5e')
        height=450
    else:
        y=306 if platform=='kakao' else 306
        width=554 if platform=='kakao' else 360
        x=24
        edge=599 if platform=='kakao' else 407
        rect(im,(1 if platform=='kakao' else 0,295,edge,718),'white')
        for m in c['menus']:
            name=m['before'] if state=='before' else m['after']
            desc=m['before_description'] if state=='before' else m['description']
            y=write(im,name,x,y,width,16 if platform=='kakao' else 14,22,'#222')
            if platform=='kakao':
                y=write(im,m['price'],x,y+2,width,16,22,'#151515',True)
                y=write(im,desc,x,y+2,width,14,20,'#777')
            else:
                y=write(im,desc,x,y+1,width,12,17,'#5e5e5e')
                y=write(im,m['price'],x,y+3,width,12,17,'#5e5e5e')
            y+=16
            rect(im,(x,y,edge if platform=='google' else 576,y),'#e5e5e5')
            y+=18
        qa.append({'platform':platform,'state':state,'content_bottom':y,'fits_720':y<=720})
        height=705
    im=im.crop((0,0,1200,height*S))
    im.save(OUT/f'{platform}_{view}_{state}.png')
    return im

for platform in ['kakao','google']:
    intro=[render(platform,'intro',state) for state in ['before','after']]
    menus=[render(platform,'menu',state) for state in ['before','after']]
    c=DATA[platform];label=('카카오맵' if platform=='kakao' else 'Google 지도')+' · '+c['name']
    page=Image.new('RGB',(1248*S,1308*S),'#f3f4f5')
    write(page,label+'  |  가상 식당 정비 예시 v2',16,12,1200,18,24,'#202124',True)
    write(page,'BEFORE · 흩어지고 모호한 정보',16,48,600,13,18,'#804936',True)
    write(page,'AFTER · 기존 소개·메뉴·메뉴판의 사실로 정리',632,48,600,13,18,'#216957',True)
    for i,im in enumerate(intro):page.paste(im,(round((16+i*616)*S),78*S))
    write(page,'소개 정비: 키워드·방문 요청 반복 → 어떤 음식을 어떻게 만드는지',16,540,1210,13,18,'#5f6368')
    for i,im in enumerate(menus):page.paste(im,(round((16+i*616)*S),577*S))
    write(page,'가상 설정 · 전후 메뉴 가격 동일 · 실제 지도 수정 없음',16,1290,1210,11,16,'#80868b')
    page.resize((1248,1308),Image.Resampling.LANCZOS).save(OUT/f'{platform}_v2.jpg',quality=96,subsampling=0)
    page.save(OUT/f'{platform}_v2_2x.png')
    # 메뉴만 크게 비교할 수 있는 가벼운 별도 이미지.
    compact=Image.new('RGB',(1248*S,780*S),'#f3f4f5')
    write(compact,label+'  |  가상 메뉴 정비',16,10,1210,18,24,'#202124',True)
    write(compact,'BEFORE',16,44,600,12,18,'#804936',True)
    write(compact,'AFTER',632,44,600,12,18,'#216957',True)
    for i,im in enumerate(menus):compact.paste(im,((16+i*616)*S,70*S))
    compact.resize((1248,780),Image.Resampling.LANCZOS).save(OUT/f'{platform}_menu_v2.jpg',quality=96,subsampling=0)
assert all(r['fits_720'] for r in qa),qa
(ROOT/'export_qa.json').write_text(json.dumps({'renderer':'정적 문서 이미지 합성. 브라우저 재검수 아님.','layout':qa,'fictional':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(qa,ensure_ascii=False))
