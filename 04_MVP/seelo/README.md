# seelo 베타

- 구현계획: [`01_기획/백엔드_구현계획/`](../../01_기획/백엔드_구현계획/00_읽는순서.md) — 이 폴더의 코드는 그 문서를 따른다.
- 진행: 0~12단계(뼈대·DB·공통 기반·계정·가게 찾기·정보 수집·질문·AI 호출·추출·지표·AI 웹 검색·인스타그램·고쳐야 할 점·무료 진단·홈 카드·정비 신청·관리자 승인·지도 연결·정비안·승인·수동 처리·정비 완료·재측정 예약·자동 정비) 완료. M1(가짜 연동) 통과, M2는 가짜 연동으로 흐름 확인(지인 가게 실제 시연 전). 자동 정비는 관리 화면 셀렉터(PoC) 전이라 켜도 수동 처리로 넘어간다. 다음은 14단계(재측정·보고서, 12_작업순서.md). 화면(React)은 백엔드 16단계 뒤에 만든다.

## 처음 한 번

```bash
cp .env.example .env          # 비밀 값(SECRET_KEY, EMAIL_HMAC_KEY, MAIL_TOKEN_FERNET_KEY)을 새로 만든다
cd backend && uv sync
```

## Compose로 실행

```bash
docker compose up -d --build db migrate api web     # http://localhost:8080/api/health
docker compose --profile dev up -d mailpit           # 메일 확인 http://localhost:8025
docker compose up -d worker-main worker-ai-openai worker-ai-gemini   # 작업 실행(수집·질문·메일, AI 호출 공급자별)
docker compose exec api python scripts/seed_demo.py  # 시드 계정(비밀번호는 스크립트의 DEMO_PASSWORD)
docker compose exec api python scripts/send_test_mail.py --to someone@example.com   # 시험 메일 → Mailpit
```

- API 문서(개발): http://localhost:8080/api/docs. 가짜 모드에서 구글·카카오 로그인은 동의 화면 없이 데모 사용자로 돌아온다(17 1장).
- 관리자 지정: `docker compose exec api python scripts/create_admin.py --email <인증 마친 이메일>`
- 가짜 모드 가게 등록: 링크 `kko.to/x`·`naver.me/x`·`maps.app.goo.gl/x`는 데모식당으로 풀린다. 이름에 "후보"를 넣고 `naver.me/x`를 쓰면 후보 화면 흐름(17 1장).

## 로컬(Windows 포함)로 실행

```bash
docker compose up -d db
cd backend
uv run alembic upgrade head
uv run python scripts/init_queue_schema.py
uv run uvicorn seelo.main:app --reload --port 8000 --no-access-log   # 접근 로그는 앱이 쿼리 없이 남긴다
uv run python -m seelo.worker.run --queues collect,measure,plan,report,email,periodic,ai_openai,ai_gemini --concurrency 4
```

- Windows에서는 `fix` 큐 워커(Playwright)를 Compose(`--profile fix`)나 WSL에서 띄운다(17 5장).

## 테스트

```bash
cd backend
uv run pytest -q              # Docker가 켜져 있으면 postgres:16 컨테이너를 띄워 쓴다
uv run ruff check . && uv run ruff format --check .
```

- 테스트 DB 컨테이너는 고정 포트 55432에 뜬다(바꾸려면 `TEST_PG_PORT`).
- 이미 띄운 DB를 쓰려면 `TEST_DATABASE_URL=postgresql+psycopg://seelo:seelo@127.0.0.1:5432/seelo_test`(빈 DB).
- 실제 API 시험: `uv run pytest -m live`(키와 `tests/fixtures/links/test_stores.csv`, 추출 정확도는 `tests/fixtures/extract/gold.jsonl` 필요).
