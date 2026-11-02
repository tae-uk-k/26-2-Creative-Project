from pathlib import Path
import json
from shapely.geometry import Polygon
from shapely.ops import unary_union
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
DEFS=[
 {'key':'B01','name':'01','positive':[[[4,4],[116,4],[4,116]]], 'negative':[[[24,18],[93,18],[24,37]],[[18,53],[59,53],[18,77]]]},
 {'key':'B02','name':'02','positive':[[[4,4],[116,4],[4,116]],[[116,116],[116,17],[17,116]]], 'negative':[[[20,18],[81,18],[20,49]],[[100,102],[39,102],[100,71]]]},
 {'key':'B03','name':'03','positive':[[[4,4],[116,44],[4,116]],[[116,4],[116,116],[4,76]]], 'negative':[[[41,35],[90,56],[48,93]]]},
 {'key':'B04','name':'04','positive':[[[4,4],[90,4],[4,90]],[[116,30],[116,116],[30,116]],[[33,43],[85,38],[72,91]]], 'negative':[[[46,52],[69,45],[68,71]]]}
]

def rounded_triangle(points,r=11):
    sample=[]
    for i,p in enumerate(points):
        a=points[(i-1)%3];b=points[(i+1)%3]
        la=((a[0]-p[0])**2+(a[1]-p[1])**2)**.5
        lb=((b[0]-p[0])**2+(b[1]-p[1])**2)**.5
        d=min(r,la*.32,lb*.32)
        u=(p[0]+(a[0]-p[0])*d/la,p[1]+(a[1]-p[1])*d/la)
        v=(p[0]+(b[0]-p[0])*d/lb,p[1]+(b[1]-p[1])*d/lb)
        for j in range(25):
            t=j/24;s=1-t
            sample.append((s*s*u[0]+2*s*t*p[0]+t*t*v[0],s*s*u[1]+2*s*t*p[1]+t*t*v[1]))
    return Polygon(sample)

def contours(g):
    ps=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
    for p in ps:
        yield list(p.exterior.coords),False
        for r in p.interiors:yield list(r.coords),True

def svg_path(g):
    return ' '.join('M '+' L '.join(f'{x:.4f} {y:.4f}' for x,y in ring)+' Z' for ring,hole in contours(g))

(ROOT/'svg').mkdir(parents=True,exist_ok=True)
for d in DEFS:
    positive=unary_union([rounded_triangle(p,12) for p in d['positive']])
    negative=unary_union([rounded_triangle(p,6) for p in d['negative']])
    g=positive.difference(negative)
    g=g.buffer(-2.0,quad_segs=8).buffer(2.0,quad_segs=8)
    g=g.buffer(1.4,quad_segs=8).buffer(-1.4,quad_segs=8)
    g=g.simplify(0.045,preserve_topology=True)
    d['count']=len(d['positive'])+len(d['negative'])
    d['coverage']=round(g.area/14400*100,2)
    d['path']=svg_path(g)
    d['svg']=f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120"><path d="{d["path"]}" fill="black" fill-rule="evenodd"/></svg>'
    assert d['count']<=4 and d['coverage']>=33,(d['key'],d['count'],d['coverage'])
    (ROOT/'svg'/f'{d["key"]}-source.svg').write_text(d['svg'],encoding='utf-8')
    d['_geom']=g

S=3;im=Image.new('RGB',(1200*S,380*S),'white');draw=ImageDraw.Draw(im)
for i,d in enumerate(DEFS):
    ox=(i*300+55)*S;oy=65*S;scale=190/120*S
    rings=list(contours(d['_geom']))
    for ring,hole in sorted(rings,key=lambda x:x[1]):
        draw.polygon([(ox+x*scale,oy+y*scale) for x,y in ring],fill='white' if hole else '#080808')
    draw.text(((i*300+140)*S,310*S),d['name'],fill='#555555',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14*S))
im.resize((1200,380),Image.Resampling.LANCZOS).save(ROOT/'geometry-review.png')
for d in DEFS:d.pop('_geom')
(ROOT/'geometry.json').write_text(json.dumps(DEFS,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:d[k] for k in ['key','count','coverage']} for d in DEFS]))
