# 한눈 식당 AI 노출 관찰실험 v1

## 2026-10-16 지도 정보 작성 방식 연구 분리

새 요청에 따라 네이버·카카오·구글 지도 기준 CLI 연구를 별도 폴더에서 시작했다. 초기 접근 파일럿 18셀은 정상 응답 13건·타 사이트 기반 추천 64건, URL 열람 권한 실패 5건이며 CLI의 지도 본문 열람은 검증되지 않았다. 이후 **지도 정보 제공 통제 실험 96회**와 카카오 후보 60곳 상세 대조·메뉴 221개 수집, 네이버 업주 소개 2곳 추가 확인을 완료했다. 통제 실험은 자연 검색 노출과 구분하며, 본 측정 90회·네이버/구글 전수 대응은 남아 있다. 과거 240회와 합산하지 않는다. 아래 과거 설계의 네이버 제외 조건은 새 연구에 적용하지 않는다. [새 연구 최신 결과](../지도기반_AI노출_20261016/수집_검수_후속결과.md).

## 2026-10-14 외부 특징 보강 완료

기존 30개 항목을 같은 기준으로 조사해 28곳의 다이닝코드 리뷰·별점·표시 사진·가격과 미쉐린 전체 목록을 수집했다. 리뷰 수를 추가한 혼합효과 회귀에서 Brier 오차가 0.227→0.176으로 줄었고, 신원 문제 항목을 제외한 26곳 재분석에서도 개선이 유지됐다. 규제 로지스틱도 개선됐으며 XGBoost·EBM의 추가 이득은 확인하지 못했다. 선정 표본의 연관성 탐색이며 인과 효과는 아니다. [최신 외부 특징 분석·정규화 자료·재실행](cli_한국어_탐색/확장분석/외부특징분석/결과_요약.md).

## 2026-10-13 추가: 한국어 CLI 추천 특징 탐색

2026-10-14 후속: 기존 30곳의 일반 질문 자료로 혼합효과 회귀·EBM·XGBoost 예비 비교를 실제 실행했다. 현재 두 특징만으로는 새 식당 예측에서 단순 평균보다 좋은 결과를 확인하지 못했다. [모형 비교·근거·재현 보고서](cli_한국어_탐색/확장분석/혼합효과분석/결과_요약.md). 아래 광범위 특징 학습 미실행 표시는 10월 13일 전처리 단계의 상태이며, 30곳의 후속 예비 분석과 구분한다.

사용자 결정에 따라 국적·VPN·영어 질문 조건을 제외하고, 현재 CLI에서 한국어 추천 질문 12개를 모델별 10회 반복한 240회 탐색 실험을 완료했다. Codex와 Antigravity의 Gemini 모델을 사용하며 소비자 웹 결과와 합산하지 않는다. 기존 식당 30곳과 앞선 응답에서 발견한 후보 132개를 구분한 162개 후보를 분석했다. 후보 전체의 실제 지점 검수와 외부 특징 수집은 미완료다.

- 최신 결과: [`확장 분석 요약`](cli_한국어_탐색/확장분석/분석_전처리_요약.md)
- 분석 방법과 재실행: [`분석방법_전처리.md`](cli_한국어_탐색/확장분석/분석방법_전처리.md)
- 240회 실행 상태와 검수: `cli_한국어_탐색/확장분석/runs_clean.csv`, `validation.json`
- 동일 후속 기간의 식당별 등장률: `cli_한국어_탐색/확장분석/ranking_prospective_all_candidates.csv`
- 전처리 후보표: `cli_한국어_탐색/확장분석/model_table_prospective.csv` (외부 특징 미수집 값은 결측; XGBoost 학습은 미실행)
- 앞선 120회 고정 결과: `cli_한국어_탐색/확장분석/baseline_120_요약.md`. 기존 `run_manifest.csv`, `sample_visibility.csv` 등은 앞선 120회 자료다.
- 실제 질문: `cli_한국어_탐색/prompts_ko.csv`

아래는 기존 외국인 소비자 웹 실험 설계이며 별도로 유지한다.

## 현재 목적

외국인 관광객이 영어로 서울 식당을 추천받을 때 어떤 식당이 ChatGPT와 Gemini 답변에 등장하는지 반복 측정한다. 이번 단계는 **정보 수정 전 기준선 관찰실험**이며, 노출 원인을 확정하거나 개선 효과를 주장하지 않는다.

## 고정 범위

- 대상: 미국 영어권 자유여행객
- 지역: 명동, 성수, 망원
- 표본: 지역별 10곳, 총 30곳
- 플랫폼: 소비자용 ChatGPT, 소비자용 Gemini
- 시나리오: 미국에서 여행 준비 / 서울 현지 이용
- 질문: 지역별 4개, 총 12개
- 반복: 질문별 5회, 항상 새 대화
- 총 실행: `2개 플랫폼 × 2개 시나리오 × 12개 질문 × 5회 = 240회`
- 제외: 네이버 플레이스, 인터뷰, 실제 식당 정보 수정

## 환경 구분

