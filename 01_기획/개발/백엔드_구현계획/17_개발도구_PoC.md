# 17. 개발 도구·가짜 연동·시드·PoC 절차·문제 해결

## 1. 가짜 외부 연동 모드(`FAKE_EXTERNALS=true`)

API 키 없이 가입부터 보고서까지 로컬에서 돌리기 위한 모드다. 화면 개발(나중 단계)과 시연 연습에도 쓴다. 운영에서는 켤 수 없다(13 1장 `_prod_guard`).

`seelo/integrations/fakes.py`의 `build_fake_clients()`가 11 3장의 테스트용 가짜와 **같은 클래스**를 쓰되, 아래처럼 입력에 따라 정해진 결과를 돌려준다.

| 연동 | 가짜 동작 |
|---|---|
| Places | `place_id`·검색어가 무엇이든 `tests/fixtures/google/demo_place.json`(가게 "데모식당", 서울 중구 명동, 좌표 37.5636/126.9850, `primaryType=korean_restaurant`, 영업시간·전화 있음, `servesVegetarianFood` 없음)을 돌려준다. 검색어에 `"후보"`가 들어 있으면 같은 이름 결과 2개(후보 흐름 시험) |
| 카카오·네이버 | 같은 가게 1건(좌표 40m 차이). 검색어에 `"없음"`이 들어 있으면 0건 |
| 짧은 링크 | 실제 요청 없이 `kko.to/x` → `https://place.map.kakao.com/1`, `naver.me/x` → `https://map.naver.com/p/entry/place/1`, `maps.app.goo.gl/x` → 데모 Google 긴 링크 |
| 웹사이트 | robots 허용, `tests/fixtures/website/demo_home.html`·`demo_menu.html` |
| OpenAI·Gemini `web_answer` | 질문마다 정해진 답변 3종을 `repeat_no`로 돌려 쓴다. 30%는 "데모식당"이 2위, 나머지는 주변 가게 5곳(고정 이름)만. 출처는 `tripadvisor.com`, `visitkorea.or.kr`, `google.com/maps` |
| OpenAI `structured` | 스키마 이름별 고정 결과(질문 3개, 추출은 답변에서 이름 목록을 정규식으로 뽑아 만듦, 정비안 글은 사실 id를 붙인 짧은 문장) |
| 메일 | 개발 compose의 Mailpit으로 실제 SMTP 발송(웹 UI `http://localhost:8025`) |
| 관리 화면(`map_admin`) | 메모리 안의 가짜 칸 값. 쓰면 바로 읽힘(`applied`). 환경변수 `FAKE_MAP_BEHAVIOR=block`이면 첫 칸에서 `AutomationBlocked`, `reflect_delay`면 `pending_reflection`. (10단계 구현) `integrations/fake_admin.py`의 `FakeMapAdmins`(지도별 `FakeMapAdmin`). `open_store`는 `fake-{provider}-{가게 id}`를 돌려준다. (13단계) `fail_write(칸, 사유)`(→ FieldWriteFailed), `before_write`(쓰기 직전 부르는 함수: 테스트가 before_value 커밋을 확인). 가짜 모드에서 자동 정비를 켜면 정비 워커가 이 가짜에 쓴다 |
| 인스타그램 | (7단계 구현) `FakeInstagram`: `demo_restaurant`만 BD 결과가 있고 나머지 이름은 Graph 오류(`graph_110`)처럼 실패. 부른 이름을 `calls`에. 플래그가 기본 꺼짐이라 가짜 모드에서도 호출 0번 |
| (4단계 구현 메모) | 지도 가짜는 `integrations/fake_maps.py`. 데모 데이터는 이미지에서도 쓰도록 `tests/fixtures/google/demo_place.json` 대신 그 파일 안에 둔다(5단계에서 상세 필드를 더함). "후보"는 **검색어**에 들어 있을 때 같은 이름 결과를 하나 더 붙인다. 카카오·네이버 기준 검색어는 사장님 입력 이름이므로, 시연은 `naver.me/x` 링크 + 이름 "데모식당 후보" |
| (5단계 구현 메모) | 웹사이트는 `fake_web.py`: 진짜 `HttpWebsiteFetcher`에 가짜 서버·가짜 DNS(모든 이름 → 공인 주소, `localhost`만 사설)를 붙여 robots·리디렉션·크기 규칙이 그대로 돈다. 데모 사이트 `https://demo-restaurant.example/`(메뉴·영문·인스타그램 링크). `FakeLlm.structured`는 `WebsiteExtractOut`이면 데모 정리 결과. 데모 Google 상세 필드(영업시간·전화·웹사이트·주소 구성요소 등)는 `fake_maps.py`의 `DEMO_GOOGLE`에 있다 |
| (8단계 구현 메모) | 데모 지도(`fake_maps.DEMO_NEIGHBORS`)에 주변 가게 "명동칼국수"(웹사이트·채식 참)·"을지면옥"을 넣어 주변 가게 사실 조회가 값을 돌려준다(나머지 3곳은 못 찾음). 데모 Google에는 채식 정보가 없어 진단 결과 고쳐야 할 점이 1개(`map_missing.attributes`) 나온다. AI 비교(`ClaimChecksOut`)는 기본 결과가 없다(데모 추출에 우리 가게 주장이 없어 부르지 않음). 테스트는 `results`로 정한다 |
| (11단계 구현 메모) | `FakeLlm.structured`가 `PlanTextsOut`이면 `demo_plan_texts(prompt)`: 프롬프트의 사실 줄(`f3 [region] 명동`)만 써서 소개 2문장(영어·한국어, 지역·업종 사실 id), 카카오 소개, 메뉴 영문명(메뉴 사실 순서대로 "House dish A/B…"), 태그를 만든다(사실 검사를 그대로 통과). 테스트는 `results["PlanTextsOut"]`·`fail_next(n, ..., only="PlanTextsOut")`로 바꾼다. 데모 진단의 고쳐야 할 점이 `map_missing.attributes` 1개라 Compose 수동 모드 Google 정비안은 편의 칸 1개(확인 필요)다 |
| (7단계 구현 메모) | `FakeLlm.structured`: `ExtractionOut`이면 프롬프트 답변의 `1. 이름 - …[n]` 줄을 추천으로(`demo_extraction`), `WebEvidenceExtractOut`이면 `SITE url \| 사이트 \| 이름 \| 주소 \| 전화 \| 영업시간 \| 인스타그램` 줄을 사이트로. `web_answer`는 AI 웹 검색 프롬프트(`Find publicly available information…`)면 그 `SITE` 줄 3개(셋째는 다른 가게라 거르기에서 빠짐)를 답한다. 가짜 모드에서 수집 → 측정 → 추출 → 마무리가 끝까지 돈다 |
| (6단계 구현 메모) | `FakeLlm.web_answer`: 같은 질문의 n번째 호출이 `n % 10 ∈ {0,3,6}`이면 데모식당이 2위(30%), 출처 tripadvisor·visitkorea·google maps. `FakeLlm.structured`는 `GeneratedQuestionsOut`이면 프롬프트를 읽어 규칙을 지키는 질문 3개(`demo_questions`). 가짜 모드에서 측정 60개 호출이 약 1초 |
| 구글·카카오 로그인(`FakeOAuth`) | 동의 화면 없이 바로 콜백(`code=demo-{provider}`)으로 돌아온다. 구글은 `google-demo@seelo.test`(인증된 이메일) → 약관 동의 화면, 카카오는 이메일 없음 → S04 이메일 입력 흐름. state 확인은 진짜로 돈다 |

