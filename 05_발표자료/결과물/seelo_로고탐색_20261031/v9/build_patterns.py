from pathlib import Path
import json,math
from shapely.geometry import Polygon
from shapely.ops import unary_union
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent
def turn(points,deg):
    a=deg*math.pi/180
    return [[60+(x-60)*math.cos(a)-(y-60)*math.sin(a),60+(x-60)*math.sin(a)+(y-60)*math.cos(a)] for x,y in points]
base=[[4,4],[108,4],[40,52]]
tri=[[60,2],[118,86],[68,76]]
DEFS=[
 {'key':'E01','rule':'반전된 두 면 · 같은 비움 반복','positive':[[[4,4],[116,42],[4,116]],[[116,4],[116,116],[4,78]]],'negative':[[[20,29],[56,42],[22,64]],[[100,91],[64,78],[98,56]]]},
 {'key':'E02','rule':'세 삼각형 · 대각으로 이어지는 적층','positive':[[[4,4],[116,4],[74,44]],[[4,54],[100,34],[116,90]],[[4,78],[46,116],[116,116]]],'negative':[]},
 {'key':'E03','rule':'평행 대각 · 삼각 비움의 반전','positive':[[[4,4],[76,4],[4,116]],[[116,4],[116,116],[44,116]]],'negative':[[[18,21],[54,21],[18,77]],[[102,99],[66,99],[102,43]]]},
 {'key':'E04','rule':'위아래 반전 · 두 삼각 비움','positive':[[[4,4],[116,4],[60,116]],[[4,116],[116,116],[60,4]]],'negative':[[[29,34],[59,34],[44,66]],[[61,86],[91,86],[76,54]]]},
 {'key':'E05','rule':'같은 삼각형 · 90도 회전 반복','positive':[turn(base,a) for a in [0,90,180,270]],'negative':[]},
 {'key':'E06','rule':'두 크기의 삼각형 · 대각 맞물림','positive':[[[4,4],[92,4],[4,72]],[[116,48],[116,116],[28,116]],[[4,80],[4,116],[52,116]],[[68,4],[116,4],[116,40]]],'negative':[]}
]

def rounded(points,r=11):
    pts=[]
    for i,p in enumerate(points):
        a=points[(i-1)%3];b=points[(i+1)%3]
        la=math.dist(a,p);lb=math.dist(b,p);d=min(r,la*.32,lb*.32)
        u=(p[0]+(a[0]-p[0])*d/la,p[1]+(a[1]-p[1])*d/la)
        v=(p[0]+(b[0]-p[0])*d/lb,p[1]+(b[1]-p[1])*d/lb)
        for j in range(33):
            t=j/32;s=1-t
            pts.append((s*s*u[0]+2*s*t*p[0]+t*t*v[0],s*s*u[1]+2*s*t*p[1]+t*t*v[1]))
    return Polygon(pts)

def rings(g):
    for p in list(g.geoms) if g.geom_type=='MultiPolygon' else [g]:
        yield list(p.exterior.coords),False
        for ring in p.interiors:yield list(ring.coords),True
def svgpath(g):
    return ' '.join('M '+' L '.join(f'{x:.4f} {y:.4f}' for x,y in ring)+' Z' for ring,hole in rings(g))

(ROOT/'svg').mkdir(parents=True,exist_ok=True)
for d in DEFS:
    pg=unary_union([rounded(t,12) for t in d['positive']]);ng=unary_union([rounded(t,6) for t in d['negative']])
    g=pg.difference(ng)
    if d['key']!='E05':g=g.buffer(-2.6,quad_segs=12).buffer(2.6,quad_segs=12).buffer(2.6,quad_segs=12).buffer(-2.6,quad_segs=12)
    g=g.simplify(.035,preserve_topology=True)
    d['count']=len(d['positive'])+len(d['negative']);d['coverage']=round(g.area/14400*100,2)
    assert d['count']<=4 and d['coverage']>=33,(d['key'],d['count'],d['coverage'])
    d['svg']=f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120"><path d="{svgpath(g)}" fill="black" fill-rule="evenodd"/></svg>'
    (ROOT/'svg'/f'{d["key"]}-source.svg').write_text(d['svg'],encoding='utf-8');d['_geom']=g

S=3;im=Image.new('RGB',(1200*S,730*S),'white');dr=ImageDraw.Draw(im)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13*S)
for i,d in enumerate(DEFS):
    x=(i%3)*400;y=(i//3)*365;ox=(x+99)*S;oy=(y+48)*S;sc=202/120*S
    for ring,hole in sorted(rings(d['_geom']),key=lambda x:x[1]):
        dr.polygon([(ox+px*sc,oy+py*sc) for px,py in ring],fill='white' if hole else '#080808')
    dr.text(((x+185)*S,(y+292)*S),d['key'],font=font,fill='#777777')
im.resize((1200,730),Image.Resampling.LANCZOS).save(ROOT/'pattern-preview.png')
for d in DEFS:d.pop('_geom')
(ROOT/'geometry.json').write_text(json.dumps(DEFS,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:d[k] for k in ['key','count','coverage']} for d in DEFS]))
