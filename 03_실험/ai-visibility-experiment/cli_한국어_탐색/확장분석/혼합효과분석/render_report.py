"""Audit evaluated artifacts and render a Korean pilot report and scientific figure."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import os
from pathlib import Path
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mpl-cache"))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, average_precision_score
from run_analysis import OUT,BASE,MODEL_COLUMNS,save_json

NAMES={'global_mean':'전체 평균','context_mean':'질문·모델별 평균','logistic_l2':'규제 로지스틱',
       'mixed_logistic':'혼합효과 회귀','ebm_main_effects':'EBM','xgboost_shallow':'XGBoost'}
MENU={'noodles_dumplings':'국수·만두','soups_stews':'국·탕·전골','barbecue':'구이',
      'set_meals':'한식 식사','western_dining':'서양식 식사','market_snacks':'시장 음식','other_meals':'기타 식사','jokbal':'족발'}


def main():
    primary=pd.read_csv(OUT/'data_primary_general.csv')
    comparison=pd.read_csv(OUT/'robust_model_comparison.csv')
    effects=pd.read_csv(OUT/'effect_estimates.csv')
    oof=pd.read_csv(OUT/'robust_oof_predictions.csv')
    folds=pd.read_csv(OUT/'robust_cv_store_folds.csv')
    summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    bootstrap=json.loads((OUT/'bootstrap_website_summary.json').read_text(encoding='utf-8'))
    cvcheck=json.loads((OUT/'robust_cv_validation.json').read_text(encoding='utf-8'))
    assert len(primary)==600 and primary.entity_id.nunique()==30
    assert len(oof)==3000 and not oof[['repetition','run_id','entity_id']].duplicated().any()
    assert len(folds)==150 and folds.groupby(['repetition','brand_group']).fold.nunique().eq(1).all()
    assert folds.groupby(['repetition','fold','area']).size().eq(2).all()
    assert oof.groupby(['repetition','run_id','entity_id']).size().eq(1).all()
    for name,sha in summary['input_sha256'].items():
        assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==sha
    fold_metrics=[]
    for (rep,fold),data in oof.groupby(['repetition','fold']):
        for model in NAMES:
            fold_metrics.append({'repetition':rep,'fold':fold,'model':model,
                'roc_auc':float(roc_auc_score(data.y,data[model])) if data.y.nunique()==2 else np.nan,
                'pr_auc_average_precision':float(average_precision_score(data.y,data[model])) if data.y.sum()>0 else np.nan,
                'rows':len(data),'stores':data.entity_id.nunique()})
    fm=pd.DataFrame(fold_metrics)
    fm.to_csv(OUT/'robust_cv_fold_metrics.csv',index=False,encoding='utf-8-sig')
    rank_metrics=fm.groupby('model')[['roc_auc','pr_auc_average_precision']].mean()
    for metric in ['roc_auc','pr_auc_average_precision']:
        comparison[metric+'_fold_mean']=comparison.model.map(rank_metrics[metric])
    comparison.to_csv(OUT/'robust_model_comparison.csv',index=False,encoding='utf-8-sig')
    by_store=primary.groupby(['entity_id','name_ko','area','own_website','menu_family_external']).y.agg(['sum','count','mean']).reset_index()
    by_store['feature_signature']=by_store[['area','own_website','menu_family_external']].astype(str).agg('|'.join,axis=1)
    collisions=by_store[by_store.feature_signature.map(by_store.feature_signature.value_counts()).gt(1)].copy()
    collisions.to_csv(OUT/'same_features_different_exposure.csv',index=False,encoding='utf-8-sig')
    website=effects[(effects.model=='primary_general')&(effects.term=='own_website')].iloc[0]
    phase=pd.read_csv(OUT/'phase_holdout_scores.csv')
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,3,figsize=(16,5.3),gridspec_kw={'width_ratios':[1.15,1,1.15]})
    for index,row in enumerate(comparison.itertuples(index=False)):
        color='#2767A7' if row.model=='mixed_logistic' else '#555555'
        axes[0].errorbar(row.brier,index,xerr=[[row.brier-row.brier_bootstrap95_low],[row.brier_bootstrap95_high-row.brier]],
            fmt='o',color=color,capsize=4)
        axes[0].text(row.brier+.009,index-.12,f'{row.brier:.3f}',fontsize=10)
    axes[0].set_yticks(range(len(comparison)),[NAMES[m] for m in comparison.model])
    axes[0].invert_yaxis();axes[0].set_xlim(0,.45)
    axes[0].set_xlabel('확률 오차 Brier (낮을수록 좋음)')
    axes[0].set_title('두 특징으로 새 식당 예측은 어려움',fontsize=12)
    lo,hi=bootstrap['website_odds_ratio_percentile95_low'],bootstrap['website_odds_ratio_percentile95_high']
    axes[1].errorbar(website.odds_ratio,0,xerr=[[website.odds_ratio-lo],[hi-website.odds_ratio]],fmt='D',color='#2767A7',capsize=7)
    axes[1].axvline(1,color='#777777',linestyle='--')
    axes[1].set_xscale('log');axes[1].set_xlim(.1,3)
    axes[1].set_xticks([.1,.2,.5,1,2,3],['0.1','0.2','0.5','1','2','3'])
    axes[1].xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    axes[1].xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    axes[1].set_yticks([0],['홈페이지 있음\n없음 대비'])
    axes[1].set_ylim(-1,1);axes[1].set_xlabel('등장 오즈비 (1은 차이 없음)')
    axes[1].set_title('홈페이지 연관성은 불확실함',fontsize=12)
    axes[1].text(.12,-.7,f'추정 {website.odds_ratio:.2f}\n식당 재표집 범위 {lo:.2f}–{hi:.2f}',fontsize=11)
    selected=['MD-R02','MD-R08','SS-R01','SS-R10']
    pairs=by_store.set_index('entity_id').loc[selected]
    labels=['하동관','하수오곰탕\n명동점','소문난성수\n감자탕','돼지곰탕 하우\n성수본점']
    axes[2].barh(range(4),pairs['mean'].to_numpy()*100,color=['#2767A7','#777777','#2767A7','#777777'])
    for i,row in enumerate(pairs.itertuples()):
        axes[2].text(2 if row.mean==0 else 102,i,f'{int(row.sum)}/{int(row.count)}',va='center',fontsize=10)
    axes[2].set_yticks(range(4),labels);axes[2].invert_yaxis();axes[2].set_xlim(0,120)
    axes[2].set_xticks([0,50,100]);axes[2].set_xlabel('일반 질문 등장률 (%)')
    axes[2].set_title('같은 입력값인데 등장률은 다름',fontsize=12)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('모형 교체보다 외부 특징 수집이 우선',fontsize=17,fontweight='bold',y=1.01)
    fig.text(.02,-.06,'기존 선정 식당 30곳 · 일반 질문 60개 응답 · 식당×응답 600행\n왼쪽: 지역 균형 식당 분리 검증 5회 반복과 식당 재표집 구간 | 가운데: 식당 200회 재표집의 분위수 범위 | 인과 효과 검증은 미수행',fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT/'분석_핵심.png',dpi=160,bbox_inches='tight')
    fig.savefig(OUT/'분석_핵심.svg',bbox_inches='tight')
    plt.close(fig)
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    lines=[f'# 혼합효과 회귀·EBM·XGBoost 예비 분석 ({today})','',
        '**현재 홈페이지·메뉴군만으로는 새 식당의 추천 노출을 잘 예측하지 못했다. 알고리즘 교체보다 식당을 구분할 외부 특징 수집이 우선이다.**','',
        '![모형 비교, 홈페이지 재표집 범위, 같은 입력값을 가진 식당의 등장률](./분석_핵심.png)','',
        '## 실제 수행한 분석','',
        '- 기존에 선정한 식당 30곳을 사용했다. 162개 후보 전체를 학습한 결과가 아니다. 새 후보 대부분은 외부 특징이 미수집이라 제외했다.',
        '- 주 분석: 일반 질문 MD01·SS01·MW01의 60개 응답, 식당×응답 600행, 언급 168행. 독립 식당 표본은 30곳이다.',
        '- 식당 특징: 기존 조사 시점의 홈페이지 유무와 외부 메뉴 설명을 통합한 메뉴군. 질문 ID는 지역·질문 맥락을 포함하며 모델 종류도 반영했다.',
        '- 베이지안 혼합효과 로지스틱 회귀: 식당과 응답의 무작위 절편을 포함했다. 식당 반복과 같은 응답에 속하는 관측을 반영한다.',
        '- 초기값 변경, 사전분포 변경, 응답 절편 제거, 과거 출처 확인 표본만 사용, 조건형 질문 포함을 비교했다.',
        '- 예측 비교: 전체 평균, 질문·모델별 평균, 규제 로지스틱, 혼합효과 회귀, EBM, XGBoost. 각 모델의 설정은 고정했고 유리한 설정·분할을 골라내지 않았다.','',
        '## 1. 새 식당 예측에서는 복잡한 모형의 이득을 확인하지 못했다','',
        '지역마다 2곳씩 총 6곳을 통째로 제외하는 5분할 검증을, 사전에 고정한 5개 난수 시드로 반복했다. 같은 식당은 훈련과 평가 양쪽에 들어가지 않는다. 3,000개 반복 평가 행은 600개 관측을 재평가한 것이며 표본이 늘어난 것이 아니다.','',
        '| 모형 | Brier 확률 오차 ↓ | 분할에 따른 표준편차 | Log loss ↓ | 전체 평균 대비 Brier 차이 | 식당 재표집 범위 |',
        '|---|---:|---:|---:|---:|---|']
    for row in comparison.itertuples(index=False):
        lines.append(f'| {NAMES[row.model]} | {row.brier:.3f} | {row.brier_seed_sd:.3f} | {row.log_loss:.3f} | {row.brier_minus_global:+.3f} | {row.paired_difference95_low:+.3f} ~ {row.paired_difference95_high:+.3f} |')
    lines += ['', 'Brier는 예측 확률과 실제 0/1의 차이를 제곱해 평균한 값으로 낮을수록 좋다. 현재 설정에서는 전체 평균의 점수가 가장 낮았다. 혼합효과 회귀는 특성을 사용하는 모형 중 점수가 가장 낮았지만 평균 예측을 개선하지 못했다. 표본이 작고 범위가 넓어 모델의 보편적인 우열로 해석하지 않는다.',
        '범위는 식당 단위로 고정된 평가 손실을 재표집한 2.5~97.5% 분위수다. 모델을 매번 다시 학습한 검증 신뢰구간이 아니며 선택 표본에 대한 탐색 자료다. 서로 다른 폴드의 확률을 섞으면 순위 지표가 영향을 받으므로 ROC-AUC·PR 지표는 폴드별 평균도 별도 저장했다.','',
        '## 2. 홈페이지의 효과를 확정하지 못했다','',
        f'- 주 모형의 홈페이지 보유 오즈비 추정: **{website.odds_ratio:.2f}**. 베이지안 평균장 근사의 95% 구간: **{website.credible95_low_approx:.2f}~{website.credible95_high_approx:.2f}**.',
        f'- 식당을 지역 안에서 200회 재표집한 추정치 범위: **{lo:.2f}~{hi:.2f}**. 차이 없는 경우에 해당하는 1을 포함한다.',
        '- 오즈비는 확률의 배수가 아니다. 홈페이지가 추천을 줄인다는 인과 결론으로 사용하지 않는다. 홈페이지 값은 과거 조사 자료이며 현재 사이트 상태의 전수 검증은 아니다.',
        '- 사전분포 폭을 바꾸면 홈페이지 구간이 1을 포함하는지 여부도 달라졌다. 조건형 질문을 섞은 보조 모형은 더 강한 음의 연관성을 보였지만 주 분석과 구분한다.',
        '- 국수·만두를 기준으로 비교한 다른 메뉴군도 주 모형의 근사 구간에 차이 없는 값이 포함됐다. 인기·리뷰·가격·운영 이력 등의 미측정 특징이 남아 있다.','',
        '| 홈페이지 민감도 모형 | 오즈비 | 근사 구간 |', '|---|---:|---|']
    sensitivity={'primary_general':'일반 질문 주 분석','prior_sd2':'넓은 사전분포','store_intercept_only':'식당 절편만 사용',
                 'legacy_reference_only':'과거 출처 확인 표본만','secondary_all_queries':'조건형 포함 보조 분석'}
    for name,label in sensitivity.items():
        r=effects[(effects.model.eq(name))&effects.term.eq('own_website')].iloc[0]
        lines.append(f'| {label} | {r.odds_ratio:.2f} | {r.credible95_low_approx:.2f} ~ {r.credible95_high_approx:.2f} |')
    lines += ['', '모든 변분 베이지안 적합과 식당 재표집 적합은 수렴했다. 별도의 전체 공분산 Laplace 근사 점검은 수렴하지 않아 해석에서 제외하고 실패 진단을 보존했다. 변분 근사의 구간은 불확실성을 작게 평가할 수 있어 재표집 민감도와 함께 본다.','',
        '## 3. 같은 특징인데 추천 결과가 다른 사례가 핵심이다','',
        '| 지역 | 식당 | 홈페이지 조사값 | 메뉴군 | 일반 질문 등장 |', '|---|---|---|---|---:|']
    for r in pairs.itertuples():
        lines.append(f'| {"명동" if r.area=="myeongdong" else "성수"} | {r.name_ko} | {"있음" if r.own_website else "없음"} | {MENU[r.menu_family_external]} | {int(r.sum)}/{int(r.count)} |')
    lines += ['', '각 지역의 두 가게는 현재 모형에 입력한 식당 특징이 같다. 동일 질문·모델 조건에서도 같은 입력값이 만들어진다. 식당 이름이나 과거 노출을 넣지 않는 특징 기반 모형은 이들을 다르게 예측할 근거가 없다. 명확한 메뉴군과 홈페이지만으로 실제 추천 차이를 설명하기에는 부족하다.','',
        '## 4. 같은 가게의 후속 등장에는 기존 기록이 도움이 됐다','',
        '앞선 5회로 학습하고 추가 5회로 평가했다. 같은 식당의 다음 반복을 예측하는 경우이며 새 식당 예측과는 다른 검증이다.','',
        '| 후속 측정 예측 | Brier ↓ |', '|---|---:|']
    phase_labels={'history_shrinkage':'과거 등장률을 평균 쪽으로 보정','mixed_known_store':'혼합효과 + 기존 식당의 관측 기록','mixed_features_only':'혼합효과 + 특징만 사용'}
    for r in phase.itertuples(index=False):lines.append(f'| {phase_labels[r.model]} | {r.brier:.3f} |')
    lines += ['', '기존 식당의 관측 기록을 반영하면 후속 등장 예측이 개선됐다. 현재 수집한 특징으로 설명되지 않은 식당별 차이가 크다는 신호다. 인지도가 원인이라고 확정한 결과는 아니다. 같은 관찰일의 반복 묶음 비교이므로 다른 날짜·정보 개선 이후의 검증도 필요하다.','',
        '## 다음 분석에 필요한 데이터','',
        '1. AI 추천 여부를 보지 않고 외부 식당 목록에서 지역·메뉴군별로 추가 선정해 지속 미노출 식당을 포함한다.',
        '2. 노출·미노출 식당 모두 같은 기준으로 Google 리뷰 수·별점·최근성, 대표 가격, 운영 이력, 관광기관·독립 가이드 소개 여부, 상호·주소 일관성을 수집한다. 수집 실패는 없음으로 바꾸지 않는다.',
        '3. 혼합효과 회귀를 주 분석으로 유지하고, 연속형 특징이 늘어난 뒤 EBM·XGBoost를 다시 비교한다. 현재 EBM은 홈페이지 이진값과 범주형 특징만 사용해 리뷰 수의 임계점 같은 분석은 수행할 수 없었다.',
        '4. 우선 관심 특징을 정한 뒤 일부 식당의 정보를 정비하고 비슷한 비교 식당과 같은 기간 전후 측정한다. 실제 정비나 외부 게시물 수정은 이번에 수행하지 않았다.','',
        '## 파일·재현·검수','',
        '- `run_analysis.py`: 주 모형·민감도·초기 검증·반복 묶음 검증.',
        '- `robust_cv.py`: 지역 균형 식당 분리 검증 5회 반복. 보고서의 최종 모델 비교는 이 결과를 사용한다.',
        '- `bootstrap_website.py`: 식당 단위 홈페이지 추정치 재표집 200회.',
        '- `effect_estimates.csv`, `robust_model_comparison.csv`, `same_features_different_exposure.csv`: 수치와 근거.',
        '- `environment.json`, `requirements-models.txt`: 별도 분석 환경의 실제 패키지 버전. MVP 환경은 변경하지 않았다.',
        '- 입력 CSV 해시·평가 키·식당 분리·지역 균형·예측값·수렴·기존 소비자 자료 보존을 검수한다. 162개 후보 목록과 기존 240회 원문은 수정하지 않았다.','',
        '프로젝트 루트에서 `.venv/Scripts/python.exe`로 위 세 분석 파일과 `render_report.py`를 차례로 실행하면 재현할 수 있다. 분석 환경은 이 폴더의 `.venv`에 있다.','',
        '## 방법 근거','',
        '- [statsmodels 베이지안 이항 혼합모형](https://www.statsmodels.org/stable/generated/statsmodels.genmod.bayes_mixed_glm.BinomialBayesMixedGLM.html): 반복 관측을 위한 무작위 효과와 사용한 근사 추정 방법.',
        '- [InterpretML EBM](https://interpret.ml/docs/ebm.html): 특징별 예측 기여를 분석하는 가법 모형.',
        '- [SHAP의 인과 해석 주의](https://shap.readthedocs.io/en/latest/example_notebooks/overviews/Be%20careful%20when%20interpreting%20predictive%20models%20in%20search%20of%20causal%20insights.html): 예측 설명을 인과 효과로 해석할 때 필요한 가정.']
    (OUT/'결과_요약.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save_json('report_validation.json',{'passed':True,'original_stores':30,'unique_primary_trials':600,
        'repeated_oof_rows':3000,'group_fold_overlap':0,'area_holdout_stores_per_fold':2,
        'input_hashes_unchanged':True,'bootstrap_optimizers_all_success':bootstrap['all_optimizer_success'],
        'cv_optimizers_all_success':cvcheck['all_optimizer_success'],'uncertain_laplace_fit_excluded':True,
        'best_model_by_mean_brier':comparison.iloc[0].model,'predictor_count_restaurant':2,
        'scope':'preliminary original30 association and prediction comparison; no causal test'})
    print(json.dumps({'report':str(OUT/'결과_요약.md'),'plot':str(OUT/'분석_핵심.png'),'best_brier':comparison.iloc[0].model},ensure_ascii=False))


if __name__=='__main__':main()