- 가짜 모드에서도 DB·작업 큐·상태 전이·권한은 진짜로 돈다. 그래서 가짜 모드 흐름 테스트(11 5.1)가 곧 통합 점검이다.
- 가짜 모드의 AI 비용은 0으로 기록한다.

## 2. 시드 데이터(`scripts/seed_demo.py`)

구현 메모(2026-10-29, 후속 개발)
- 기본 실행은 계정만 만든다. 카드까지 준비하려면 `FAKE_EXTERNALS=true`인 개발 환경에서 `python scripts/seed_demo.py --scenarios`를 쓴다. 기존 DB를 비우지 않는다. 아래 `--reset`은 초기 구상이며 이번 검증에서는 쓰지 않았다.
- 실제 카드 데이터 팩토리는 배포 이미지에서도 쓸 수 있게 `scripts/demo_scenarios.py`에 뒀다. 서비스 상태 전이 대신 새 행의 시작 상태만 지정하며 외부 호출·작업 등록·메일 발송은 하지 않는다.
- 기존 가게가 하나라도 있는 계정은 건너뛴다. 역할·비밀번호·이메일 로그인 방식이 다른 계정도 보호한다. 기존 계정·가게·무료 사용 이력을 바꾸지 않으므로, 이미 사용한 계정의 카드는 아래 표와 다를 수 있다.
- 사용자 행 잠금으로 카드 생성을 직렬화하고, 계정 생성은 이메일 충돌 시 건너뛴다. 반복·동시 실행에 새 가게가 중복 생성되지 않는다. 운영 환경·실제 외부 연동 모드의 카드 생성은 거부한다.
- 새 DB 기준 계정 17개, 카드 상태가 있는 계정 15개다. `changed`에는 이전 가게 이력도 생긴다. 시연 보고서는 고정 ID의 fixture를 복사하지 않고 실제 보고서 계산 함수로 현재 ID를 넣어 만든다. 등장률 30%→50%는 시연용 합성 값이다.
- 진행 중 카드도 작업을 등록하지 않는 정지 상태 예시다. 워커를 계속 켜 두면 정체 작업 정리 같은 주기 작업이 나중에 상태를 바꿀 수 있다. 버튼 이후의 정상 흐름 시험은 별도 인수 시험을 쓴다(11 5장).

