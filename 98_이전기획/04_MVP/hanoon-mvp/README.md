# 한눈(Hanoon) MVP

외국인 관광객이 ChatGPT·Gemini 같은 AI에게 장소를 물어볼 때, 소규모 가게가 추천 답변에 발견될 가능성을 높이도록 현재 노출 상태를 진단하고 온라인 정보를 정비한 뒤 전후 변화를 보여주는 시연용 MVP입니다.

## 구현 범위

- 서비스 소개 랜딩 페이지
- 가게 정보 입력 및 유효성 검사
- 더미데이터 기반 AI 노출 진단 보고서
- 영문 정보·관광객 조건·채널 일관성 개선안
- 영문 소개 문안 편집·복사·승인
- 공개 영문 소개 페이지 미리보기
- 동일 조건의 개선 전후 지표 비교
- 모바일·데스크톱 반응형 화면

실제 OpenAI·Gemini API, 지도·SNS 자동 수정, 결제, 회원가입, 결과 영구 저장은 포함하지 않습니다.

## 실행 방법

Windows PowerShell 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

브라우저에서 `http://127.0.0.1:5000`에 접속합니다.

Windows에서는 `run.bat`을 실행해도 같은 과정을 자동으로 진행합니다.

## 테스트

```powershell
python -m pytest -q
```

### 핵심 기술 테스트 코드

화면 렌더링만 확인하는 것이 아니라 서비스의 핵심 기술을 별도 모듈로 구현하고 테스트합니다.

- `core/visibility.py`: 반복 AI 답변의 추천 등장률·평균 순서·정보 정확도·조건 반영률 계산
- `find_missing_tourist_fields()`: 영문 메뉴·가격·결제·식이 정보 등의 누락 탐지
- `find_channel_conflicts()`: Google Maps·Naver Place·Instagram의 주소·영업시간 불일치 탐지
- `compare_visibility()`: 질문·반복 횟수·모델·언어가 같은지 확인한 뒤 정비 전후 변화량 계산
- `tests/test_visibility_engine.py`: 정상·미노출·누락·불일치·측정 조건 오류·전후 개선 시나리오 검증

핵심 기술 테스트만 실행하려면 다음 명령을 사용합니다.

```powershell
python -m pytest tests/test_visibility_engine.py -v
```

Windows에서는 `test_core.bat`을 실행하면 가상환경 준비부터 핵심 테스트 실행까지 자동으로 진행됩니다.

## 프로젝트 구조

```text
hanoon-mvp/
├─ app.py
├─ requirements.txt
├─ test_core.bat
├─ core/
│  ├─ __init__.py
│  └─ visibility.py
├─ data/
│  └─ demo_store.json
├─ templates/
│  ├─ base.html
│  ├─ index.html
│  ├─ demo.html
│  └─ store_preview.html
├─ static/
│  ├─ css/app.css
│  ├─ js/demo.js
│  ├─ js/store-preview.js
│  └─ favicon.svg
└─ tests/
   ├─ test_app.py
   └─ test_visibility_engine.py
```

## 주의

화면의 가게와 측정 수치는 모두 가상 데이터입니다. 한눈은 특정 AI 추천 순위나 노출을 보장하지 않으며, 사실에 기반한 정보 정비와 반복 측정을 지원하는 서비스입니다.
