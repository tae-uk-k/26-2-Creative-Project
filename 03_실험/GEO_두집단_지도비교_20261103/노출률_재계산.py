"""Compute audited exposure rates; zero valid responses => null, never zero.

Input attempt status must already be manually audited as 'valid'. This program
does not infer successful source access from a model's claim or a URL. Failed
calls and identity-ambiguous mentions stay outside confirmed appearances.
"""
import argparse
import csv
import json
import statistics
from pathlib import Path


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def calculate(directory):
    pairs = read_rows(directory/'확정_매장쌍.csv')
    attempts = read_rows(directory/'실제_추천_시도_기록.csv')
    mentions = read_rows(directory/'추천_매장_순서_출처_추출표.csv')
    schedule = {r['cell_id']: r for r in read_rows(directory/'전체_실행목록_90셀.csv')}
    valid = {}
    for attempt in attempts:
        if attempt['status'] == 'valid':
            if attempt['cell_id'] not in schedule:
                raise ValueError('Unregistered cell')
            valid.setdefault(attempt['cell_id'], attempt['attempt_id'])
    member = {}
    for p in pairs:
        for group in ['A', 'B']:
            cid = p[group+'_candidate_id']
            if cid in member:
                raise ValueError('Store reused in more than one pair')
            member[cid] = {'group': group, 'area_id': p['area_id'], 'pair_id': p['pair_id']}
    ranks = {}
    ambiguous = []
    for mention in mentions:
        cid = mention.get('candidate_id', '')
        if mention.get('identity_status') != 'confirmed':
            ambiguous.append(mention)
            continue
        if cid not in member or valid.get(mention['cell_id']) != mention['attempt_id']:
            continue
        if schedule[mention['cell_id']]['area_id'] != member[cid]['area_id']:
            raise ValueError('Cross-region appearance included')
        key = cid, mention['cell_id']
        rank = int(mention['rank'])
        ranks[key] = min(ranks.get(key, rank), rank)
    stores = []
    for cid, meta in member.items():
        for question in ['Q1', 'Q2', 'Q3', 'ALL']:
            cells = [cell for cell in valid if schedule[cell]['area_id'] == meta['area_id']
                     and (question == 'ALL' or schedule[cell]['question_id'] == question)]
            present = [ranks[cid, cell] for cell in cells if (cid, cell) in ranks]
            stores.append(dict(candidate_id=cid, **meta, question_id=question,
                valid_denominator=len(cells), appearance_count=len(present),
                exposure_pct=100*len(present)/len(cells) if cells else None,
                mean_rank_when_present=statistics.mean(present) if present else None))
    groups = []
    for area in ['MD', 'SS', 'MW', 'ALL']:
        for question in ['Q1', 'Q2', 'Q3', 'ALL']:
            for group in ['A', 'B']:
                rows = [r for r in stores if r['group'] == group and r['question_id'] == question
                        and (area == 'ALL' or r['area_id'] == area)]
                values = [r['exposure_pct'] for r in rows]
                groups.append(dict(area_id=area, question_id=question, group=group, store_count=len(rows),
                    exposure_pct=statistics.mean(values) if values and all(v is not None for v in values) else None))
    lookup = {(r['candidate_id'],r['question_id']):r for r in stores}
    contrasts = []
    for p in pairs:
        for q in ['Q1','Q2','Q3','ALL']:
            a, b = lookup[p['A_candidate_id'],q], lookup[p['B_candidate_id'],q]
            if a['valid_denominator'] != b['valid_denominator']:
                raise ValueError('Unequal A/B valid response set')
            av, bv = a['exposure_pct'], b['exposure_pct']
            contrasts.append(dict(pair_id=p['pair_id'], question_id=q,
                B_minus_A_pp=bv-av if av is not None and bv is not None else None))
    return dict(confirmed_pair_count=len(pairs), actual_attempt_count=len(attempts),
        valid_cell_count=len(valid), duplicate_valid_attempts_excluded=sum(a['status']=='valid' for a in attempts)-len(valid),
        ambiguous_mentions=len(ambiguous), stores=stores, groups=groups, pair_contrasts=contrasts,
        uncertainty_interval=None, uncertainty_note='미산출. 반복 응답을 독립 매장 표본으로 취급하지 않음.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = calculate(args.directory)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ['stores','groups','pair_contrasts']}, ensure_ascii=False))