- `python scripts/seed_demo.py --reset`: 서비스 테이블을 비우고(`APP_ENV`가 `prod`면 거부) 아래 계정을 만든다. **비밀번호는 이 스크립트 안의 상수 `DEMO_PASSWORD`에만 둔다**(문서·채팅에 적지 않는다). 모든 계정은 인증 완료·약관 동의 상태.

| 이메일 | 역할 | 상태(S07 카드) |
|---|---|---|
| `admin@seelo.test` | admin | — |
| `nostore@seelo.test` | owner | `no_store` |
| `measuring@seelo.test` | owner | `measuring`(측정 running, 23/60) |
| `failed@seelo.test` | owner | `measure_failed` |
| `diagnosed@seelo.test` | owner | `diagnosed`(지표·주변 가게·고쳐야 할 점 5개) |
| `changed@seelo.test` | owner | `free_used_store_changed` |
| `requested@seelo.test` | owner | `fix_requested` |
| `rejected@seelo.test` | owner | `fix_rejected` |
| `connect@seelo.test` | owner | `connect_needed` |
| `preparing@seelo.test` | owner | `plan_preparing` |
| `approve@seelo.test` | owner | `plan_needs_approval`(확인 필요 칸 1개, 민감 칸 1개 포함) |
| `fixing@seelo.test` | owner | `fixing`(수동 처리 칸 1개) |
| `waiting@seelo.test` | owner | `remeasure_waiting` |
| `remeasuring@seelo.test` | owner | `remeasuring` |
| `refailed@seelo.test` | owner | `remeasure_failed` |
| `report@seelo.test` | owner | `report_ready`(보고서 content는 `tests/fixtures/report/case_1.json`의 기대값) |
| `revoked@seelo.test` | owner | `fixing` + Google `revoked` |

