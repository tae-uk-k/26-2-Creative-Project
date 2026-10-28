# seelo — 외국인 대상 식당 AI 노출 연구

외국인 관광객이 ChatGPT·Gemini에서 서울 식당을 추천받을 때 어떤 식당이 노출되는지 측정하고, 정보 정비 전후 변화를 검증하는 창의프로젝트입니다.

진행 상황과 결정 사항은 [`컨텍스트_창의프로젝트.md`](./컨텍스트_창의프로젝트.md)에 정리합니다.

## 폴더 구조

```text
01_기획/       아이디어 발산, MVP 기획, 이전 주제 기록
02_조사/       식당 AI 노출 선행조사와 서비스 아이디어
03_실험/       ChatGPT·Gemini 소비자 환경 실험 코드와 결과
04_MVP/        seelo Flask MVP와 핵심 기술 테스트
05_발표자료/   PPT 원본, 제출 결과물, 제작·검수 자료
99_보관/       이전 텔레프롬프터와 이전 제출본 격리 자료
```

## 현재 핵심 파일

- 실험 안내: [`03_실험/ai-visibility-experiment/README.md`](./03_실험/ai-visibility-experiment/README.md)
- 소비자 실험 결과: `03_실험/ai-visibility-experiment/data/consumer_results.csv`
- 기술 실패 기록: `03_실험/ai-visibility-experiment/data/consumer_failures.csv`
- 응답 원문: `03_실험/ai-visibility-experiment/data/raw/`
- MVP 안내: [`04_MVP/hanoon-mvp/README.md`](./04_MVP/hanoon-mvp/README.md)
- 최종 제출물: `05_발표자료/결과물/`

## 실행

실험 데이터 검증:

```powershell
& '.\04_MVP\hanoon-mvp\.venv\Scripts\python.exe' '.\03_실험\ai-visibility-experiment\experiment.py' validate
```

MVP 실행:

```powershell
Set-Location '.\04_MVP\hanoon-mvp'
.\run.bat
```
