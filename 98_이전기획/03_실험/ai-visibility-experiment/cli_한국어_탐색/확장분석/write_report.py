"""Render the report from audited tables; never hard-code observed rates."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from prepare import ROOT, STUDY, AREA_NAMES, completed_runs, load_csv, save_csv


def pct(value): return f"{float(value)*100:.1f}%"


def write_report():
    info=json.loads((ROOT/'analysis_summary.json').read_text(encoding='utf-8'))
    s=info['summary']
    runs, attempts=completed_runs()
    counts=Counter(r['backend'] for r in runs)
    rankings=load_csv(ROOT/'ranking_by_cohort.csv')
    prospective=load_csv(ROOT/'ranking_prospective_all_candidates.csv')
    stability=load_csv(ROOT/'rank_stability.csv')
    differences=load_csv(ROOT/'model_differences_original.csv')
    features=load_csv(ROOT/'restaurant_features.csv')
    pages=[json.loads(x) for x in (ROOT/'source_pages.jsonl').read_text(encoding='utf-8').splitlines()]
    readiness=json.loads((ROOT/'model_readiness.json').read_text(encoding='utf-8'))
    lines=['# 한국어 CLI 식당 추천 확장 분석', '',
           f"갱신: {datetime.now(timezone.utc).isoformat()} · 성공 {s['run_count']}/240회 · 추가 성공 {s['prospective_runs']}/120회", '',
           f"후보 **162개**로 확대했다. 기존 표본 30곳과 앞선 응답에서 발견한 후보 132개를 구분했다. 추가 실행에서 다시 등장하는지 평가했으며, 전체 원문·실행 실패를 보존했다. 후보 수는 실제 지점 검수를 마친 식당 수와 다르다.", '',
           '## 어떤 식당이 더 자주 나왔나', '',
           '모두 추가 반복 6~10회만 사용한 표다. 분모는 해당 지역의 성공한 두 모델 응답 수다. 일반·예산·혼밥·음식 조건이 섞인 등장률이며 상호 기준이다. 전체 162개 순위는 `ranking_prospective_all_candidates.csv`에 있다.', '',
           '| 지역 | 상호 | 추가 등장/성공 응답 | 등장률 | 일반 질문 등장/응답 |',
           '|---|---|---:|---:|---:|']
    for area in AREA_NAMES:
        for r in [r for r in prospective if r['area']==area][:5]:
            name='훈훈호떡 (원표본: 흥흥호떡)' if r['entity_id']=='MW-R04' else r['name_ko']
            lines.append(f"| {AREA_NAMES[area]} | {name} | {r['appearance_count']}/{r['runs']} | {pct(r['appearance_rate'])} | {r['general_count']}/{r['general_runs']} |")
    lines += ['', '기존 표본은 앞선 측정까지 합쳐 모델별 최대 지역당 40개 응답에서 비교할 수 있다. 새 후보는 발견에 사용한 앞선 응답을 평가에서 제외한다.', '',
              '| 기존 표본 주요 식당 | Codex 전체 등장률 | Gemini 전체 등장률 |', '|---|---:|---:|']
    wanted={'MD-R01','MD-R02','MD-R05','MD-R06','MD-R08','MD-R09','SS-R01','MW-R01','MW-R07','MW-R10'}
    for r in rankings:
        if r['entity_id'] in wanted: lines.append(f"| {r['name_ko']} | {pct(r['codex_rate'])} | {pct(r['gemini_rate'])} |")
    lines += ['', '## 관찰된 패턴', '',
              f"1. **자주 나오는 식당에는 반복성이 있다.** 같은 질문의 두 응답에서 평균 Codex {info['mean_within_model_overlap']['codex']:.2f}/5곳, Gemini {info['mean_within_model_overlap']['agy']:.2f}/5곳이 겹쳤다. 두 모델끼리의 겹침은 {info['cross_model_overlap']:.2f}/5곳이었다. 매번 목록은 바뀌지만 일부 식당이 반복 등장한다.",
              '2. **모델별 차이가 크다.** 아래 차이는 같은 기존 식당 표본을 각 모델의 해당 지역 성공 응답 수로 나눈 값이다. 모델 차이를 평균 하나로 가리지 않고 따로 분석해야 한다.', '',
              '| 상호 | Codex | Gemini | 차이 Codex-Gemini |', '|---|---:|---:|---:|']
    for r in differences[:4]: lines.append(f"| {r['name_ko']} | {pct(r['codex_rate'])} | {pct(r['gemini_rate'])} | {float(r['difference_codex_minus_gemini_pp']):+.1f}%p |")
    perm=info['website_permutation']
    lines += ['',
              f"3. **홈페이지 보유만으로 높은 노출을 설명하지 못했다.** 일반 질문에서 지역을 맞춘 기존 표본의 홈페이지 보유-미보유 평균 차이는 {perm['area_standardized_difference_pp']:+.1f}%p였다. 탐색적 지역 내 순열검정 p={perm['p_two_sided_exploratory']:.3f}, 비교 식당 {perm['independent_stores']}곳이다. 홈페이지가 불리하다는 결론은 아니다. 선정 표본이 작고 메뉴·인지도 등이 통제되지 않았다. 자체 사이트와 가격 공개를 확인한 하수오곰탕·고시레의 실제 등장률은 위 표에 기록했다.",
              f"4. **한 번 발견한 후보가 계속 추천되는 것은 아니다.** 새 후보 132개 중 추가 측정에서 다시 등장한 후보는 {info['discovery_mentioned_again']}개, 등장하지 않은 후보는 {info['discovery_not_mentioned_again']}개였다. 후보 일부의 상호·지점 동일성은 미검수여서 실제 식당의 재추천 비율로 확정하지 않는다.",
              f"5. **기존 표본의 미노출 사례도 남겼다.** 기존 30곳 중 현재 전체 측정에서 {info['original_zero_exposure_count']}곳이 한 번도 언급되지 않았다. 폐업·이전 여부를 뜻하지 않는다.", '',
              '**후속 검증 가설:** 대표 메뉴의 명확성, 공식 관광·독립 가이드의 식당별 소개, 리뷰·운영 이력 등 축적된 외부 정보가 함께 작용하는지 비교한다. 명동교자·하동관의 가이드 소개, 소문난성수감자탕의 관광 소개는 확인했지만, 미노출 식당도 같은 기준으로 조사하기 전에는 효과 크기를 계산할 수 없다. 현재 리뷰 수·별점 효과는 판단하지 않는다.', '',
              '## 앞선 5회와 추가 5회의 순위 안정성', '',
              '| 모델 | 지역 | 기존 10곳 Spearman | 한 번이라도 노출된 식당 수 | 지속 미노출 제외 Spearman |', '|---|---|---:|---:|---:|']
    for r in stability:
        val=lambda key: f"{float(r[key]):.3f}" if r[key] else '계산 불가'
        lines.append(f"| {r['backend']} | {AREA_NAMES[r['area']]} | {val('spearman_baseline_vs_prospective')} | {r['ever_exposed_store_count']} | {val('spearman_among_ever_exposed')} |")
    lines += ['', '전체 10곳 상관은 계속 0인 식당의 동률에 영향을 받는다. 노출된 식당만의 값도 함께 기록했다. 소수의 선정 식당을 대상으로 한 기술통계다. Wilson 구간도 개별 응답의 독립성을 가정한 참고값이며 일반화·인과 추론을 보장하지 않는다.', '',
              '## 전처리 완료 항목', '',
              f"- 유효 응답 {s['run_count']}개, 추천 슬롯 {s['recommended_slots']}개, 식당×응답 행 {s['trial_rows']:,}개.",
              f"- 식당×모델 후속 집계 {s['model_table_rows']}행. 324행은 162개 후보의 두 모델 관측이며 독립 식당 324곳이 아니다.",
              '- 상호·별칭 정규화, 미매칭 검수 목록, 상호 언급/원본 주소 일치 구분, 완료된 응답의 미언급 0 처리.',
              '- 메뉴군 통합, 확인 가격 숫자화, 결측 표시, 향후 리뷰 수 log1p 변환, 식당 그룹 분리.',
              '- AI 추천 이유·반환 가격·출처 URL은 학습 입력에서 제외. 미수집 리뷰·별점은 0으로 채우지 않음.',
              f"- 고정 후보와 매칭하지 못한 추가·모호한 추천 {s['unmatched_slots']}슬롯은 `unmatched_review_queue.csv`에 보존. 후보 목록을 후속 응답으로 다시 늘리지 않음.",
              f"- 공개 URL {len(pages)}개 자동 점검: 본문 접근 {sum(r['access_status']=='accessible' for r in pages)}개. 자동 접근·제목 일치는 식당 검증 또는 학습 특징 확인과 다름.",
              f"- 외부 메뉴 분류 확보 {sum(r['category_external']!='' for r in features)}/162개, 홈페이지 조사값 {sum(r['own_website_external']!='' for r in features)}/162개, 정확한 대표 가격 {sum(r['signature_price_krw_external']!='' for r in features)}/162개. 전체 후보의 특징 수집은 미완료.", '',
              '## 분석 방법과 다음 데이터', '',
              '지역·질문·모델별 빈도와 반복 안정성을 먼저 보고, 외부 특징을 동일 기준으로 수집한 후 규제 회귀를 기준 모델로 사용한다. 이후 얕은 XGBoost를 식당 그룹을 분리해 검증하고, 검증 성능이 개선될 때 폴드별 중요도·SHAP을 확인한다. SHAP은 예측 연관성을 설명한다. 정보 정비의 효과는 비교 식당을 둔 전후 실험으로 확인한다.', '',
              f"**현재 XGBoost 학습은 수행하지 않았다.** 현재 특징 수집은 기존 표본의 홈페이지·메뉴군에 집중돼 있고 리뷰·사진·최근성 등 주요 값은 미수집이다. 검토 표본의 준비 확인 결과: {readiness['independent_restaurants']}개 상호 그룹, 학습 준비={readiness['ready_for_exploratory_training']}. 기존 30곳의 과거 조사 자료와 새 후보 5개의 외부 상호·주소 대조를 사용한 값이며 현장 영업 검증 수가 아니다. 환경 의존성과 상세 이유는 `model_readiness.json`에 기록했다.", '',
              '상세 방법·수집 기준·재실행 명령은 [분석방법_전처리.md](./분석방법_전처리.md)에 있다. 추가 표본은 AI 추천 결과를 보지 않고 외부 목록에서 지역·메뉴군별로 선정해 지속 미노출 식당을 포함해야 한다.', '',
              '## 실행 조건과 검수', '',
              f"- Codex {counts['codex']}/120, Gemini/Antigravity {counts['agy']}/120. 계획은 2개 모델×12개 한국어 질문×10회=240개 응답이다.",
              '- 요청 모델은 Codex gpt-6.1-sol, Antigravity Gemini 3.8 Flash (Low). 현재 위치를 통제하지 않은 CLI 결과이며 소비자 앱으로 일반화하지 않음.',
              '- 매 실행 새 세션에서 실제 웹 검색. 가게 이름·목록·프로젝트 파일을 질문에 제공하지 않음.',
              '- Gemini CLI 자체의 UNSUPPORTED_CLIENT 오류는 별도 기술 실패. Gemini 측정은 Antigravity를 사용함.',
              '- Codex 사용량 제한과 네트워크 오류는 미노출로 집계하지 않고 재시도. 원문 로그와 시도 기록 보존.',
              '- 후보 목록 해시·중복 행·실행 분모·결측·그룹 분리와 소비자 CSV 해시를 검수. `validation.json`은 자료 무결성 검수이며 현장 영업 검증이 아님.', '',
              '## 주요 파일', '',
              '| 파일 | 내용 |', '|---|---|',
              '| ranking_prospective_all_candidates.csv | 동일 후속 기간의 전체 후보 순위 |',
              '| restaurant_features.csv | 외부 특징과 결측 표시 |',
              '| exposure_trials.csv | 식당×유효 응답의 0/1·순위 관측 |',
              '| query_outcomes.csv | 식당×모델×질문×측정 단계 집계 |',
              '| model_table_prospective.csv | 후속 등장률과 외부 특징을 결합한 학습 후보표 |',
              '| unmatched_review_queue.csv / identity_review.csv | 상호·지점·출처 검수 대상 |',
              '| feature_missingness.csv / model_readiness.json | 수집 부족과 학습 준비 상태 |',
              '| prepare.py / analyze.py / validate.py / train_models.py | 재실행 가능한 전처리·분석·검수·향후 학습 코드 |',
              '| baseline_120_요약.md / baseline_runs_120.jsonl | 고정한 앞선 120회 결과 |']
    pilot_report = ROOT / '혼합효과분석' / '결과_요약.md'
    if pilot_report.exists():
        lines[1:1] = ['', '> 후속 모형 분석: 기존 30곳의 혼합효과 회귀·EBM·XGBoost 예비 비교를 실행했다. [2026-10-14 결과](./혼합효과분석/결과_요약.md). 아래 학습 미실행 표시는 광범위 특징 학습 준비 단계와 구분한다.']
    enriched_report = ROOT / '외부특징분석' / '결과_요약.md'
    if enriched_report.exists():
        lines[1:1] = ['', '> 최신 후속 분석: 28곳의 리뷰·평점·사진·가격과 미쉐린 전체 목록을 보강해 모형을 재비교했다. 리뷰 추가 혼합효과 오차 0.227→0.176. [2026-10-14 외부 특징 결과](./외부특징분석/결과_요약.md). 아래 수집 부족·학습 미실행 서술은 원래 162개 후보 전처리 스냅샷의 상태다.']
    (ROOT/'분석_전처리_요약.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    present={(r['backend'],r['prompt_id'],r['repeat']) for r in runs}
    missing=[{'backend':b,'prompt_id':p,'repeat':i,'reason':'no_completed_valid_response_yet'} for b in ('codex','agy') for p in sorted({r['prompt_id'] for r in runs}) for i in range(1,11) if (b,p,i) not in present]
    save_csv('remaining_runs.csv',missing,['backend','prompt_id','repeat','reason'])
    print(json.dumps({'report':str(ROOT/'분석_전처리_요약.md'),'successful_runs':len(runs),'remaining':len(missing)},ensure_ascii=False))


if __name__=='__main__': write_report()
