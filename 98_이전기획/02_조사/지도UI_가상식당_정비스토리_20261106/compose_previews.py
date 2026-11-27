from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json

ROOT=Path(__file__).resolve().parent
IMAGES=ROOT/'images'
data=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
font=ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf',17)
small=ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf',12)

def capture(platform,view,state):
 im=Image.open(IMAGES/f'{platform}_{view}_{state}_final.png').convert('RGB')
 if platform=='kakao':
  assert im.size==(1280,720),im.size
  return im.crop((340,0,940,720))
 assert im.width==600,im.size
 return im

def row(page,before,after,y,height):
 for i,im in enumerate([before,after]):
  x=16+i*616
  page.paste(im.crop((0,0,600,height)),(x,y))
  ImageDraw.Draw(page).rectangle((x-1,y-1,x+600,y+height),outline='#dfe1e5')

for p in ['kakao','google']:
 label=('카카오맵' if p=='kakao' else 'Google 지도')+' · '+data[p]['name']
 intro_h=350 if p=='kakao' else 400
 menu_h=640 if p=='kakao' else 600
 intro=[capture(p,'intro',s) for s in ['before','after']]
 menus=[capture(p,'menu',s) for s in ['before','after']]
 page=Image.new('RGB',(1248,132+intro_h+menu_h),'#f3f4f5')
 d=ImageDraw.Draw(page)
 d.text((16,10),label+' · 가상 식당 정비 예시',font=font,fill='#202124')
 d.text((16,38),'BEFORE · 원래 지도 정보',font=small,fill='#5f6368')
 d.text((632,38),'AFTER · 기존 소개·메뉴·가상 메뉴판에서 추출해 완성',font=small,fill='#5f6368')
 row(page,*intro,64,intro_h)
 mid=64+intro_h
 d.text((16,mid+12),'메뉴 정비 · 같은 가게, 같은 가격',font=small,fill='#5f6368')
 row(page,*menus,mid+40,menu_h)
 d.text((16,page.height-21),'매장·소개·가격·메뉴판은 모두 가상 설정입니다.',font=small,fill='#80868b')
 page.save(IMAGES/f'{p}_story_before_after.png')
 menu=Image.new('RGB',(1248,menu_h+94),'#f3f4f5')
 d=ImageDraw.Draw(menu);d.text((16,10),label+' · 가상 메뉴 정비',font=font,fill='#202124')
 d.text((16,42),'BEFORE',font=small,fill='#5f6368');d.text((632,42),'AFTER',font=small,fill='#5f6368')
 row(menu,*menus,68,menu_h)
 menu.save(IMAGES/f'{p}_menu_before_after.png')
print(json.dumps({'comparison_images':4,'fictional':True},ensure_ascii=False))
