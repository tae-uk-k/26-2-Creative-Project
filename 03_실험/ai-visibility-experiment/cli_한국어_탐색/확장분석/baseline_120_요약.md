# 한국어 CLI 식당 추천 특징 탐색

2026-10-13 · 성공 120/120회 · 미완료 0회 · 상태: 실행 완료

## 실행 조건

- 명동·성수·망원 각 4개 한국어 질문, 모델별 질문당 5회, 매번 새 세션.
- VPN·국적·여행 시나리오를 통제하지 않은 현재 CLI 환경. 질문에 식당 목록이나 이름을 제공하지 않음.
- Codex 요청 모델: `gpt-6.1-sol` / Antigravity 표시 모델: `Gemini 3.8 Flash (Low)`.
- 실제 검색 호출 로그와 응답 원문을 저장. 표본 밖 추천도 모두 보존.
- Gemini CLI 자체는 `UNSUPPORTED_CLIENT` 오류로 실행 불가. Gemini 측정은 Antigravity로 분리하며, 기존 소비자 웹 결과와 합산하지 않음.

## 실행 현황

| 도구 | 성공 | 시간 초과 | 기타 실패 |
|---|---:|---:|---:|
| agy | 60 | 6 | 1 |
| codex | 60 | 5 | 0 |
| gemini | 0 | 0 | 1 |

응답이 없는 오류·시간 초과는 추천 미노출로 집계하지 않음. 단, 원문에 공급자의 완료 표식(Codex turn.completed / Antigravity result SUCCESS)과 5개 추천 JSON이 확인된 경우는 응답 성공과 CLI 종료 오류를 구분해 응답을 사용한다. 원본 실행 상태와 재판정은 response_review.csv에 보존하며, 응답 성공과 프로세스 시간 초과 숫자는 겹칠 수 있다.

## 주요 식당의 등장 횟수

분모는 해당 지역의 성공한 질문 수. 일반·예산·혼밥·메뉴 질문이 섞인 탐색 지표이며, 상호 기준 등장과 기존 표본 주소 일치 등장을 별도로 기록했다. 아래 표는 상호 기준이며, 기존 표본 주소가 함께 표시된 횟수는 sample_visibility.csv의 appeared_runs_original_address_match 열에 기록했다. 주소 일치는 응답과 기존 표본의 대조이며 실제 영업·이전 여부를 검증한 판정이 아니다.

| 지역 | 식당 | Codex | Gemini / Antigravity |
|---|---|---:|---:|
| 명동 | 명동교자 | 17/20 | 20/20 |
| 명동 | 하동관 | 14/20 | 15/20 |
| 명동 | 명동함흥면옥 | 15/20 | 2/20 |
| 명동 | 미성옥 | 9/20 | 13/20 |
| 명동 | 하수오곰탕 명동점 | 0/20 | 0/20 |
| 명동 | 고시레 명동본점 | 0/20 | 0/20 |
| 성수 | 소문난성수감자탕 | 13/20 | 13/20 |
| 성수 | 성수족발 | 5/20 | 2/20 |
| 성수 | 할머니의 레시피 | 3/20 | 5/20 |
| 망원 | 우이락 망원본점 | 14/20 | 14/20 |
| 망원 | 홍두깨손칼국수 | 13/20 | 12/20 |
| 망원 | 망원동즉석우동 본점 | 6/20 | 8/20 |

전체 추천 600개 슬롯 중 기존 30곳과 상호가 매칭된 슬롯은 269개. 나머지는 표본 밖 또는 미매칭으로 별도 보존.

## 이번에 검토할 특징

1. **대표 메뉴와 축적된 외부 소개 정보**: 자주 등장하는 명동교자·하동관은 미쉐린의 개별 소개 페이지에서 대표 메뉴와 오랜 운영 이력을 확인했다. 소문난성수감자탕·우이락도 관광기관 자료에 가게별 특징이 구체적으로 공개되어 있다. 추천 원인이라고 확정하지 않고 다음 비교 가설로 사용한다.
2. **홈페이지·가격표 공개만으로는 충분하지 않은 사례**: 하수오곰탕·고시레는 자체 사이트, 주소, 메뉴 가격을 직접 확인했다. 이들의 실제 등장 횟수는 위 표와 CSV에 기록했다. 사이트 보유 효과 전체를 부정하거나 외부 소개 효과를 증명한 결과는 아니다.
3. **질문 조건별 차이**: 예산·혼밥·시장 음식 등 요구에 따라 후보가 달라짐. 특징 비교에는 조건이 적은 일반 질문의 등장률도 별도 제공한다.

