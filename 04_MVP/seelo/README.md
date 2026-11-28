# seelo 서비스 코드

현재 대상은 스마트스토어·카페24 상품 정비다. 쇼핑몰 API·데이터·설정·검증 범위는 [쇼핑몰 백엔드](backend/COMMERCE.md), 화면 실행과 시험은 [프런트엔드 안내](frontend/README.md)를 따른다. 남은 구현과 결정은 [운영 현황](../../01_기획/운영/운영현황.md)에서 추적한다.

| 폴더 | 내용 |
|---|---|
| `backend` | FastAPI·작업 워커. 쇼핑몰 코드는 `api/commerce.py`, `services/commerce_*.py`, `domain/commerce*.py`, `integrations/browser/commerce.py`, `worker/tasks_commerce.py`다. |
| `frontend` | 쇼핑몰 React 기본 폼과 메모리 시연 |
| `infra` | 운영 Compose·nginx·배포·백업 스크립트 |

계정·인증·작업 큐·배포는 지도 베타 때 만든 공통 기반이다. 지도 베타 기능 코드(가게 식별·진단·지도 정비·보고서: `api/stores.py`·`diagnosis.py`·`fix_*.py`·`reports.py` 등)는 코드에 남아 있다. 그 설계 문서는 [이전 기획 보관의 백엔드 구현계획](../../98_이전기획/01_기획/개발/백엔드_구현계획/00_읽는순서.md)에 있다. 아래 명령의 "17 1장" 같은 표기는 이 구현계획의 장 번호다.

## 처음 한 번

```bash
cp .env.example .env          # 비밀 값(SECRET_KEY, EMAIL_HMAC_KEY, MAIL_TOKEN_FERNET_KEY)을 새로 만든다
cd backend && uv sync
```

## Compose로 실행

```bash
docker compose up -d --build db migrate api web     # http://localhost:8080/api/health
docker compose --profile dev up -d mailpit           # 메일 확인 http://localhost:8025
docker compose up -d worker-main worker-ai-openai worker-ai-gemini   # 작업 실행(AI 준비·메일 등, AI 측정 공급자별)
docker compose --profile fix up -d worker-fix        # 쇼핑몰 관리자 화면 작업(commerce_browser 큐, Playwright)
docker compose exec api python scripts/seed_demo.py  # 인증 완료 시드 계정(비밀번호는 스크립트의 DEMO_PASSWORD)
docker compose exec api python scripts/send_test_mail.py --to someone@example.com   # 시험 메일 → Mailpit
```

- API 문서(개발): http://localhost:8080/api/docs. 가짜 모드에서 구글·카카오 로그인은 동의 화면 없이 데모 사용자로 돌아온다(17 1장).
- 관리자 지정: `docker compose exec api python scripts/create_admin.py --email <인증 마친 이메일>`
- (지도 베타 코드) 가짜 모드 가게 등록: 링크 `kko.to/x`·`naver.me/x`·`maps.app.goo.gl/x`는 데모식당으로 풀린다. 이름에 "후보"를 넣고 `naver.me/x`를 쓰면 후보 화면 흐름(17 1장).

## 로컬(Windows 포함)로 실행

```bash
docker compose up -d db
cd backend
uv run alembic upgrade head
uv run python scripts/init_queue_schema.py
uv run uvicorn seelo.main:app --reload --port 8000 --no-access-log   # 접근 로그는 앱이 쿼리 없이 남긴다
uv run python -m seelo.worker.run --queues collect,measure,plan,report,email,periodic,ai_openai,ai_gemini --concurrency 4
```

- Windows에서는 `fix,commerce_browser` 큐 워커(Playwright)를 Compose(`--profile fix`)나 WSL에서 띄운다(17 5장). 브라우저가 있는 로컬 PC에서만 확인할 때는 `COMMERCE_BROWSER_RUNNER=inline`을 쓸 수 있다.
- 쇼핑몰 담당자 로그인: `uv run --group browser python scripts/commerce_browser_login.py --platform cafe24 --external-id 몰아이디`. 준비 절차는 [관리자 화면 자동화](../../01_기획/개발/쇼핑몰_관리자화면자동화.md)를 따른다.

## 시연 데이터·API 계약

`seed_demo.py --scenarios`는 지도 베타 화면용 데이터다. 쇼핑몰 화면 시연은 프런트엔드의 메모리 시연(`npm run dev:demo`)을 쓴다.

```bash
docker compose exec -T api python scripts/seed_demo.py --scenarios
cd backend
uv run python scripts/export_openapi.py
uv run python scripts/export_openapi.py --check
```

- 카드별 시연 상태는 `FAKE_EXTERNALS=true`인 개발 환경에서 만든다. 계정 17개 중 15개에 상태를 추가하고, 빈 계정·관리자는 그대로 둔다. 반복 실행은 기존 가게를 건너뛰며 계정·비밀번호·무료 이력을 덮어쓰지 않는다. 기존 이력이 있으면 카드가 달라질 수 있다.
- 데이터만 만들며 외부 호출·작업 등록·메일 발송은 없다. 진행 중 카드도 정지 상태 예시여서 워커의 정체 작업 정리가 나중에 상태를 바꿀 수 있다.
- API 계약은 [`frontend/openapi.json`](frontend/openapi.json). 설정·DB·실제 키 없이 생성한다. `--check`는 파일 변경 없이 최신 여부를 검사하고 차이가 있으면 종료 코드 1을 돌려준다.
- 자세한 조건은 구현계획 17 2·4장, 확인 결과는 [후속 개발 보고서](../../98_이전기획/03_실험/구현시험/후속_시연데이터_API계약_20261029.md)에 있다.

## 테스트

```bash
cd backend
uv run pytest -q              # Docker가 켜져 있으면 postgres:16 컨테이너를 띄워 쓴다
uv run ruff check . && uv run ruff format --check .
```

- 테스트 DB 컨테이너는 고정 포트 55432에 뜬다(바꾸려면 `TEST_PG_PORT`).
- 이미 띄운 DB를 쓰려면 `TEST_DATABASE_URL=postgresql+psycopg://seelo:seelo@127.0.0.1:5432/seelo_test`(빈 DB).
- 실제 API 시험: `uv run pytest -m live`(지도 베타 시험은 키와 `tests/fixtures/links/test_stores.csv`, 추출 정확도는 `tests/fixtures/extract/gold.jsonl` 필요).

## 운영 준비

- 절차·미완료 체크: [`infra/OPERATIONS.md`](infra/OPERATIONS.md).
- 운영은 `docker-compose.prod.yml` 단독 구성이다. 개발 compose와 합치지 않는다. `infra/production.env.example`의 빈 값을 운영자가 채우고 실제 인증서를 연결해야 한다. 이 작업에서는 실제 배포하지 않았다.
- 운영 env의 `SEELO_BROWSER_WORKER=true`면 배포가 worker-fix를 빌드·기동한다. 운영 DB에는 쇼핑몰 마이그레이션 `0003`·`0004`를 백업 뒤 별도로 적용한다(운영 현황 U3).
- 공통 보안·배포 준비 기록: [`16단계`](../../03_실험/구현시험/단계16_보안배포준비_20261029.md). 지도 베타의 14·15단계 기록은 [이전 기획 보관](../../98_이전기획/03_실험/구현시험/)에 있다.
