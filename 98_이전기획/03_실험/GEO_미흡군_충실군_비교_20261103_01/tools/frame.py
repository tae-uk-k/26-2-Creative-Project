"""Parse new native-map observations; candidate identity requires detail review."""
import argparse
import csv
import itertools
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]

def key(s):return re.sub('[^가-힣a-z0-9]','',unicodedata.normalize('NFC',s).lower())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('version');args=parser.parse_args()
    captures=[json.loads(l) for l in (ROOT/'evidence'/'browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    latest={}
    for c in captures:
        if c.get('kind')=='search' and c.get('area') in {'MD','SS','MW'}:latest[c['platform'],c['area'],c['query'],str(c['page']),c.get('condition_id','default')]=c
    cards=[]
    for (platform,area,query,page,condition),c in latest.items():
        if platform=='kakao' and condition=='region_v1':
            expected={'MD':'서울 중구 명동','SS':'서울 성동구 성수','MW':'서울 마포구 망원'}[area]
            displayed=c.get('displayed_condition','')
            if not (expected in displayed and '주변' in displayed):
                raise ValueError('Unverified regional interpretation: '+repr((area,query,page,displayed)))
        seen=set();natural=0
        for r in c['rows']:
            txt=r.get('text','') or '';lines=txt.splitlines();url=r.get('url','') or ''
            if platform=='google':
                m=re.search('!19s([^!/?]+)',url);pid=unquote(m[1]) if m else ''
                sponsored=r.get('sponsored',False) or '스폰서' in txt or ('사이트 방문하기' in txt and '' in txt)
                name=r.get('name','') or ''
                rm=re.search(r'(?m)^([0-5]\.\d)\(([\d,]+)\)',txt)
                catline=next((l for l in lines if ' · ' in l),'')
                category=catline.split(' · ')[0];address=catline.split(' · ')[-1]
                if sponsored or not pid or pid in seen:continue
                seen.add(pid);natural+=1;rank=natural
            else:
                name=lines[0] if lines else '';pid=url.rsplit('/',1)[-1];sponsored=False
                rm=re.search(r'별점\n([0-5]\.\d)\n([\d,]+)건',txt)
                address=next((l for l in lines if l.startswith('서울 ')),'')
                catline=next((l for l in lines if re.match(r'^[A-O] ',l)),'')
                category=catline[2:].removeprefix(name).strip();rank=(int(page)-1)*15+r['rank']
            if rank>min(60,int(c.get('requested_limit',60))):continue
            cards.append(dict(platform=platform,area_id=area,query=query,condition_id=condition,rank=rank,name=name,place_id=pid,url=url,
                address_card=address,category_card=category,rating=rm[1] if rm else '',reviews=rm[2].replace(',','') if rm else '',
                observed_at=c['observed_at'],evidence_scope='native_search_card_only',raw_card=txt))
    # Retain every observed position, but match using a store's first native rank.
    raw_positions=list(cards)
    first={}
    for card in sorted(cards,key=lambda x:int(x['rank'])):
        identity=tuple(card[k] for k in ['platform','area_id','query','condition_id','place_id'])
        first.setdefault(identity,card)
    cards=list(first.values())
    candidates=[]
    for k in [c for c in cards if c['platform']=='kakao']:
        kn=key(k['name'])
        for g in [c for c in cards if c['platform']=='google' and c['area_id']==k['area_id'] and c['query']==k['query'] and c['condition_id']==k['condition_id']]:
            gn=key(g['name'])
            names=(kn==gn or len(kn)>=3 and kn in gn or len(gn)>=3 and gn in kn)
            ka=re.search(r'([가-힣0-9]+(?:대로|로|길)\s+\d+(?:-\d+)?)',k['address_card'])
            addr=ka and re.search(re.escape(ka[1])+r'(?![\d-])',g['address_card'])
            if not (names or addr):continue
            candidates.append(dict(store_id=k['area_id']+'-'+k['place_id'],area_id=k['area_id'],query=k['query'],condition_id=k['condition_id'],
                name=k['name'],kakao_id=k['place_id'],kakao_url=k['url'],kakao_rank=k['rank'],kakao_address=k['address_card'],kakao_category=k['category_card'],
                google_name=g['name'],google_id=g['place_id'],google_url=g['url'],google_rank=g['rank'],google_address=g['address_card'],google_category=g['category_card'],
                google_rating=g['rating'],google_reviews=g['reviews'],identity_status='requires_detail_review',name_match=bool(names),address_match=bool(addr)))
    dest=ROOT/'analysis'/args.version;dest.mkdir(exist_ok=False)
    for name,data in [('native_cards.csv',cards),('native_raw_positions.csv',raw_positions),('crossmap_candidates.csv',candidates)]:
        with (dest/name).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,list(data[0]));w.writeheader();w.writerows(data)
    feasible=[]
    for a,b in itertools.combinations(candidates,2):
        if a['query']!=b['query'] or a['condition_id']!=b['condition_id'] or a['area_id']!=b['area_id'] or a['store_id']==b['store_id']:continue
        if any(abs(int(a[k])-int(b[k]))>20 for k in ['kakao_rank','google_rank']):continue
        try:
            gap=abs(float(a['google_rating'])-float(b['google_rating']))
            ca,cb=int(a['google_reviews']),int(b['google_reviews'])
            if min(ca,cb)<=0 or max(ca,cb)/min(ca,cb)>8 or gap>.60000001:continue
        except ValueError:continue
        feasible.append(dict(area=a['area_id'],query=a['query'],condition_id=a['condition_id'],a=a['store_id'],name_a=a['name'],cat_a=a['kakao_category'],
            b=b['store_id'],name_b=b['name'],cat_b=b['kakao_category'],kranks=f"{a['kakao_rank']}/{b['kakao_rank']}",granks=f"{a['google_rank']}/{b['google_rank']}",
            ratinggap=round(gap,3),reviewratio=round(max(ca,cb)/min(ca,cb),3)))
    if feasible:
        with (dest/'baseline_pairs.csv').open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,list(feasible[0]));w.writeheader();w.writerows(feasible)
    print(json.dumps({'cards':len(cards),'candidate_links':len(candidates),'unique_candidate_kakao_ids':len({c['store_id'] for c in candidates}),'baseline_pairs':len(feasible)},ensure_ascii=False))
    print(json.dumps({'notice':'All links and numeric pair candidates require identity, geography, menu, unit, score and basic-fact review; none are selected pairs.'},ensure_ascii=False))

if __name__=='__main__':main()
