"""Flatten browser field examples with explicit authorship and missingness.

No exposure labels are attached to these collection examples.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_csv(name, rows, fields):
    with (ROOT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def main():
    data = json.loads((ROOT / 'profile_examples.json').read_text(encoding='utf-8'))
    features, observations = [], []
    for p in data['profiles']:
        description, post = p['description'], p['owner_post']
        owner_description_observed = description['status'] == 'observed' and description['author_type'] == 'owner'
        features.append({
            'profile_id': p['profile_id'], 'map_id': p['map_id'], 'area_id': p['area_id'], 'name': p['name'],
            'snapshot_date_kst': data['collected_date_kst'], 'source_url': p['source_url'],
            'owner_description_status': description['status'],
            'owner_description_chars': description.get('chars_including_spaces') if owner_description_observed else None,
            'owner_description_sections': description.get('bracket_section_count') if owner_description_observed else None,
            'owner_description_numeric_price_mentions': description.get('numeric_won_price_mentions') if owner_description_observed else None,
            'owner_description_phrase_counts': json.dumps(description.get('exact_phrase_counts'), ensure_ascii=False) if owner_description_observed else None,
            'owner_post_status': post['status'], 'owner_post_chars': post.get('chars_including_spaces'),
            'owner_post_language': post.get('language'), 'rating_display': p['rating'],
            'review_count_display': p['review_count_display'], 'review_count_exact': p['review_count_exact'],
            'review_count_missing_reason': 'abbreviated_display_not_exact' if p['review_count_exact'] is None else '',
            'independent_candidate_frame': False, 'cli_exposure_label': None,
            'writing_effect_analysis_eligible': False,
        })
        for field, value, author, status, evidence in [
            ('owner_description', description.get('excerpt'), description['author_type'], description['status'], description.get('author_evidence', description.get('reason', ''))),
            ('owner_post', post.get('excerpt'), post['author_type'], post['status'], post.get('author_evidence', 'not collected')),
            *[(x['field'], x['value'], x['author_type'], 'observed', x['evidence']) for x in p['other_fields']],
        ]:
            observations.append({'profile_id': p['profile_id'], 'field': field,
                                 'value': json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value,
                                 'author_type': author, 'field_status': status,
                                 'source_url': p['source_url'], 'evidence': evidence,
                                 'observed_by': 'research_browser_not_cli'})
    write_csv('profile_features_examples.csv', features, list(features[0]))
    write_csv('profile_field_observations.csv', observations, list(observations[0]))
    # Empty entry tables are templates, never pretend that 60 candidates were collected.
    if not (ROOT / 'candidate_frame.csv').exists():
        write_csv('candidate_frame.csv', [], ['restaurant_id', 'brand_group_id', 'area_id', 'verified_name', 'verified_address',
                                             'selected_at_kst', 'selection_query', 'selection_map', 'selection_rank',
                                             'is_sponsored', 'sort_mode', 'map_center', 'source_url', 'identity_status'])
    if not (ROOT / 'main_profile_collection.csv').exists():
        write_csv('main_profile_collection.csv', [], ['restaurant_id', 'map_id', 'snapshot_at_kst', 'source_url',
                                                     'field', 'author_type', 'field_status', 'raw_text_path',
                                                     'raw_text_sha256', 'evidence_excerpt', 'collection_method'])
    assert len(features) == 3
    assert features[0]['review_count_exact'] is None
    assert features[1]['owner_description_chars'] is None
    assert features[2]['owner_description_chars'] is None and features[2]['owner_post_chars'] == 1221
    assert all(x['cli_exposure_label'] is None and not x['writing_effect_analysis_eligible'] for x in features)
    print(json.dumps({'profiles': len(features), 'field_observations': len(observations),
                      'eligible_effect_rows': 0, 'candidate_frame_rows': sum(1 for _ in csv.DictReader((ROOT / 'candidate_frame.csv').open(encoding='utf-8-sig'))),
                      'missingness_and_attribution_checks': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
