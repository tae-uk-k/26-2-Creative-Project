"""Audit outputs and render a reproducible Korean analysis report and chart."""
import hashlib
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
OLD = BASE / '혼합효과분석'
os.environ['MPLCONFIGDIR'] = str(OLD / '.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter

LABEL = {'global_mean': '전체 평균 기준선', 'mixed_logistic': '혼합효과 회귀',
         'logistic_l2': '규제 로지스틱', 'xgboost_shallow': 'XGBoost', 'ebm_main_effects': 'EBM'}


def main():
    d = pd.read_csv(OUT / 'analysis_data_general.csv')
    f = pd.read_csv(OUT / 'restaurant_features_enriched.csv')
    scores = pd.read_csv(OUT / 'model_comparison.csv').set_index('model')
    oof = pd.read_csv(OUT / 'oof_predictions.csv')
    sensitivity = pd.read_csv(OUT / 'sensitivity_model_comparison.csv')
    bootstrap = json.loads((OUT / 'bootstrap_summary.json').read_text(encoding='utf-8'))
    association = json.loads((OUT / 'review_count_association.json').read_text(encoding='utf-8'))
    prep = json.loads((OUT / 'preprocessing_validation.json').read_text(encoding='utf-8'))
    model_audit = json.loads((OUT / 'model_validation.json').read_text(encoding='utf-8'))
    assert prep['passed'] and model_audit['passed'] and bootstrap['all_optimizer_success']
    assert model_audit['all_glmm_optimizer_success']
    assert d.entity_id.nunique() == 30 and len(d) == 600 and len(oof) == 3000
    assert not oof[['repetition', 'run_id', 'entity_id']].duplicated().any()
    for _, g in oof.groupby('repetition'):
        assert len(g) == 600
        check = g[['run_id', 'entity_id', 'y']].merge(d[['run_id', 'entity_id', 'y']], on=['run_id', 'entity_id'], validate='one_to_one', suffixes=('_oof', '_raw'))
        assert check.y_oof.eq(check.y_raw).all()
    folds = pd.read_csv(OLD / 'robust_cv_store_folds.csv')
    check = oof.merge(folds[['repetition', 'entity_id', 'fold']], on=['repetition', 'entity_id'], validate='many_to_one', suffixes=('_actual', '_fixed'))
    assert check.fold_actual.eq(check.fold_fixed).all()
    audit_states = json.loads((OUT / 'fold_preprocessing_states.json').read_text(encoding='utf-8'))
    for state in audit_states:
        held = set(folds.loc[folds.repetition.eq(state['repetition']) & folds.fold.eq(state['fold']), 'entity_id'])
        assert not held & set(state['training_entity_ids'])
        train = d[d.entity_id.isin(state['training_entity_ids'])].drop_duplicates('entity_id')
        for col, spec in state['state']['numeric'].items():
            assert abs(spec['median'] - train[col].median()) < 1e-9
    consumer = BASE.parent.parent / 'data'
    expected = {'consumer_results.csv': '149f1bb971981f3d5f5aec50a5f6ae466d44593c16af790058d1cc0ea9cfbdc3',
                'consumer_failures.csv': 'e2024bbd9096d269a455e38a170091aaefba7c998280c205d86b887411ecd80e'}
    consumer_hashes = {name: hashlib.sha256((consumer / name).read_bytes()).hexdigest() for name in expected}
    assert expected == consumer_hashes
    stores = pd.read_csv(OUT / 'store_feature_outcomes.csv')
    observed = stores.dropna(subset=['diningcode_review_count'])
    corr = observed[['diningcode_review_count', 'diningcode_rating', 'display_photo_count', 'price_krw']].corr(method='spearman')
    corr.to_csv(OUT / 'feature_rank_correlations.csv', encoding='utf-8-sig')
    # Residuals use predictions from held-out restaurants, not training fits.
    residual = oof.groupby('entity_id', as_index=False).agg(actual_rate=('y', 'mean'), predicted_rate=('reviews_mixed_logistic', 'mean'))
    residual = residual.merge(stores, on='entity_id', validate='one_to_one')
    residual['actual_minus_predicted'] = residual.actual_rate - residual.predicted_rate
    residual.sort_values('actual_minus_predicted').to_csv(OUT / 'store_prediction_residuals.csv', index=False, encoding='utf-8-sig')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'font.size': 10, 'axes.unicode_minus': False, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), gridspec_kw={'width_ratios': [1.02, 1]})
    colors = {'myeongdong': '#335f8a', 'seongsu': '#bf7548', 'mangwon': '#4b8772'}
    for area, g in observed.groupby('area'):
        label = {'myeongdong': '명동', 'seongsu': '성수', 'mangwon': '망원'}[area]
        axes[0].scatter(g.diningcode_review_count, g.appearance_rate * 100, label=label, color=colors[area], s=48, alpha=.9)
    axes[0].set_xscale('log')
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    axes[0].set_ylim(-4, 108)
    axes[0].set_xlabel('다이닝코드 평가 수 (로그 눈금)')
    axes[0].set_ylabel('일반 질문 AI 등장률 (%)')
    axes[0].set_title(f'리뷰 수와 등장률의 연관성: ρ={association["spearman_rho"]:.2f}')
    axes[0].legend(frameon=False, loc='upper left')
    for entity, offset in [('MD-R02', (-28, -34)), ('MD-R08', (-5, 24)), ('SS-R01', (-15, -18)), ('SS-R10', (5, 8))]:
        r = stores[stores.entity_id.eq(entity)].iloc[0]
        axes[0].annotate(r.name_ko, (r.diningcode_review_count, r.appearance_rate * 100), xytext=offset, textcoords='offset points', fontsize=8, arrowprops={'arrowstyle': '-', 'color': '#888888', 'lw': .6})
    kinds = ['mixed_logistic', 'logistic_l2', 'xgboost_shallow', 'ebm_main_effects']
    y = np.arange(4)
    for index, prefix in enumerate(['legacy_', 'reviews_', 'full_']):
        values = [scores.loc[prefix + kind, 'brier'] for kind in kinds]
        axes[1].barh(y + (index - 1) * .23, values, height=.22,
                     label=['기존 2개 특징', '기존 + 리뷰 수', '평점·사진·가격·가이드까지'][index],
                     color=['#bdc4cb', '#335f8a', '#91a6b8'][index])
    axes[1].axvline(scores.loc['global_mean', 'brier'], color='#9a5f40', linestyle='--', label='전체 평균 기준선')
    axes[1].set_yticks(y, [LABEL[k] for k in kinds])
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, .4)
    axes[1].set_xlabel('Brier 오차 — 낮을수록 좋음')
    axes[1].set_title('동일 식당 그룹 분할에서 비교', pad=44)
    axes[1].legend(frameon=False, fontsize=8, loc='lower left', bbox_to_anchor=(0, 1.015), ncol=2)
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#eeeeee', zorder=0)
    fig.suptitle('외부 특징 보강 분석 · 한국어 CLI · 2026-10-14', fontsize=15, x=.04, ha='left')
    fig.text(.04, .025, '기존 선정 30개 항목 / 리뷰 관측 28곳 / 일반 응답 60개 · 반복 응답은 독립 식당 표본 수를 늘리지 않음 · 인과 분석 아님', fontsize=9, color='#555555')
    fig.tight_layout(rect=[.025, .075, .995, .91])
    fig.savefig(OUT / '분석_핵심.png', dpi=180, bbox_inches='tight')
    fig.savefig(OUT / '분석_핵심.svg', bbox_inches='tight')
    plt.close(fig)
    table = ['| 모형 | 기존 홈페이지·메뉴 | 리뷰 수 추가 | 평점·사진·가격·단위·미쉐린도 추가 |', '|---|---:|---:|---:|']
    for kind in kinds:
        table.append('| ' + LABEL[kind] + ' | ' + ' | '.join(f'{scores.loc[p + kind, "brier"]:.3f}' for p in ['legacy_', 'reviews_', 'full_']) + ' |')
    sens_table = ['| 검수 범위 | 식당 수 | 전체 평균 | 기존 혼합효과 | 리뷰 추가 혼합효과 | 리뷰 추가 로지스틱 |', '|---|---:|---:|---:|---:|---:|']
    for subset, label in [('complete_profiles_28', '프로필 수집 완료'), ('identity_checked_26', '명칭·지점 문제도 제외')]:
        s = sensitivity[sensitivity.subset.eq(subset)].set_index('model')
        sens_table.append(f'| {label} | {int(s.independent_stores.iloc[0])} | ' + ' | '.join(f'{s.loc[m, "brier"]:.3f}' for m in ['global_mean', 'legacy_mixed_logistic', 'reviews_mixed_logistic', 'reviews_logistic_l2']) + ' |')
    sample_table = ['| 식당 | 일반 질문 등장 | 다이닝코드 평가 수 | 평점 | 수집 출처 |', '|---|---:|---:|---:|---|']
    for entity in ['MD-R02', 'MD-R08', 'SS-R01', 'SS-R10', 'SS-R08', 'MW-R06']:
        r = stores[stores.entity_id.eq(entity)].iloc[0]
        url = f.loc[f.entity_id.eq(entity), 'profile_url'].iloc[0]
        sample_table.append(f'| {r.name_ko} | {int(r.appearances)}/{int(r.opportunities)} | {int(r.diningcode_review_count)} | {r.diningcode_rating:.1f} | [프로필]({url}) |')
    b = bootstrap['or_doubling_percentile95']
    gl = scores.loc['reviews_mixed_logistic']
    note = f'''# 외부 특징 보강 결과 — 2026-10-14

**현재 표본에서는 다이닝코드 리뷰 수가 AI 추천 등장률을 설명하는 유용한 후보 변수다. 리뷰 수를 넣은 혼합효과 회귀·규제 로지스틱이 XGBoost·EBM보다 낮은 예측 오차를 보였다.** 리뷰 증가 자체의 인과 효과를 입증한 결과는 아니다.

## 실제로 수집한 자료

- 기존 선정 30개 식당 항목을 모두 같은 기준으로 조회했다. 정확한 도로명 주소와 프로필 상·하단 집계가 일치하는 **28곳**의 평가 수·평점·표시 사진 수·메뉴 가격을 확보했다. 메뉴 가격 28건은 구조화된 메뉴표 387건과 다시 대조했다.
- 미쉐린 서울·주변 공식 목록 4페이지를 합쳐 **180개, 중복 0**을 확인했다. 원래 표본에서 명동교자·하동관 2곳이 명칭과 일치했다. 이 값은 현재 목록 등재이며 과거 수상 이력이 아니다. [미쉐린 공식 목록](https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurants)
- 공식 개별 관광 소개는 11곳, 문서에 명시된 운영 시작 연도는 5곳에서 보존했다. 관광정보를 못 찾은 19곳과 연도 미확인 25곳을 0으로 바꾸지 않았다. 희소하고 연도 의미도 브랜드/지점마다 달라 주 모델 입력에서 제외했다.
- 구글 리뷰와 최신 리뷰 날짜는 균일하게 실측하지 못해 결측으로 남겼다. 식당 자체 홈페이지의 구글 평가 인용이나 다이닝코드 수치를 구글 실측 값으로 채우지 않았다. 리뷰·별점 출처는 **다이닝코드**다. 표시 사진 수는 프로필의 음식·실내·실외·메뉴정보 합계이며 전체 사진 수가 아니다.
- 가격은 대표 메뉴 단가다. 한 끼·고기 1인분·공유요리·간식을 구분했으며 공유 요리 가격을 임의 인원수로 나누지 않았다. 원래 홈페이지 변수는 과거 목록값을 유지하고 현재 재검증된 값으로 포장하지 않았다.

## 어떤 특징과 패턴이 보였나

리뷰가 관측된 28곳에서 리뷰 수와 일반 질문 등장률의 Spearman 상관은 **{association['spearman_rho']:.2f}**이었다. 지역 안에서만 등장률을 섞은 10,000회 탐색적 순열검정 p={association['area_blocked_permutation_p']:.4f}이었다. 목적 선정한 표본의 내부 연관성으로 해석한다.

{chr(10).join(sample_table)}

하수오곰탕·하우는 별점이 높아도 추천에 등장하지 않았다. 한편 할머니의 레시피·청어람은 리뷰가 비교적 많아도 일반 질문에서는 등장하지 않았다. **리뷰 수가 설명력을 더하지만 모든 식당의 차이를 설명하지는 못한다.** 조건형 질문까지 포함한 전체 240회 등장률과 위 일반 질문 등장률은 다르다.

리뷰 수와 사진 수의 상관은 {corr.loc['diningcode_review_count', 'display_photo_count']:.2f}다. 거의 함께 움직이므로 둘의 회귀계수·SHAP 값을 각각 독립적인 이유로 해석하기 어렵다. 리뷰 수는 기존 인지도·영업 이력·다른 웹 문서량의 대리 지표일 수 있으며, AI가 이 플랫폼의 리뷰 수를 직접 사용했다는 증거는 수집하지 않았다.

## 모델 비교

일반 질문 60개 응답에서 지역에 해당하는 식당×응답 600행을 분석했다. 독립 식당은 30개다. 이전 분석의 고정 식당 분할 5종×5분할을 재사용해 학습 식당과 평가 식당을 분리했다. 식당 이름·과거 노출층·AI 출처 수는 입력에서 제외했다. 결측 대체·표준화는 각 학습 구간의 식당만 사용했다. 모델별 설정을 고정하고 탐색적 튜닝은 하지 않았다.

아래는 Brier 오차로 낮을수록 좋다. 전체 평균 기준선은 **{scores.loc['global_mean', 'brier']:.3f}**다.

{chr(10).join(table)}

리뷰 추가 혼합효과는 기존 같은 모형 대비 **{gl['brier_minus_same_legacy_model']:.3f}**만큼 낮아졌다. 식당별 고정 교차검증 손실을 5,000회 재표집한 차이의 95% 범위는 {gl['delta_legacy_ci_low']:.3f}~{gl['delta_legacy_ci_high']:.3f}다. 전체 평균 기준선 대비 차이 범위는 {gl['delta_global_ci_low']:.3f}~{gl['delta_global_ci_high']:.3f}다. 모델을 재학습한 성능 신뢰구간이 아니라 **현재 표본의 교차검증 손실 재표집 범위**다.

현재는 리뷰 수를 추가한 회귀를 주 분석으로 유지하는 편이 적절하다. 특징을 더 많이 넣거나 XGBoost로 바꿨을 때 추가 이득은 확인하지 못했다. 이는 모든 데이터에서 XGBoost가 부적절하다는 뜻은 아니다. 이번에 평가한 고정 설정·작은 식당 표본에 대한 결과다.

## 명칭·지점 검수와 민감도

- **흥흥호떡(MW-R04)**: 원본 한글명은 훈훈호떡과 다르다. 영어명·주소는 대응하지만 고정 라벨은 소급 변경하지 않았다. 원본 항목의 0/20을 실제 훈훈호떡 미노출로 해석하지 않는다.
- **황인호 크로켓(MW-R03)**: 대표자 이름이 포함된 원당수제고로케로 추정할 자료는 있으나 현재 식당명·지점 연결을 확정하지 못했다. 다른 고로케 가게의 수치를 대입하지 않았다.
- **명동교자(MD-R01)**: 원래 주소 프로필에서 본점 공사·신관 이용 후기가 확인됐다. 현재 물리적 지점의 영업을 확인했다고 보지 않는다.
- **퀴버(SS-R05)**: 검색 목록에는 과거 집계가 보이지만 동일 지점 상세 프로필을 확보하지 못해 최신 숫자를 넣지 않았다.

먼저 미수집 2곳을 제외한 28곳, 이어 명동교자·호떡 명칭 문제도 제외한 26곳에서 같은 분할을 제한해 모델을 **다시 학습**했다. 두 범위에서도 리뷰 추가 회귀가 기존 특징 모형보다 오차가 낮았다. 검수 완료는 온라인 이름·주소 자료 대조이며 실제 당일 영업 확인은 아니다.

{chr(10).join(sens_table)}

리뷰 추가 혼합효과의 식당 재표집 200회에서는 `(리뷰 수+1)`이 두 배가 될 때의 오즈비 중앙값이 {bootstrap['or_doubling_median']:.2f}, 재표집 95% 범위가 {b[0]:.2f}~{b[1]:.2f}였다. 지역별 식당 수를 유지하고 식당의 모든 반복 응답을 함께 재표집했다. 확률 배수나 리뷰를 늘렸을 때의 효과가 아니며, 목적 선정한 현재 표본에서 추정이 얼마나 변하는지 보는 값이다.

## 남은 한계와 다음 실험

1. 식당 선정 자체에 기존 예상 노출층이 사용됐다. 반복 질문 600행을 600개 독립 식당처럼 취급하면 안 된다. 현재 변수·결과를 본 후 선정한 모델이므로 새로운 식당과 다른 날짜에서 재검증해야 한다.
2. 특징은 2026-10-14, 추천 관찰은 2026-10-13이다. 사후 수집한 연관성 탐색이며, 과거 시점에 미리 수집한 전향 특징 자료가 아니다. CLI 결과를 소비자용 ChatGPT·Gemini 결과와 합산하지 않았다.
3. 관광·가이드·운영 이력은 자료 범위가 서로 다르다. 보안 차단 페이지를 정상 식당 소개로 세지 않았고, 검색 미발견을 홈페이지 없음·미등재·폐업으로 바꾸지 않았다. 현재 공식 문서 가격과 방문 후기 가격이 충돌할 수도 있다.
4. 다음은 AI 응답과 독립적인 외부 식당 목록에서 새 표본을 확보해 리뷰·사진·가격·연도를 먼저 고정 수집하고, 새 날짜의 동일 질문으로 검증하는 것이다. 노출 증가의 원인은 비교 식당을 둔 정보 정비 전후 실험으로 따로 검증한다.

## 파일과 재실행

- 수집 원문: `profile_pages_live_2026-10-14.jsonl`, `reference_pages_2026-10-14.jsonl`, `michelin_complete_listing.json`, `search_evidence.txt`
- 정규화·근거: `restaurant_features_enriched.csv`, `profile_snapshot.csv`, `price_validation.csv`, `reference_reviews.csv`, `feature_coverage.csv`, `수집_프로토콜.md`
- 분석·검수: `analysis_data_general.csv`, `analysis_config.json`, `model_comparison.csv`, `oof_predictions.csv`, `mixed_effect_estimates.csv`, `sensitivity_model_comparison.csv`, `review_effect_bootstrap.csv`, `preprocessing_validation.json`, `model_validation.json`, `report_validation.json`
- 모형 환경: 이전 `혼합효과분석/.venv`와 `requirements-models.txt`를 재사용한다. 재실행은 수집 스냅샷을 재사용하며 최신 값을 덮어쓴다고 해석하지 않는다. 초기 학습 시드 점검 결과는 `초기_모델시드_점검/`에 보존했고 최종 비교는 이전 모형과 동일한 머신러닝 시드로 다시 실행했다.

```powershell
$base = 'C:\\Users\\xodnr\\Desktop\\26-2-Creative-Project-main\\03_실험\\ai-visibility-experiment\\cli_한국어_탐색\\확장분석'
$python = Join-Path $base '혼합효과분석\\.venv\\Scripts\\python.exe'
$out = Join-Path $base '외부특징분석'
& $python (Join-Path $out 'collect_profiles.py')
& $python (Join-Path $out 'prepare_features.py')
& $python (Join-Path $out 'run_enriched_analysis.py')
& $python (Join-Path $out 'check_sensitivity.py')
& $python (Join-Path $out 'render_report.py')
```

원래 소비자 결과·실패 CSV 해시는 유지됐고 고정 후보·추천 원문·라벨을 변경하지 않았다. 실제 원문 검증 스크립트의 240회 검수도 별도로 유지한다. 위 결론은 CLI 노출의 탐색적 연관성에 대한 것이다.
'''
    (OUT / '결과_요약.md').write_text(note, encoding='utf-8')
    audit = {'passed': True, 'rows': 600, 'independent_stores': 30, 'profile_features_collected': 28,
             'prices_against_structured_menu': 28, 'oof_unique_keys': True, 'fixed_folds_matched': True,
             'fold_imputation_checked_against_training_stores': True, 'source_labels_unchanged': True,
             'consumer_hashes_unchanged': consumer_hashes, 'glmm_all_converged': True,
             'bootstrap_resamples': bootstrap['resamples'], 'sensitivity_stores': [28, 26],
             'sensitivity_all_optimizer_success': all(x['optimizer_success'] for x in json.loads((OUT / 'sensitivity_diagnostics.json').read_text(encoding='utf-8'))),
             'report_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'causal_claim': False}
    assert audit['sensitivity_all_optimizer_success']
    (OUT / 'report_validation.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
