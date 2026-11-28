"""Intent-specific reanalysis of the immutable 240-run study (no new causal labels)."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'ai-visibility-experiment'/'cli_한국어_탐색'/'확장분석'
INTENTS={'MD01':'general','MD02':'budget_25000_local_korean','MD03':'solo_weekday_evening','MD04':'traditional_korean',
         'SS01':'general','SS02':'budget_25000_korean_lunch','SS03':'local_character_dinner','SS04':'solo_and_information',
         'MW01':'general_including_market_food','MW02':'budget_15000_local_food','MW03':'market_snacks','MW04':'seated_full_meal'}

def read(name):
    return list(csv.DictReader((OLD/name).open(encoding='utf-8-sig',newline='')))

def write(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    runs=read('runs_clean.csv');recs=read('recommendations_clean.csv')
    assert len(runs)==240 and len({r['run_id'] for r in runs})==240 and len(recs)==1200
    registry={r['entity_id']:r for r in read('restaurant_registry.csv')}
    denom=Counter((r['prompt_id'],r['backend']) for r in runs)
    seen=set();counts=Counter();ranks=defaultdict(list);domains=Counter();claims=[]
    for r in recs:
        entity=r['entity_id'] or 'UNRESOLVED-'+hashlib.sha256((r['name_raw']+'|'+r['address_raw']).encode('utf-8')).hexdigest()[:12]
        key=(r['run_id'],entity)
        assert key not in seen;seen.add(key)
        counts[(r['entity_id'],r['prompt_id'],r['backend'])]+=1
        ranks[(r['entity_id'],r['prompt_id'],r['backend'])].append(int(r['rank']))
        for url in set(r['sources_raw_model_do_not_train'].split('|')):
            domains[(r['prompt_id'],r['backend'],urlsplit(url).hostname or 'invalid')]+=1
        # Literal tags describe generated explanations only, not the actual restaurant.
        text=r['reason_raw_model_do_not_train']
        groups={'solo_seating':['혼자','혼밥','바 좌석','1인석','1인 주문'],
                'budget_value':['가성비','저렴','합리적','부담 없는','가볍게'],
                'authority_award':['미쉐린','미슐랭','빕 구르망','블루리본'],
                'heritage':['노포','전통','오래된','오랜'],
                'fame_social':['인기','유명','SNS','웨이팅','줄 서'],
                'local_tourism':['현지','로컬','관광','지역'],
                'menu_specificity':['전문','대표','시그니처'],
                'information_recency':['확인','최근','2026','영업시간']}
        for tag,words in groups.items():
            matches=[w for w in words if w in text]
            if matches:
                claims.append({'run_id':r['run_id'],'backend':r['backend'],'prompt_id':r['prompt_id'],
                    'entity_id':r['entity_id'],'tag':tag,'literal_matches':'|'.join(matches),
                    'label_role':'model_reason_only_not_independent_feature','reason':text})
    rows=[]
    for entity,p in registry.items():
        ids=[q for q in INTENTS if q[:2] in {'MD':'MD','SS':'SS','MW':'MW'} and
             {'MD':'myeongdong','SS':'seongsu','MW':'mangwon'}[q[:2]]==p['area']]
        for prompt in ids:
            for backend in ['codex','agy','combined']:
                bs=['codex','agy'] if backend=='combined' else [backend]
                n=sum(denom[(prompt,b)] for b in bs)
                k=sum(counts[(entity,prompt,b)] for b in bs)
                base=prompt[:2]+'01'
                bn=sum(denom[(base,b)] for b in bs);bk=sum(counts[(entity,base,b)] for b in bs)
                rr=sum((ranks[(entity,prompt,b)] for b in bs),[])
                rows.append({'entity_id':entity,'name':p['name_ko'],'area':p['area'],'prompt_id':prompt,
                             'intent':INTENTS[prompt],'backend':backend,'appearances':k,'successful_runs':n,
                             'appearance_rate':k/n,'general_appearances':bk,'general_runs':bn,
                             'delta_vs_general_pp':100*(k/n-bk/bn),'mean_rank_when_mentioned':sum(rr)/len(rr) if rr else '',
                             'cohort':p['sampling_cohort'],'identity_status':p['identity_status'],
                             'inclusion_conditioning':'discovered candidates were selected after first 120 outcomes; descriptive only'})
    write('legacy_intent_rates.csv',rows)
    features={r['entity_id']:r for r in read('restaurant_features.csv')}
    categories=defaultdict(list)
    for r in rows:
        f=features.get(r['entity_id'],{})
        if r['cohort']=='original30_preselected' and f.get('menu_family_external'):
            categories[(r['area'],r['prompt_id'],r['backend'],f['menu_family_external'])].append(r)
    write('legacy_category_intent_associations.csv',[
        {'area':a,'prompt_id':p,'intent':INTENTS[p],'backend':b,'menu_family_external':family,
         'independent_stores':len(v),'sum_appearances':sum(r['appearances'] for r in v),
         'store_run_opportunities':sum(r['successful_runs'] for r in v),
         'mean_store_appearance_rate':sum(r['appearance_rate'] for r in v)/len(v),
         'mean_within_store_delta_vs_general_pp':sum(r['delta_vs_general_pp'] for r in v)/len(v),
         'feature_role':'prior external category; legacy identities not all currently verified',
         'inference':'descriptive original30 cohort only; small category groups, no causal effect'}
        for (a,p,b,family),v in categories.items()])
    write('legacy_cited_domains.csv',[{'prompt_id':p,'intent':INTENTS[p],'backend':b,'domain':d,'citation_occurrences':n}
          for (p,b,d),n in sorted(domains.items(),key=lambda v:-v[1])])
    write('legacy_reason_claim_tags.csv',claims)
    tagrows=[]
    for p in INTENTS:
        for backend in ['codex','agy']:
            group=[r for r in recs if r['prompt_id']==p and r['backend']==backend]
            for tag in ['solo_seating','budget_value','authority_award','heritage','fame_social','local_tourism','menu_specificity','information_recency']:
                n=sum(c['tag']==tag and c['prompt_id']==p and c['backend']==backend for c in claims)
                tagrows.append({'prompt_id':p,'intent':INTENTS[p],'backend':backend,'claim_tag':tag,
                                'recommendations_with_tag':n,'recommendations':len(group),'rate':n/len(group)})
    write('legacy_reason_tag_summary.csv',tagrows)
    summary={'runs':len(runs),'recommendations':len(recs),'prompt_success_counts':{f'{p}-{b}':n for (p,b),n in denom.items()},
             'counts_by_intent_top':{p:[{k:r[k] for k in ['name','appearances','successful_runs','general_appearances','delta_vs_general_pp']}
                                      for r in sorted([r for r in rows if r['prompt_id']==p and r['backend']=='combined'],key=lambda r:-r['appearances'])[:6]] for p in INTENTS},
             'inputs_sha256':{str(OLD/n):hashlib.sha256((OLD/n).read_bytes()).hexdigest() for n in ['runs_clean.csv','recommendations_clean.csv','restaurant_registry.csv']}}
    (ROOT/'legacy_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary['counts_by_intent_top'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
