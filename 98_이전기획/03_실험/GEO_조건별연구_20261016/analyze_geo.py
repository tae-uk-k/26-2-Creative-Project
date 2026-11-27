"""Descriptive GEO outcomes; preserves uncertainty and does not infer causes from reasons."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT=Path(__file__).resolve().parent

def write(name,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)

def norm_name(text):
    return re.sub(r'[^0-9a-z가-힣]','',str(text or '').lower())

def norm_url(url):
    try:
        p=urlsplit(url);return urlunsplit(('https',p.netloc.lower().removeprefix('www.'),p.path.rstrip('/'),p.query,''))
    except ValueError:return ''

def domain(url):
    try:return (urlsplit(url).hostname or '').lower().removeprefix('www.')
    except ValueError:return ''

def source_type(url):
    d=domain(url)
    if d in {'m.place.naver.com','pcmap.place.naver.com','map.naver.com','naver.me','place.map.kakao.com','map.kakao.com','kko.to','maps.app.goo.gl','maps.google.com'} or ('google.' in d and '/maps' in url):return 'map'
    if d.endswith(('visitseoul.net','visitkorea.or.kr','seoul.go.kr','mapo.go.kr','sd.go.kr')):return 'public_tourism_or_government'
    if d in {'guide.michelin.com','happycow.net','logs.happycow.net'}:return 'specialist_guide'
    if d.endswith(('diningcode.com','tabling.co.kr','catchtable.co.kr','siksinhot.com','tripinfo.co.kr','autoreserve.com','tripadvisor.com','restaurantguru.com','polle.com','revitguide.com')):return 'aggregator_or_booking'
    if d.endswith(('instagram.com','youtube.com','facebook.com','tiktok.com','threads.net')):return 'social'
    if d.endswith(('tistory.com','blog.naver.com','brunch.co.kr')):return 'blog'
    return 'other_requires_review'

def events(path):
    result=[]
    for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
        try: result.append(json.loads(line))
        except ValueError:pass
    return result

def main():
    journal=ROOT/'attempts.jsonl'
    records=[json.loads(l) for l in journal.read_text(encoding='utf-8').splitlines()]
    latest={}
    for r in records:
        old=latest.get(r['run_id'])
        # A failed retry never replaces a usable successful response.
        if old is None or (old['status']!='completed' and r['attempt']>=old['attempt']) or r['status']=='completed':latest[r['run_id']]=r
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    runs=[];recs=[];sources=[];queries=[];trace=[];flags=[]
    for m in manifest:
        r=latest.get(m['run_id'])
        if r is None:
            runs.append({**m,'status':'not_attempted','recommendations':'','searched':'','elapsed_seconds':''});continue
        ev=events(r['raw_path']);observed_urls=set();run_queries=[];open_actions=0;external_actions=[]
        for idx,e in enumerate(ev):
            item=e.get('item',{})
            step=e.get('step_update',{})
            if e.get('type')=='item.completed' and item.get('type')=='web_search':
                action=item.get('action') or {}
                if action.get('type')=='search':
                    qs=action.get('queries') or ([action['query']] if action.get('query') else [])
                    run_queries.extend(qs)
                elif action.get('type') in ['open','click']:open_actions+=1
                for result in item.get('results',[]):
                    if result.get('url'):observed_urls.add(norm_url(result['url']))
                trace.append({'run_id':r['run_id'],'event_index':idx,'kind':'codex_web_search',
                              'action_json':json.dumps(action,ensure_ascii=False),'results_count':len(item.get('results',[]))})
            if e.get('type')=='item.completed' and item.get('type') in ['command_execution','mcp_tool_call']:
                external_actions.append(item.get('type'))
            if e.get('event')=='step_update' and step.get('step_type')=='tool':
                tool=step.get('tool_name','');params=step.get('tool_info',{}).get('parameters',{})
                if tool=='search_web' and step.get('state')=='ACTIVE':
                    q=params.get('query')
                    if q:run_queries.append(q)
                if tool in ['read_url','read_url_content'] and step.get('state')=='ACTIVE':open_actions+=1
                if tool not in ['search_web','read_url','read_url_content'] and step.get('state')=='ACTIVE':external_actions.append(tool)
                trace.append({'run_id':r['run_id'],'event_index':idx,'kind':'agy_'+tool,
                              'action_json':json.dumps(params,ensure_ascii=False),'results_count':''})
        n=len(r['parsed_answer']['restaurants']) if r['status']=='completed' else ''
        runs.append({**m,'status':r['status'],'recommendations':n,'searched':r['web_search_observed'],
                     'elapsed_seconds':r['elapsed_seconds'],'observed_query_count':len(run_queries),'observed_open_actions':open_actions,
                     'query_budget_exceeded':len(run_queries)>3,'unrequested_tool_calls':'|'.join(external_actions),
                     'access_note':(r.get('parsed_answer') or {}).get('access_note',''),'raw_path':r['raw_path']})
        for j,q in enumerate(run_queries,1):queries.append({**m,'query_order':j,'query':q,'query_source':'tool_trace'})
        if r['status']!='completed':continue
        seen=set()
        for rec in r['parsed_answer']['restaurants']:
            key=norm_name(rec.get('name'))
            if not key:
                flags.append({'run_id':r['run_id'],'flag':'missing_name','detail':str(rec)});continue
            if key in seen:
                flags.append({'run_id':r['run_id'],'flag':'duplicate_name_within_answer','detail':rec['name']});continue
            seen.add(key)
            if len(seen)>5:flags.append({'run_id':r['run_id'],'flag':'over_five_recommendations','detail':rec['name']})
            provided_sources=rec.get('sources') or []
            urls=[s if isinstance(s,str) else s.get('url','') for s in provided_sources]
            root_only=[u for u in urls if urlsplit(u).path in ['','/']]
            row={**m,'name_key':key,'name':rec['name'],'branch':rec.get('branch'),'address':rec.get('address'),
                 'identity_status':'name_level_not_verified_branch','rank':rec.get('rank'),'cuisine_claim':rec.get('cuisine'),
                 'reason_claim':rec.get('reason'),'condition_status_raw':rec.get('condition_status'),
                 'condition_status':'not_applicable' if m['intent']=='general' else rec.get('condition_status'),
                 'condition_evidence_claim':rec.get('condition_evidence'),'evidence_level_claim':rec.get('evidence_level'),
                 'first_query_contains_selected_name':bool(run_queries and key in norm_name(run_queries[0])),
                 'source_count':len(urls),'domain_only_sources':len(root_only),'source_urls':'|'.join(urls),
                 'source_content_independently_verified':False}
            recs.append(row)
            for s,u in zip(provided_sources,urls):
                sources.append({**m,'name_key':key,'name':rec['name'],'url':u,'domain':domain(u),'source_type_by_domain':source_type(u),
                                'source_type_model_claim':s.get('source_type','') if isinstance(s,dict) else '',
                                'domain_only_url':u in root_only,'url_observed_in_tool_result':norm_url(u) in observed_urls,
                                'tool_returned_url_absence_is_not_no_access_proof':True,'content_support_status':'not_independently_audited'})
    write('runs_audited.csv',runs)
    write('recommendations.csv',recs)
    write('cited_sources.csv',sources)
    write('retrieval_queries.csv',queries)
    write('tool_trace.csv',trace)
    write('audit_flags.csv',flags,['run_id','flag','detail'])
    good=[r for r in runs if r['status']=='completed']
    summaries=[]
    for intent in dict.fromkeys(r['intent'] for r in manifest):
        for b in ['codex','agy','combined']:
            rr=[r for r in runs if r['intent']==intent and (b=='combined' or r['backend']==b)]
            success=[r for r in rr if r['status']=='completed']
            cc=[r for r in recs if r['intent']==intent and (b=='combined' or r['backend']==b)]
            summaries.append({'intent':intent,'backend':b,'planned':len(rr),'completed':len(success),
                              'technical_or_permission_failure':sum(r['status'] not in ['completed','not_attempted'] for r in rr),
                              'not_attempted':sum(r['status']=='not_attempted' for r in rr),
                              'zero_recommendation_answers':sum(r['recommendations']==0 for r in success),
                              'recommendations':len(cc),'mean_recommendations_per_completed':len(cc)/len(success) if success else '',
                              'self_report_confirmed':sum(r['condition_status']=='confirmed' for r in cc),
                              'self_report_partial':sum(r['condition_status']=='partial' for r in cc),
                              'self_report_unknown':sum(r['condition_status']=='unknown' for r in cc),
                              'domain_only_source_recommendations':sum(r['domain_only_sources']>0 for r in cc)})
    write('intent_summary.csv',summaries)
    rates=[]
    for area in ['MD','SS','MW']:
        names={r['name_key']:r['name'] for r in recs if r['area_id']==area}
        for key,name in names.items():
            for intent in dict.fromkeys(r['intent'] for r in manifest):
                for b in ['codex','agy','combined']:
                    sr=[r for r in good if r['area_id']==area and r['intent']==intent and (b=='combined' or r['backend']==b)]
                    br=[r for r in good if r['area_id']==area and r['intent']=='general' and (b=='combined' or r['backend']==b)]
                    cc=[r for r in recs if r['area_id']==area and r['name_key']==key and r['intent']==intent and (b=='combined' or r['backend']==b)]
                    bc=[r for r in recs if r['area_id']==area and r['name_key']==key and r['intent']=='general' and (b=='combined' or r['backend']==b)]
                    rates.append({'area_id':area,'name_key':key,'name':name,'intent':intent,'backend':b,
                                  'appearances':len(cc),'successful_runs':len(sr),'appearance_rate':len(cc)/len(sr) if sr else '',
                                  'general_appearances':len(bc),'general_successful_runs':len(br),
                                  'delta_vs_general_pp':100*(len(cc)/len(sr)-len(bc)/len(br)) if sr and br else '',
                                  'identity_status':'name_level_not_verified_branch','discovery':'outcome_selected_descriptive_only'})
    write('store_intent_rates.csv',rates)
    cited=Counter((r['intent'],r['backend'],r['source_type_by_domain']) for r in sources)
    write('source_type_summary.csv',[{'intent':i,'backend':b,'source_type_by_domain':t,'citation_occurrences':n} for (i,b,t),n in cited.items()])
    payload={'planned':len(manifest),'attempts':len(records),'status_counts':dict(Counter(r['status'] for r in runs)),
             'recommendations':len(recs),'queries':len(queries),'sources':len(sources),
             'domain_only_citations':sum(s['domain_only_url'] for s in sources),
             'query_budget_violations':sum(r.get('query_budget_exceeded',False) for r in runs),
             'identity':'name level only; branch not verified','all_condition_and_source_labels':'self-report unless separately audited',
             'journal_sha256':hashlib.sha256(journal.read_bytes()).hexdigest()}
    (ROOT/'summary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False))

if __name__=='__main__':main()
