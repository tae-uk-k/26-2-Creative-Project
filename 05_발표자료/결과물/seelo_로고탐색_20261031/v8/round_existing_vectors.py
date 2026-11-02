from pathlib import Path
import json
from shapely.geometry import Polygon
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent

def cubic(a,b,c,d):
    return [((1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0],(1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1]) for t in [i/100 for i in range(101)]]
def quadratic(a,b,c):
    return [((1-t)**2*a[0]+2*(1-t)*t*b[0]+t*t*c[0],(1-t)**2*a[1]+2*(1-t)*t*b[1]+t*t*c[1]) for t in [i/100 for i in range(101)]]

# Original P06 / P12 vector coordinates. Attached bitmaps are identification references only.
P06=[
 Polygon([(8,8),(57,8),(57,57)]+cubic((57,57),(29.9,57),(8,35.1),(8,8))),
 Polygon([(114,8),(114,57),(65,57)]+cubic((65,57),(65,29.9),(86.9,8),(114,8))),
 Polygon([(57,65),(57,114),(8,114)]+cubic((8,114),(8,86.9),(29.9,65),(57,65))),
 Polygon([(65,65)]+cubic((65,65),(92.1,65),(114,86.9),(114,114))+[(65,114)])
]
P12=[
 Polygon([(8,8),(58,8),(58,58)]),
 Polygon([(112,8),(112,58),(66,58),(66,54)]+quadratic((66,54),(66,8),(112,8))),
 Polygon([(8,66),(58,66)]+quadratic((58,66),(58,112),(8,112))),
 Polygon([(66,66),(112,66),(112,112)])
]

def rings(g):
    gs=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
    for p in gs:
        yield list(p.exterior.coords),False
        for r in p.interiors:yield list(r.coords),True
def paths(g):
    return ' '.join('M '+' L '.join(f'{x:.4f} {y:.4f}' for x,y in pts)+' Z' for pts,hole in rings(g))

defs=[]
for number,parts in enumerate([P06,P12],1):
    for level,r in [('light',2.6),('soft',5.2)]:
        rounded=[p.buffer(-r,quad_segs=16).buffer(r,quad_segs=16).simplify(.025,preserve_topology=True) for p in parts]
        key=f'D{len(defs)+1:02d}'
        body=''.join(f'<path d="{paths(p)}" fill="black" fill-rule="evenodd"/>' for p in rounded)
        defs.append({'key':key,'source':'P06' if number==1 else 'P12','reference':number,'level':level,'radius':r,'name':('첫 번째' if number==1 else '두 번째')+' · '+('약한 라운드' if level=='light' else '더 둥근 라운드'),'svg':f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">{body}</svg>','_parts':rounded})

(ROOT/'svg').mkdir(parents=True,exist_ok=True)
for d in defs:(ROOT/'svg'/f'{d["key"]}-source.svg').write_text(d['svg'],encoding='utf-8')

S=3;im=Image.new('RGB',(1080*S,420*S),'#080808');draw=ImageDraw.Draw(im)
for i,d in enumerate(defs):
    ox=(i*270+45)*S;oy=62*S;scale=180/120*S
    for p in d['_parts']:
        for pts,hole in rings(p):draw.polygon([(ox+x*scale,oy+y*scale) for x,y in pts],fill='#080808' if hole else '#ffffff')
    draw.text(((i*270+117)*S,300*S),d['key'],fill='#aaaaaa',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13*S))
im.resize((1080,420),Image.Resampling.LANCZOS).save(ROOT/'rounded-preview.png')
for d in defs:d.pop('_parts')
(ROOT/'geometry.json').write_text(json.dumps(defs,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'key':d['key'],'source':d['source'],'radius':d['radius']} for d in defs]))
