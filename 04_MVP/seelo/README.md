# seelo 베타

- 구현계획: [`01_기획/백엔드_구현계획/`](../../01_기획/백엔드_구현계획/00_읽는순서.md) — 이 폴더의 코드는 그 문서를 따른다.
- 진행: 백엔드 0~16단계의 코드·로컬 검증과 후속 운영 구성을 구현했다. GCP의 실제 도메인 HTTPS·지도 검색·Google/카카오 인증 콜백, 서버→PC Codex CLI 웹 검색, 정기 백업·PC 외부 보관·별도 DB 복구를 확인했다. 승인한 시험 메일 10종은 SMTP 수락까지 확인했으며 받은편지함 수신은 미확인이다. 최신 작업은 선택 회귀 504개와 OAuth/웹훅 보완 26개, 마지막 보고서 비교 조건 회귀 33개가 통과했다. Gemini CLI 인증은 Google에서 차단돼 전체 두 공급자 진단은 미완료이며, 카카오 웹훅 등록·최종 가입 UI·실제 가게 인수·알림 수신이 남았다. 자동 지도 정비는 계속 꺼져 있다. React 화면은 이번 작업 범위 밖이다. [최신 작업 기록](../../03_실험/구현시험/로컬CLI_AI_연동진행_20261031.md)을 따른다.

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

## 시연 데이터·API 계약

```bash
docker compose exec -T api python scripts/seed_demo.py --scenarios
cd backend
uv run python scripts/export_openapi.py
uv run python scripts/export_openapi.py --check
```

- 카드별 시연 상태는 `FAKE_EXTERNALS=true`인 개발 환경에서 만든다. 계정 17개 중 15개에 상태를 추가하고, 빈 계정·관리자는 그대로 둔다. 반복 실행은 기존 가게를 건너뛰며 계정·비밀번호·무료 이력을 덮어쓰지 않는다. 기존 이력이 있으면 카드가 달라질 수 있다.
- 데이터만 만들며 외부 호출·작업 등록·메일 발송은 없다. 진행 중 카드도 정지 상태 예시여서 워커의 정체 작업 정리가 나중에 상태를 바꿀 수 있다.
- API 계약은 [`frontend/openapi.json`](frontend/openapi.json). 설정·DB·실제 키 없이 생성한다. `--check`는 파일 변경 없이 최신 여부를 검사하고 차이가 있으면 종료 코드 1을 돌려준다.
- 자세한 조건은 구현계획 17 2·4장, 확인 결과는 [후속 개발 보고서](../../03_실험/구현시험/후속_시연데이터_API계약_20261029.md)에 있다.

## 테스트

```bash
cd backend
uv run pytest -q              # Docker가 켜져 있으면 postgres:16 컨테이너를 띄워 쓴다
uv run ruff check . && uv run ruff format --check .
```

- 테스트 DB 컨테이너는 고정 포트 55432에 뜬다(바꾸려면 `TEST_PG_PORT`).
- 이미 띄운 DB를 쓰려면 `TEST_DATABASE_URL=postgresql+psycopg://seelo:seelo@127.0.0.1:5432/seelo_test`(빈 DB).
- 실제 API 시험: `uv run pytest -m live`(키와 `tests/fixtures/links/test_stores.csv`, 추출 정확도는 `tests/fixtures/extract/gold.jsonl` 필요).

## 운영 준비(16단계)

- 절차·미완료 체크: [`infra/OPERATIONS.md`](infra/OPERATIONS.md).
- 운영은 `docker-compose.prod.yml` 단독 구성이다. 개발 compose와 합치지 않는다. `infra/production.env.example`의 빈 값을 운영자가 채우고 실제 인증서를 연결해야 한다. 이 작업에서는 실제 배포하지 않았다.
- 단계 보고: [`14단계`](../../03_실험/구현시험/단계14_재측정보고서_20261029.md), [`15단계`](../../03_실험/구현시험/단계15_알림마무리_20261029.md), [`16단계`](../../03_실험/구현시험/단계16_보안배포준비_20261029.md).