- 시드는 서비스 함수를 거치지 않고 팩토리(`tests/factories.py`)로 직접 행을 만든다. 작업은 등록하지 않는다(상태만 재현).
- 이메일 도메인 `.test`는 실제로 메일이 가지 않는 예약 도메인이다.

## 3. PoC 절차(개발 할 일의 사전 확인 + 이 문서의 `[PoC]`)

결과는 모두 `03_실험/구현시험/PoC_<이름>_<YYYYMMDD>.md`에 남기고, 바뀐 값은 표의 "고칠 곳"에 반영한다.

| PoC | 하는 일 | 기록할 것 | 고칠 곳 |
|---|---|---|---|
| 링크 형식 | 테스트 가게 20곳 × 3사 × (앱 공유·웹 공유) 링크 복사, 짧은 링크는 `curl -sI`로 `Location`만 확인 | 링크 원문, 최종 긴 링크, 가게 번호·이름·좌표 위치 | `tests/fixtures/links/links.csv`, 07 2.2 표 |
| 네이버 이름 검색 정확도 | 20곳 이름으로 HUB 지역 검색 `display=5` | 정답이 1위·5위 안·없음 | 07 3.2 네이버 규칙, D-11 |
| 네이버 좌표 형식 | 같은 응답의 `mapx`·`mapy` 원문 | 정수(×10⁷)인지 실수인지 | 07 4.3 `parse_naver_coord` |
| 업종 목록 | 20곳 + 비대상 5곳의 Google `types`·카카오 `category_name`·네이버 `category` | 원문 목록 | `config/categories.json`, D-11 |
| 이름 유사도 기준 | 20곳의 세 지도 이름 쌍과 주변 다른 가게 이름 쌍으로 `name_similarity` 분포 | 같은 가게 최솟값, 다른 가게 최댓값 | `NAME_SIMILARITY_THRESHOLD`, D-11 |
| 지역 추출 | 20곳 Google `addressComponents`(ko·en) | 동·구가 어느 `types`에 오는지 | 07 6.6 |
| 카카오 이메일 | 카카오 로그인 앱에서 이메일 동의 항목 설정 가능 범위 | 필수 동의 가능 여부(비즈 앱 필요?) | 05 5장 |
| 인스타그램 BD | seelo 비즈니스 계정 토큰으로 BD 1회 호출 | 심사 없이 되는지, 오류 원문 | `INSTAGRAM_*`, W-03-5 |
| Google 관리 화면 | 지인 가게에서 관리자 초대 → `scripts/browser_login.py`로 로그인 → `scripts/capture_admin_html.py`로 목록·정보·편집 화면 저장 | 로그인 차단 여부, 칸별 편집 가능 여부, 저장 뒤 화면 표시(검토 중 등), 반영 시간 | `selectors/google.yaml`, `field_dictionary.json`, D-13·D-17 |
| 카카오 파트너센터 | 같은 방식(운영자 초대) | 같음 + 칸별 글자 수·선택지·개수 | `selectors/kakao.yaml`, `field_dictionary.json` |
| 카카오 고객센터 | 외부 운영자·자동화 허용 문의 | 답변 원문 | `KAKAO_FIX_ENABLED` |
| GBP API | 사용 신청 → 승인 뒤 `GBP_VALIDATE_ONLY=true`로 칸별 PATCH 검증 | 칸별 지원 여부, 속성 이름 목록, 메뉴 API 여부 | 16 5장 `api` 값, D-14 |
| 반영 시간 | 지인 가게에서 영업시간·소개 1번씩 수정 | 관리 화면 표시 시각, 지도 공개 반영 시각 | D-15 확인, 09 10장 |
| Gemini 인용 위치 | 한국어 답변 10개에서 `segment.text`와 `end_index` 비교 | 문자·바이트 단위 | 08 2.3(지금은 `segment.text`로 찾음) |

