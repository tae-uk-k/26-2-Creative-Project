from pathlib import Path
import json,re,math
from shapely.geometry import LineString
from shapely.ops import unary_union,polygonize

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'before.json').read_text(encoding='utf-8'))

def parse_path(s):
    tokens=re.findall(r'[MLCQHVZmlcqhvz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',s)
    i=0;cmd=None;cur=(0,0);start=None;pts=[];loops=[]
    def n():
        nonlocal i
        x=float(tokens[i]);i+=1;return x
    def close():
        nonlocal pts
        if len(pts)>2:
            if pts[-1]!=pts[0]:pts.append(pts[0])
            loops.append(pts)
        pts=[]
    while i<len(tokens):
        if tokens[i].isalpha():cmd=tokens[i];i+=1
        if cmd=='M':
            if pts:close()
            cur=(n(),n());start=cur;pts=[cur];cmd='L'
        elif cmd=='L':cur=(n(),n());pts.append(cur)
        elif cmd=='H':cur=(n(),cur[1]);pts.append(cur)
        elif cmd=='V':cur=(cur[0],n());pts.append(cur)
        elif cmd=='C':
            a=cur;b=(n(),n());c=(n(),n());d=(n(),n())
            for k in range(1,65):
                t=k/64;u=1-t;pts.append((u**3*a[0]+3*u*u*t*b[0]+3*u*t*t*c[0]+t**3*d[0],u**3*a[1]+3*u*u*t*b[1]+3*u*t*t*c[1]+t**3*d[1]))
            cur=d
        elif cmd=='Q':
            a=cur;b=(n(),n());c=(n(),n())
            for k in range(1,65):
                t=k/64;u=1-t;pts.append((u*u*a[0]+2*u*t*b[0]+t*t*c[0],u*u*a[1]+2*u*t*b[1]+t*t*c[1]))
            cur=c
        elif cmd=='Z':
            close();cur=start;cmd=None
        else:raise ValueError(cmd)
    if pts:close()
    return loops

def winding(loop,x,y):
    w=0
    for a,b in zip(loop,loop[1:]):
        cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
        if a[1]<=y<b[1] and cross>0:w+=1
        if b[1]<=y<a[1] and cross<0:w-=1
    return w

out=[]
for pattern,source,target in [('P08','366:409',4.5),('P09','366:442',4.5),('P12','366:508',14)]:
    v=next(x for x in data['vectors'] if x['id']==source)
    geoms=[]
    for path in v['paths']:
        loops=parse_path(path['data'])
        faces=polygonize(unary_union([LineString(loop) for loop in loops]))
        selected=[]
        for face in faces:
            rp=face.representative_point();w=sum(winding(loop,rp.x,rp.y) for loop in loops)
            if (w%2!=0) if path['windingRule']=='EVENODD' else (w!=0):selected.append(face)
        geoms.append(unary_union(selected))
    g=unary_union(geoms)
    pieces=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
    rounded=[];radii=[]
    for piece in pieces:
        r=min(target,.4*2*piece.area/piece.length)
        rr=piece.buffer(-r,quad_segs=16).buffer(r,quad_segs=16).simplify(.015,preserve_topology=True)
        if rr.is_empty:raise ValueError('rounding removed a piece')
        rounded.append(rr);radii.append(round(r,3))
    result=unary_union(rounded)
    final=list(result.geoms) if result.geom_type=='MultiPolygon' else [result]
    contours=[]
    for poly in final:
        contours.append(list(poly.exterior.coords))
        contours.extend(list(r.coords) for r in poly.interiors)
    d=' '.join('M '+' L '.join(f'{x:.4f} {y:.4f}' for x,y in c)+' Z' for c in contours)
    out.append({'pattern':pattern,'targets':[x['id'] for x in data['vectors'] if x['pattern']=='Abstract / '+pattern],'data':d,'pieces':len(pieces),'radii':radii,'areaBefore':round(g.area,3),'areaAfter':round(result.area,3)})
(ROOT/'shared-corner-paths.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:x[k] for k in ['pattern','pieces','radii','areaBefore','areaAfter']} for x in out]))
