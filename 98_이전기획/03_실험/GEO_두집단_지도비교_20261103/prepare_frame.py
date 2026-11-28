"""Parse native UI search cards, retain displayed ranks, and list possible identity matches."""
import csv
import hashlib
import itertools
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parent
def namekey(x):return re.sub(r'[^a-z0-9가-힣]','',unicodedata.normalize('NFC',x).lower())
def csvout(name,rows,fields=None):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields or list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    captures=[json.loads(l) for l in (ROOT/'browser_observed.jsonl').read_text(encoding='utf-8').splitlines()]
    captures=[x for x in captures if x.get('phase')=='formal']
    latest={}
    for x in captures:latest[(x['platform'],x['area'],str(x['page']))]=x
    rows=[]
    for (platform,area,page),x in latest.items():
        natural=0;seen=set()
        for r in x['rows']:
            txt=r.get('text','') or '';lines=txt.splitlines();url=r.get('url','') or ''
            sponsored='\n스폰서\n' in txt
            if not sponsored:natural+=1
            if platform=='google':
                if natural>60 and not sponsored:continue
                name=r.get('name','') or '';m=re.search(r'!19s([^!/?]+)',url)
                place_id=unquote(m[1]) if m else ''
                rating=re.search(r'(?m)^([0-5]\.\d)\(([\d,]+)\)',txt)
                address=next((l.split(' · ')[-1] for l in lines if ' · ' in l),'')
                category=next((l.split(' · ')[0] for l in lines if ' · ' in l),'')
                rank=natural if not sponsored else ''
            else:
                name=lines[0] if lines else '';place_id=url.rsplit('/',1)[-1]
                rating=re.search(r'별점\n([0-5]\.\d)\n([\d,]+)건',txt)
                address=next((l for l in lines if l.startswith('서울 ')),'')
                card=next((l for l in lines if re.match(r'^[A-O] ',l)),'')
                category=card.removeprefix(card[:2]).removeprefix(name).strip()
                rank=(int(page)-1)*15+r['rank']
            rows.append({'platform':platform,'area_id':area,'query':x['query'],'rank':rank,
                         'display_position':r.get('display_position',r.get('rank')),'page':page,'sponsored':sponsored,
                         'name':name,'place_id':place_id,'url':url,'address_search_card':address,'category_search_card':category,
                         'rating':rating[1] if rating else '', 'review_count':rating[2].replace(',','') if rating else '',
                         'observed_at_utc':x['observed_at'],'evidence_scope':'native_search_card_not_detail','raw_search_card':txt})
    csvout('search_cards.csv',rows)
    k=[r for r in rows if r['platform']=='kakao' and not r['sponsored']]
    g=[r for r in rows if r['platform']=='google' and not r['sponsored']]
    possible=[]
    for kr in k:
        for gr in g:
            if kr['area_id']!=gr['area_id']:continue
            kn,gn=namekey(kr['name']),namekey(gr['name'])
            if not kn or not gn:continue
            if kn==gn or (len(kn)>=3 and kn in gn) or (len(gn)>=3 and gn in kn):
                possible.append({'candidate_id':kr['area_id']+'-'+kr['place_id'],'area_id':kr['area_id'],
                 'kakao_name':kr['name'],'kakao_id':kr['place_id'],'kakao_rank':kr['rank'],'kakao_url':kr['url'],
                 'kakao_address_card':kr['address_search_card'],'kakao_category_card':kr['category_search_card'],
                 'google_name':gr['name'],'google_id':gr['place_id'],'google_rank':gr['rank'],'google_url':gr['url'],
                 'google_address_card':gr['address_search_card'],'google_category_card':gr['category_search_card'],
                 'google_rating':gr['rating'],'google_review_count':gr['review_count'],
                 'identity_status':'possible_name_match_requires_detail_address_check'})
    csvout('possible_crossmap_matches.csv',possible)
    preliminary_pairs=[]
    for a,b in itertools.combinations(possible,2):
        if a['area_id']!=b['area_id'] or a['candidate_id']==b['candidate_id']:continue
        ar,br=int(a['kakao_rank']),int(b['kakao_rank']);ag,bg=int(a['google_rank']),int(b['google_rank'])
        rank_ok=abs(ar-br)<=15 and (ar-1)//20==(br-1)//20 and abs(ag-bg)<=15 and (ag-1)//20==(bg-1)//20
        try:
            ratingdiff=abs(float(a['google_rating'])-float(b['google_rating']))
            reviewratio=max(int(a['google_review_count']),int(b['google_review_count']))/min(int(a['google_review_count']),int(b['google_review_count']))
        except (ValueError,ZeroDivisionError):continue
        if rank_ok and ratingdiff<=.40000001 and reviewratio<=3:
            preliminary_pairs.append({'area_id':a['area_id'],'candidate_1':a['candidate_id'],'name_1':a['kakao_name'],
               'category_1':a['kakao_category_card'],'candidate_2':b['candidate_id'],'name_2':b['kakao_name'],'category_2':b['kakao_category_card'],
               'kakao_ranks':f'{ar}|{br}','google_ranks':f'{ag}|{bg}','google_rating_gap':ratingdiff,'review_ratio':reviewratio,
               'not_yet_checked':'identity, cuisine, menu, unit, price, information, GEO score'})
    csvout('baseline_feasible_pairs_before_detail.csv',preliminary_pairs,['area_id','candidate_1','name_1','category_1','candidate_2','name_2','category_2','kakao_ranks','google_ranks','google_rating_gap','review_ratio','not_yet_checked'])
    print(json.dumps({'cards':len(rows),'possible_name_matches':len(possible),'rank_rating_review_feasible_pairs':len(preliminary_pairs)},ensure_ascii=False))
    for x in preliminary_pairs:print(json.dumps(x,ensure_ascii=False))

if __name__=='__main__':main()