### 3.1 관리 화면 저장 도구(`scripts/capture_admin_html.py`)

- `--provider google|kakao --name <화면이름>`: 영구 프로필로 **화면이 보이는** 브라우저를 열고, 관리자가 원하는 화면까지 직접 이동한 뒤 터미널에서 Enter를 누르면 `page.content()`를 `tests/fixtures/browser/{provider}/{name}.html`로 저장한다.
- 저장 전에 가림: 이메일(`EMAIL_RE`), 전화번호(`0\d{1,2}-?\d{3,4}-?\d{4}`), 사업자등록번호(`\d{3}-\d{2}-\d{5}`)를 `***`로 바꾼다. 가게 이름·주소는 테스트에 필요하므로 남기되, 저장소를 공개하지 않는다.
- 꼭 저장할 화면: 가게 목록, 정보 화면, 칸별 편집 화면(열린 상태), 저장 직후 화면, 로그인 화면, 보안 확인(나오면), "인증 필요" 표시가 있는 가게(있으면).

### 3.2 live 시험 기록 형식

```text
# W-04-2 live 시험 — 2026-11-05
- 가게: 5곳(테스트 가게 세트 3, 7, 11, 14, 19)
- 모델: openai=<id>, gemini=<id>
- 결과: 호출 300번 중 성공 291, 실패 9(timeout 6, rate_limited 3), 중복 0
- 시간: 측정 1건 평균 9분 40초(최대 13분 2초)
- 비용: 측정 1건 평균 $0.00 (openai $0.00, gemini $0.00)
- 원문 저장: 291/291
- 이상한 점: (있으면)
```

## 4. 화면(프론트)과의 계약 넘기기

구현 메모(2026-10-29, 후속 개발)
- `backend`에서 `uv run python scripts/export_openapi.py`로 생성한다. 실제 API 라우터를 쓰며 설정 파일·DB·작업 큐·실제 키 없이 실행된다.
- 결과는 `frontend/openapi.json`. 키 정렬·들여쓰기·줄 끝을 고정해 같은 계약은 같은 파일이 되고, 변경이 없으면 파일을 다시 쓰지 않는다.
- `uv run python scripts/export_openapi.py --check`는 파일을 바꾸지 않고 최신 여부만 검사한다. 누락·차이가 있으면 종료 코드 1이다. `--05_발표자료/내보내기 <경로>`로 별도 위치도 지정한다.
- `tests/unit/test_export_openapi.py`가 실제 앱의 OpenAPI·참조 연결·저장된 계약의 일치 여부를 검사한다. API 변경 시 다시 생성한다. React 구현·TypeScript 타입 생성은 이번 작업에서 하지 않았다.

- `uv run python scripts/export_openapi.py` → `frontend/openapi.json`. 화면 쪽은 `npx openapi-typescript frontend/openapi.json -o frontend/src/api/schema.d.ts`로 타입을 만든다.
- API를 바꾸면 이 파일을 다시 만들어 커밋한다(커밋 메시지에 "API 변경"을 적는다).
- 화면 개발자는 `FAKE_EXTERNALS=true` + 시드 계정으로 모든 카드·화면을 띄울 수 있다.

## 5. 막혔을 때