| 시나리오 | 핵심 조건 |
|---|---|
| `pre_trip_us` | 영어 UI·영어 질문, 개인화·메모리 없음, 정밀 위치 끔, 미국 IP 또는 API의 미국 위치, 목적지는 질문에 명시 |
| `in_korea` | 영어 UI·영어 질문, 개인화·메모리 없음, 서울 IP, 위치 허용, 해당 지역에서 `near me` 맥락 사용 |

소비자 앱 결과와 API·Antigravity 결과는 합치지 않는다.

- 소비자용 ChatGPT/Gemini: 실제 사용자 노출의 1차 지표
- 위치 지정 API: 조건 통제와 민감도 확인용 보조 지표
- Antigravity CLI: 프롬프트·저장 구조 점검용 공학 파일럿. Gemini 앱 노출 지표가 아님

### 2026-10-08 소비자 파일럿 고정값

- 미국 IP: Atlanta, Georgia로 확인
- ChatGPT: English UI, Temporary Chat, Unpersonalized, 화면 표시 모델 `Instant`
- Gemini: English UI, Temporary Chat, `3.8 Flash`
- Gemini `3.1 Pro`는 사전 점검에서 오류와 장시간 정지가 재현되어 이번 48회 파일럿의 고정 모델에서 제외한다.
- 사전 점검은 `data/shakedown_2026-10-08.md`에 기록하며 분석 대상에서 제외한다.
- 공식 실행 결과는 `data/consumer_results.csv`, 원문은 `data/raw/`에 저장한다.
- 미국 환경 파일럿 진행: 성공 결과 `14/24`건 저장, Gemini 오류·정지 `6`건은 `data/consumer_failures.csv`에 별도 기록해 통계에서 제외, 미시도 `4`건.
- 현재 성공 내역: ChatGPT `9`건, Gemini `5`건. 실패한 Gemini 실행은 같은 모델·새 임시 대화로 나중에 다시 시도한다.

## 표본 원칙

1. AI 추천 답변을 보기 전에 표본을 정한다.
2. 지역별로 사전 공개정보가 많은 곳과 적은 곳을 섞는다.
3. 동일 브랜드의 여러 지점은 하나의 지점 ID로 고정한다.
4. 영업 여부와 주소는 실험 실행 당일 다시 확인한다.
5. `prior_visibility_stratum`은 사전 층화일 뿐 결과가 아니다.

## 질문 원칙

- 식당명을 질문에 넣지 않는다.
- 모든 질문은 정확히 5곳을 요청한다.
- 현재 영업 여부를 확인하고 지어내지 말라고 요청한다.
- 지역, 예산, 식사 상황처럼 실제 여행자가 쓸 조건을 섞는다.
- 여행 전과 현지 시나리오는 의도는 같고 상황 표현만 바꾼다.

## 1차 지표

- `appearance_rate`: 전체 실행 중 표본 식당이 한 번이라도 등장한 비율
- `mean_reciprocal_rank`: 등장 순위의 역수 평균
- `top1_rate`, `top3_rate`, `top5_rate`
- `source_rate`: 식당을 뒷받침하는 출처 URL이 제공된 비율
- `accuracy_rate`: 상호·주소·영업·가격 정보가 검증 가능한 비율
- `hallucination_rate`: 실재하지 않거나 식별 불가능한 식당 비율
- `run_variability`: 같은 조건 5회 사이 추천 집합 변동

## 실행 절차

1. 데이터 검증

   ```powershell
   & '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' validate
   ```

2. 240회 실행표 생성

   ```powershell
   & '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' build-manifest
   ```

3. 먼저 48회 파일럿 실행표를 생성한다.

   ```powershell
   & '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' build-pilot-manifest
   ```

4. 소비자 앱에서 파일럿 실행표 순서대로 새 대화를 열어 질문한다.
5. 원문 답변·모델명·시각·출처를 그대로 저장한다.
6. 추천 식당을 정규화하고 사람이 한 번 검수한다.
7. 환경과 수집 항목에 문제가 없으면 240회 기준선 측정으로 확대한다.
8. 기준선 분석 후 한두 식당을 골라 정보 개선 전후 실험으로 넘어간다.

## Antigravity 공학 파일럿

아래 실행은 계정의 Google AI Pro 사용량을 사용하지만, 결과는 소비자용 Gemini 측정치에 포함하지 않는다.

```powershell
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' agy-pilot --prompt-id MD01 --scenario pre_trip_us --repeats 1
```

기본 모델은 비용과 사용량을 아끼기 위해 `Gemini 3.8 Flash (Low)`이다. 결과는 `data/agy_pilot.jsonl`에 저장된다. 표본 식당 매칭 요약은 아래 명령으로 생성한다.

```powershell
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' summarize-agy
```

## 아직 필요한 사용자 환경

- 소비자용 여행 전 시나리오: 미국 VPN 권장
- 소비자용 현지 시나리오: 서울에서 위치 권한을 켠 실제 실행 권장
- OpenAI/Gemini API 통제실험: 각각의 API 키와 별도 API 결제 필요
