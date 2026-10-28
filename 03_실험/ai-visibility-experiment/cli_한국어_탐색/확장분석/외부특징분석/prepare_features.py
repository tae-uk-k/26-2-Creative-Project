"""Join audited public snapshots without editing the frozen experiment labels."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
OLD = BASE / '혼합효과분석'


def norm(value):
    return ''.join(c for c in str(value) if c.isalnum()).lower()


def main():
    profiles = pd.read_csv(OUT / 'profile_snapshot.csv')
    prices = pd.read_csv(OUT / 'representative_menu_selection.csv')
    menus = pd.read_csv(OUT / 'menu_prices_raw.csv')
    refs = pd.read_csv(OUT / 'reference_reviews.csv')
    guides = json.loads((OUT / 'michelin_complete_listing.json').read_text(encoding='utf-8'))
    assert [len(g['names']) for g in guides] == [48, 48, 48, 36]
    guide_names = [n for g in guides for n in g['names']]
    assert len(guide_names) == len(set(guide_names)) == 180
    guide_set = {norm(n) for n in guide_names}
    trials = pd.read_csv(OLD / 'data_primary_general.csv')
    original = trials[['entity_id', 'name_ko', 'area', 'brand_group', 'own_website', 'menu_family_external']].drop_duplicates()
    assert len(original) == 30 and trials.shape[0] == 600
    features = original.merge(profiles.drop(columns=['name_ko', 'area']), on='entity_id', validate='one_to_one')
    features = features.merge(prices, on='entity_id', validate='one_to_one')
    features = features.merge(refs, on='entity_id', validate='one_to_one')
    price_audit = []
    for row in features.itertuples(index=False):
        matched = menus.loc[menus.entity_id.eq(row.entity_id) & menus.menu_name.map(norm).eq(norm(row.menu_name)) & menus.price_krw.eq(row.price_krw)]
        collected = pd.notna(row.price_krw)
        assert not collected or len(matched) == 1, (row.entity_id, row.menu_name, row.price_krw)
        price_audit.append({'entity_id': row.entity_id, 'collected': collected, 'structured_menu_match': len(matched),
                            'source_url': matched.iloc[0].source_url if len(matched) else ''})
    features['michelin_listing_current'] = features.name_ko.map(lambda n: int(norm(n) in guide_set))
    assert set(features.loc[features.michelin_listing_current.eq(1), 'entity_id']) == {'MD-R01', 'MD-R02'}
    features['feature_snapshot_date'] = '2026-10-14'
    features['website_value_provenance'] = 'legacy_registry_website_indicator_not_uniformly_reverified'
    features['identity_sensitivity_exclude'] = features.entity_id.isin(['MD-R01', 'MW-R03', 'MW-R04']).astype(int)
    for src, dst in [('diningcode_review_count', 'log_review_count'), ('display_photo_count', 'log_photo_count'), ('price_krw', 'log_price_krw')]:
        features[dst] = np.log1p(features[src])
    for c in ['diningcode_review_count', 'diningcode_rating', 'display_photo_count', 'price_krw']:
        features[c + '_missing'] = features[c].isna().astype(int)
    observed = features.diningcode_review_count.notna()
    assert features.loc[observed, 'road_match'].eq(1).all()
    assert features.loc[observed, 'review_aggregate_crosscheck'].eq(1).all()
    assert features.loc[observed, 'diningcode_rating'].between(1, 5).all()
    assert features.loc[observed, 'diningcode_review_count'].ge(0).all()
    added = ['log_review_count', 'diningcode_rating', 'log_photo_count', 'log_price_krw', 'unit', 'michelin_listing_current',
             'identity_sensitivity_exclude', 'diningcode_review_count', 'display_photo_count', 'price_krw']
    merged = trials.merge(features[['entity_id'] + added], on='entity_id', validate='many_to_one')
    assert len(merged) == 600 and merged[['run_id', 'entity_id']].duplicated().sum() == 0
    assert np.array_equal(merged.y, trials.y)
    features.to_csv(OUT / 'restaurant_features_enriched.csv', index=False, encoding='utf-8-sig')
    merged.to_csv(OUT / 'analysis_data_general.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(price_audit).to_csv(OUT / 'price_validation.csv', index=False, encoding='utf-8-sig')
    coverage = []
    for col in ['own_website', 'menu_family_external', 'diningcode_review_count', 'diningcode_rating', 'display_photo_count',
                'price_krw', 'michelin_listing_current', 'tourism_individual_page_verified', 'reported_established_year',
                'google_review_count', 'recent_review_age_days']:
        coverage.append({'feature': col, 'collected_stores': int(features[col].notna().sum()), 'total_stores': 30,
                         'missing_stores': int(features[col].isna().sum()), 'unique_observed_values': int(features[col].nunique())})
    pd.DataFrame(coverage).to_csv(OUT / 'feature_coverage.csv', index=False, encoding='utf-8-sig')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        OUT / 'profile_pages_live_2026-10-14.jsonl', OUT / 'profile_selection.csv', OUT / 'representative_menu_selection.csv',
        OUT / 'michelin_complete_listing.json', OUT / 'reference_reviews.csv', OLD / 'data_primary_general.csv',
        OLD / 'robust_cv_store_folds.csv']}
    summary = {'passed': True, 'original_stores': 30, 'rows': 600, 'profiles_with_matching_road_and_aggregate': int(observed.sum()),
               'prices_verified_against_menu': sum(p['collected'] for p in price_audit), 'michelin_listing_count': 180,
               'guide_positive_stores': 2, 'response_labels_changed': False, 'missing_profiles': features.loc[~observed, 'entity_id'].tolist(),
               'tourism_nonfinding_is_not_zero': True, 'google_counts_imputed_from_other_platforms': False,
               'feature_snapshot_after_outcomes': True, 'input_sha256': hashes}
    (OUT / 'preprocessing_validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