| 증상 | 원인 | 해결 |
|---|---|---|
| Windows에서 `psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'` | psycopg 비동기는 Windows 기본 이벤트 루프(Proactor)를 못 쓴다 | `seelo/__init__.py` 맨 위: `if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` |
| 위를 넣은 뒤 Windows에서 Playwright가 `NotImplementedError`(subprocess) | Playwright는 Windows에서 Proactor 루프가 필요하다 | Windows에서는 `fix` 큐 워커를 Docker(리눅스)나 WSL에서 띄운다. 다른 프로세스는 Windows에서 그대로 실행 |
| 화면에서 모든 POST가 403 `CSRF_FAILED` | 화면(5173)과 API(8000)가 다른 출처라 쿠키가 안 붙음 | Vite 개발 서버 프록시로 `/api`를 8000에 넘겨 같은 출처로 만든다. `fetch`에 `credentials: "include"`, 헤더 `X-CSRF-Token`에 `seelo_csrf` 쿠키 값 |
| 작업이 등록됐는데 실행되지 않음 | 등록한 트랜잭션을 커밋하지 않음(NOTIFY는 커밋 때) / 워커가 그 큐를 안 들음 | `session.commit()` 확인, 워커 `--queues` 확인 |
| `procrastinate_jobs` 없음 | 큐 스키마 미적용 | `python scripts/init_queue_schema.py` |
| `ConnectorException` | 테스트 인메모리 커넥터에 `connection=`을 넘김 | `jobs.defer`의 커넥터 종류 분기 확인(06 3장) |
| `InvalidRequestError: A transaction is already begun` | `session.begin()`을 씀 | 쓰지 않는다. 명시적 `commit()`(01 7.2) |
| `MissingGreenlet`·지연 로딩 오류 | 비동기 세션에서 관계를 그냥 읽음, 또는 `rollback()`(`expire_on_commit=False`여도 롤백은 객체를 만료시킴) 뒤 `obj.id` 같은 속성을 읽음 | `selectinload`로 미리 읽기, `lazy="raise"` 유지. 롤백할 수 있는 흐름에서는 필요한 ID를 먼저 지역 변수로 꺼내 둔다 |
| 같은 `queueing_lock` 중복 등록 뒤 `InFailedSqlTransaction` | `jobs.defer`가 연결을 `begin_nested()` 블록 밖에서 꺼내 SAVEPOINT가 나가지 않음 | 연결은 블록 안에서 꺼낸다(06 3장) |
| 테스트에서 워커·작업 등록이 엉뚱한 DB를 봄 | Procrastinate 앱은 import될 때 DSN을 읽는데 테스트 DB 포트가 나중에 정해짐 | 테스트 DB 포트를 고정하고 환경변수를 conftest 맨 위에서 정한다(11 2장) |
| 로그에 `email_log_id: [REDACTED]` | 키 이름에 `email`이 들어가 가림 | `_id`로 끝나는 정수 키는 가리지 않는다(13 5장) |
| `@seelo.test`로 가입·로그인하면 422 `invalid_email` | email-validator가 예약 도메인 `.test`를 거부 | `create_app`이 `APP_ENV`가 prod가 아니면 `.test`만 허용(`allow_test_email_domain`). 운영은 그대로 거부 |
| 시간 이동 테스트에서 만료 세션이 그대로 남음 | httpx 쿠키 저장소가 `Max-Age` 지난 쿠키를 보내지 않아 서버까지 안 감 | `raw_request`로 쿠키를 직접 싣는다(11 2장) |
| 워커 실행 테스트에 `cleanupUnverified` 작업이 끼어듦 | 워커가 시각에 따라 주기 작업을 등록(매시 5분 뒤 10분 안) | 테스트는 관심 있는 작업 이름만 본다 |
| 요청 제한 테스트가 가끔 6번째도 통과 | 5번 요청이 분 경계를 넘어 창이 나뉨 | 창을 앱 시계로 정하고 `frozen_time`(05 10장) |
| 테스트·로컬 실행이 DB 연결에서 멈춤(풀 `error connecting`, 메시지 없음) | Windows에서 `localhost`가 `::1`(IPv6)로 먼저 풀리면 Docker 포트 연결이 응답 없이 멈출 때가 있다(2026-10-27 Docker Desktop 재시작 뒤) | DB 주소는 `127.0.0.1`로 쓴다(테스트 conftest, `.env.example`) |
| 테스트 시작 때 testcontainers `500 … /start` | 앞 실행의 준비 단계가 실패해 컨테이너가 고정 포트(55432)를 잡고 남음 | `docker rm -f <이름>`. conftest는 준비 실패에도 컨테이너를 지우게 고침 |
| 서비스 모듈의 쿼리가 이상하게 실패 | 서비스 함수 이름이 `select`라 SQLAlchemy `select`를 가림 | 함수 이름을 바꾼다(`select_candidate`) |
| 링크 CSV 테스트에서 Google 링크가 잘림 | Google 링크의 `@37.5,126.9,17z` 쉼표 | CSV 값은 따옴표로 감싼다 |
| `ImportError: Modest backend is deprecated` | selectolax 1.0부터 `selectolax.parser`(Modest) 사용 불가 | `from selectolax.lexbor import LexborHTMLParser` |
| api 컨테이너를 다시 만든 뒤 nginx가 502 | nginx가 `api` 주소를 시작 때 한 번만 풀어 옛 IP로 보냄 | `resolver 127.0.0.11` + 변수 `proxy_pass`(01 5장). 급하면 `docker compose restart web` |
| 테스트에서 주기 작업이 등록 안 됨 | 작업 모듈(`seelo.worker.periodic`)을 import하지 않음(워커는 시작 때 `import_paths`로 불러옴) | 테스트에서 모듈을 직접 import |
| 가게 요약 주소가 늘 카카오 값 | Google 스냅샷 payload는 `{"ko": …}`인데 `payload.formattedAddress`를 읽음 | `payload.ko.formattedAddress`(14 3장 `summary`) |
| `~text("EXISTS …")`에서 `AssertionError`(메시지 없음) | SQLAlchemy `TextClause`는 부정(`~`)을 지원하지 않음 | `text("NOT EXISTS …")`로 쓴다 |
| "returned no FROM clauses due to auto-correlation" | 바깥과 같은 테이블을 하위 질의에서 다시 씀 | `aliased(...)` + `.correlate(...)`(진행률 쿼리) |
| 테스트에서 `updated_at`을 과거로 바꿔도 그대로 | `set_updated_at` 트리거가 UPDATE마다 `now()`로 덮음 | 그 문장에서만 `SET LOCAL session_replication_role = replica`(테스트 전용, 11 2장) |
| `TypeError: 'MappedColumn' object is not callable` | 모델 도우미 함수 이름이 컬럼 이름과 같음(`created_at = created_at()`) | 도우미는 `created_col()`처럼 다른 이름(13 10장) |
| OpenAI 구조화 출력 스키마 오류 | 기본값·자유 딕셔너리 필드 | 08 0.4 규칙대로 모델 수정 |
| Places 400 `INVALID_ARGUMENT` | 필드 마스크에 공백, Text Search 마스크에 `places.` 없음 | 07 4.1 상수 확인 |
| NAVER 401 | 옛 주소(`openapi.naver.com`)에 HUB 키 | `NAVER_LOCAL_SEARCH_URL`을 HUB 주소로 |
| 카카오 토큰 요청이 클라이언트 인증 오류로 실패 | 클라이언트 시크릿 누락(REST API 키는 기본으로 시크릿 사용) | `KAKAO_OAUTH_CLIENT_SECRET` 설정(05 5.1) |
| 수집 테스트에서 `fail_next`가 엉뚱한 호출을 실패시킴 | 수집은 웹사이트 정리와 AI 웹 검색이 같은 가짜 LLM을 동시에 부름 | `fail_next(n, 사유, only="WebsiteExtractOut")`처럼 호출을 지정(11 2장) |
| 추출 프롬프트에 카카오 이름이 "들어 있다"고 테스트가 실패 | 프롬프트에는 AI 답변 원문도 들어가므로 답변에 나온 이름은 당연히 있음 | 이름 후보 줄(`target places:`)만 검사한다 |
| 관리 화면 작업이 매번 `login_required` | 프로필 로그인이 풀림 | `scripts/browser_login.py`로 다시 로그인. 반복되면 PoC 기록에 남기고 수동 처리로 운영 |