## 반복 측정과 모델 차이

- codex: 같은 질문의 두 응답을 비교할 때 평균 2.52/5곳이 겹침. 현재 120개 응답 쌍 기준.
- agy: 같은 질문의 두 응답을 비교할 때 평균 3.00/5곳이 겹침. 현재 120개 응답 쌍 기준.
- 같은 질문·반복 번호로 두 모델을 비교하면 평균 2.00/5곳이 겹침. 현재 60쌍 기준.

## 해석 범위와 검수

- 30곳은 기존에 선정한 표본이며 지역 전체 식당의 전수 목록이 아니다. 표본 밖 추천은 제외하지 않는다.
- 5회 반복은 추천 변동을 관찰하기 위한 반복이며, 동일 식당을 독립 표본 5개로 부풀려 통계 검정하지 않는다.
- 홈페이지 보유 여부 비교 CSV는 기존 목록의 조사 시점 값이다. 이번에 직접 확인한 특징은 `feature_checks.csv`에 구분했다.
- 리뷰 수·별점·사진 수의 효과는 아직 측정하지 않았으므로 주장하지 않는다.
- 상호 매칭과 실제 지점·현재 영업·가격 정확도는 별개다. 출처 전체의 내용 검증을 완료한 상태가 아니며, 일부 접근 오류는 죽은 링크라고 단정하지 않는다.
- `page_source_count`는 URL 경로 유무를 세는 기계적 검사로, 페이지가 식당 정보를 뒷받침한다는 판정이 아니다.
- 기존 표본의 MW-R04는 흥흥호떡으로 적혀 있으나 응답의 훈훈호떡과 Hoon-Hoon Hotteok 자료를 주소 기준으로 대조하는 항목이다. 원본 표본은 변경하지 않았다.

## 확인한 공개 자료

- [명동교자: 메뉴·운영 이력](https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/myeongdong-kyoja)
- [하동관: 메뉴·운영 이력](https://guide.michelin.com/kr/ko/seoul-capital-area/kr-seoul/restaurant/hadongkwan)
- [소문난성수감자탕: 혼밥·운영 정보](https://stage-kr.visitseoul.net/restaurants/SeongsuGamjatang/KOPlceoxk)
- [우이락: 대표 메뉴·주소](https://english.visitkorea.or.kr/svc/thingsToDo/foodTrip/special_view.do?vcontsId=187836)
- [하수오곰탕 메뉴](https://www.myeongdong-restaurant.com/ko/menu)
- [고시레 메뉴·주소](https://www.myeongdongkoreanbbq.kr/ko)

## 파일과 재실행

- `prompts_ko.csv`: 실제 질문 원문 / `run_manifest.csv`: 120회 실행 상태.
- `results_codex.jsonl`, `results_agy.jsonl`, `raw/`: 원문과 실행 로그.
- `sample_visibility.csv`: 표본 30곳의 모델별 노출률과 일반 질문 노출률.
- `recommendations.csv`: 표본 밖을 포함한 전체 추천 / `sources.csv`: 모델 반환 출처.
- `repeat_consistency.csv`, `cross_model_overlap.csv`: 반복 변동과 모델 간 공통 추천.
- `feature_checks.csv`, `source_checks.csv`: 직접 확인한 특징과 출처 접근 기록.

```powershell
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\cli_한국어_탐색\run_cli.py' --backend codex --repeats 5 --workers 2
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\cli_한국어_탐색\run_cli.py' --backend agy --repeats 5 --workers 1 --timeout 300
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\cli_한국어_탐색\summarize.py'
```

재실행 시 성공한 실행 ID는 건너뛰고 미완료만 수행한다. 로그인된 계정의 사용량을 사용한다.
