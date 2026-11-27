# 쇼핑몰 백엔드

2026-11-27 파일럿 설정. 실제 쓰기는 `COMMERCE_WRITES_ENABLED=true`일 때만 허용한다. `COMMERCE_WRITE_TARGETS={"12":["12345"]}`처럼 seelo 스토어 번호와 플랫폼 원상품번호를 설정하면 해당 상품의 저장·복구만 허용한다. 빈 객체에서는 전체 쓰기 설정을 따른다.

Compose의 API·AI 작업 워커·브라우저 워커는 `/data/commerce-config`를 같은 읽기 전용 볼륨으로 읽는다. 운영자가 외부 설정을 배치할 경우 `COMMERCE_BROWSER_CONFIG_HOST_DIR`에 절대 경로를 지정한다. `<플랫폼>/<몰 ID>/<쇼핑몰 번호>.yaml`은 스토어의 전체 설정이고, 파일이 없으면 `<플랫폼>.yaml`, 그다음 코드에 포함된 기본 설정을 사용한다. 로그인 세션은 별도 브라우저 볼륨에 보관한다.

기준: 2026-11-19. 대상은 스마트스토어·카페24다. 기존 지도 베타의 테이블과 API는 유지한다.

**2026-11-24 변경:** 기본 수정 경로는 위임받은 관리자 화면의 브라우저 자동화다. `COMMERCE_EDIT_MODE=browser`에서 관리자 권한 확인 후 수집·저장·재조회·복구를 수행한다. API 토큰은 요구하지 않는다. `snapshotSource=browser`, 변경 `method=browser`를 사용하며 API 인증 상태는 올리지 않는다. 기존 API 경로는 `COMMERCE_EDIT_MODE=api`로 선택한다. 실제 화면 설정·실계정 검증 상태는 [관리자 화면 자동화](../../../01_기획/개발/쇼핑몰_관리자화면자동화.md)를 따른다.

기능 기준은 [쇼핑몰 진행 지침](../../../02_조사/쇼핑몰_타깃플랫폼과_수정수행방식_20261117.md)이다.

**2026-11-25 변경:** 남은 구현 진행 상태는 [운영현황](../../../01_기획/운영/운영현황.md)의 C-01~C-11에서 추적한다. 이 문서는 동작과 실행 방법만 적는다.

| 항목 | 동작 |
|---|---|
| 지원 필드 | 스토어·상품 응답의 `fieldSupport`가 현재 편집 모드·실행기 설정의 자동·수동·미지원 필드를 알려 준다. 미지원 필드는 정비안 생성·승인·저장 전에 `field_not_supported`로 거부한다. 브라우저 모드의 카페24 모바일 설명은 화면 설정에 입력 칸이 없어 미지원이다. |
| 브라우저 실행 위치 | `COMMERCE_BROWSER_RUNNER=worker`(기본)이면 API는 `commerce_jobs`에 작업만 등록하고 202를 돌려준다. worker-fix가 `commerce_browser` 큐에서 실행한다. 같은 몰 프로필은 lock으로 하나씩 연다. 같은 상품 수집·같은 정비안 작업은 중복 등록을 막는다. 자동 재시도는 없다. `inline`은 브라우저가 있는 로컬 PC 검증 전용이다. |
| 로그인 만료·중단 | `login_required`·`captcha`·`security_check`는 스토어의 `browserSession`에 남긴다. 오래 실행 중인 작업은 `stalled`로 정리하고 새 작업을 받는다. 결과가 불명확한 저장은 `uncertain`으로 두고 재조회 작업만 받는다. |
| 서버 세션 이전 | 담당자는 PC에서 `scripts/commerce_browser_login.py`로 로그인한 뒤 `scripts/commerce_browser_session.py export`로 내보내고, 서버 worker에서 `import`한다. 플랫폼 도메인 쿠키만 옮기고 값은 출력하지 않는다. 평문 파일은 가져온 뒤 지운다. |
| 고객·운영자 역할 | 승인은 스토어 소유자만 한다. 운영자는 `approvedBy`가 소유자인 정비안만 저장·복구한다. `/operator/shops`·`/operator/tasks`는 관리자 전용 조회다. |
| 위임 스토어 식별 | 운영자가 위임 확인 때 `storeName`·`storeId`를 기록한다. 실행기는 화면 값과 정확히 대조한다. 설정한 경우에만 위임 목록에서 정확히 같은 1곳으로 전환하고, 0곳·2곳 이상이면 멈춘다. 카페24는 최종 화면 주소의 쇼핑몰 번호도 대조한다. |
| 플랫폼 상품 목록 | `POST/GET /shops/{id}/catalog`. 몰별 설정의 `catalog`가 있어야 한다. 기본 설정에는 실제 화면 확인 전이라 넣지 않았다. |
| AI 기본 흐름 | 수집이 끝나면 `prepare` 작업이 자료 조사(본문 속 공개 링크 포함) → 필요한 사실 판단 → 정비안 생성을 이어 간다. 확인하지 못한 필수 사실만 묻는다. 식품 사실 키(원재료·영양성분·섭취·알레르기·원산지·보관·제조원)를 추가했다. 함량·섭취량은 숫자+단위가 출처 인용문에 있어야 저장한다. 효능·인증·후기 키는 없다. 웹 검색 자료 발견은 `COMMERCE_WEB_DISCOVERY=true`일 때만 쓴다. |
| AI 노출 진단 | 고정 질문 세트(질문에 대상 상품명·URL 금지) → 회차 측정(공급자별 AI 큐) → 원문·출처·발견·추천 순위·링크 인용 저장 → 같은 세트·조건끼리 비교. 호출 실패는 1회만 다시 실행하고 무효로 남긴다. 측정 당시 원본 해시와 마지막 반영 정비안을 함께 저장한다. 14일 재측정·가격 정책은 적용하지 않는다. |

## 구현 범위

| 항목 | 구현 내용 |
|---|---|
| 계정 | 기존 이메일·Google·카카오 로그인, 세션, 약관, CSRF를 재사용한다. |
| 스토어 | 두 플랫폼만 등록한다. 등록·관리자 초대·API 인증을 별도 상태로 관리한다. |
| 상품 | API 원본과 판매자가 제공한 원본을 구분한다. 상품번호·쇼핑몰·모델 식별·수집 시각·원본 해시를 저장한다. |
| AI 조사 | 사실 목록이 없으면 정비안 생성 전에 기존 상품 본문을 먼저 읽는다. 지정한 제조사 자료도 조사할 수 있다. robots·공인 주소 검사와 크기·시간 제한을 적용한다. |
| 근거 | 동일 상품 식별값, 인용문 속 실제 값, 출처를 검사한다. AI가 만든 인용문이 원문에 없으면 거부한다. 자료가 충돌하면 새 값을 임의 채택하지 않는다. |
| 정비안 | 원래 본문·이미지를 보존하고 확인한 사실을 추가한다. 충분한 기존 요약·SEO는 유지한다. 없는 사양을 생성하지 않는다. |
| 질문·보류 | 한 번에 미해결 사실 두 개 이내만 묻는다. 필요한 사실이 없으면 해당 새 변경을 보류한다. 준비된 나머지는 승인할 수 있다. |
| 승인 | 원본 해시와 정비안 ID를 검사한다. `fields`로 승인할 필드만 선택할 수 있다. 승인 목록은 저장·복구·작업 지침에 그대로 적용한다. |
| 저장 | 전송 전에 이력을 저장한다. 변경된 원본과 중복 승인을 차단한다. 가격·재고·옵션·배송·판매 상태는 정비 대상에서 제외한다. |
| 검증 | 저장 응답·관리 API 재조회·PC/모바일 공개 확인을 구분한다. 공개 확인은 관리자 관찰 기록이다. API 재조회 성공을 공개 확인으로 표시하지 않는다. |
| 복구 | 별도 요청으로 승인 범위의 수정 전 값만 복구한다. 판매자가 그 뒤 바꾼 값은 덮어쓰지 않는다. |
| 불명확한 결과 | `uncertain`, `pending_reflection`, `applying`은 재조회한다. 같은 쓰기를 자동 재전송하지 않는다. |
| 개인정보 | 토큰은 기존 Fernet 보호 설정으로 암호화한다. 응답·감사 기록에 토큰을 넣지 않는다. 탈퇴 시 쇼핑몰·상품·토큰·정비안도 FK 연쇄로 정리한다. |

쇼핑몰의 무료 횟수·누적 질문 상한·가격·결제·14일 재측정은 확정하지 않았다. 지도 베타의 숫자를 이식하지 않는다. 누적 질문 상한은 결정한 경우에만 `COMMERCE_QUESTION_LIMIT`으로 설정한다.

## 플랫폼별 쓰기

| 플랫폼 | 자동 경로 | 수동 경로·조건 |
|---|---|---|
| 양 플랫폼 기본 | 관리자 위임 확인 → 관리 화면 원본 읽기 → 승인된 입력 칸 수정·저장 → 재조회 | 실제 화면 설정이 없거나 로그인·보안 확인이 필요하면 중단한다. API 연결은 필요하지 않다. |
| 카페24 | OAuth → 상품/SEO 조회 → 승인한 설명·요약·SEO 필드만 PUT → 재조회 | 카테고리별 상품 속성의 쓰기 매핑은 별도 검증 대상이다. |
| 스마트스토어 | 공식 커머스솔루션 SELLER 인증 → 원상품 조회 → 최신 구조를 보존한 원상품 PUT | 공식 연결 전에는 매니저 권한으로 수동 처리한다. 개인용 SELF 앱 키를 입력받지 않는다. 상품 속성은 수동 처리한다. |

스마트스토어의 본문 API 경로는 정비안 생성에서 별도로 확인한 `allowEditorConversion=true`를 해당 정비안에 기록한다. 승인은 같은 정비안 ID와 원본 해시를 지정해야 한다. 승인 요청에 `editorConversionConfirmed=false`를 명시하면 전환을 거부한다. 별도 확인이 없으면 수동 정비안으로 만든다.

위 표의 API 경로는 API 모드에서만 사용한다. 브라우저 모드는 실제 HTML 입력 화면을 확인한 범위에서 실행하며 API 편집기 전환 옵션을 요구하지 않는다. `BrowserProduct`는 `selectors/{platform}.yaml` 또는 전용 설정 폴더를 읽는다. 기본 설정은 실제 화면에서 구성했다. 2026-11-24 두 플랫폼에서 본문 수정·저장·재조회·공개 확인·복구를 검증했다. 스마트스토어는 기존 HTML 작성 방식 상품을 대상으로 한다. 대표 계정 검증이며 별도 고객의 위임 역할 검증과 구분한다.

수동 저장 기록은 `manual_recorded`다. 이 기록만으로 API 인증·쓰기 검증·공개 반영을 완료 처리하지 않는다.

## API

모든 경로는 `/api/commerce` 아래에 있다. 변경 요청은 기존 CSRF 쿠키·헤더가 필요하다.

| 경로 | 용도 |
|---|---|
| `GET /capabilities` | 플랫폼·지원 필드·현재 편집 모드의 `fieldSupport`·권한 방식 |
| `GET /operator/shops`, `GET /operator/tasks` | 관리자 전용 고객 스토어·초대 확인 대기·작업 대기 |
| `GET /jobs/{job_id}`, `GET /shops/{shop_id}/jobs` | 브라우저·AI 작업 상태 |
| `POST /shops/{shop_id}/catalog`, `GET /shops/{shop_id}/catalog` | 위임 관리 화면의 플랫폼 상품 목록 조회·마지막 결과 |
| `POST /products/{product_id}/prepare` | AI 조사·필요 정보 판단·정비안 생성 |
| `POST/GET /products/{product_id}/measure-sets`, `POST /measure-sets/{set_id}/runs`, `GET /products/{product_id}/measure-runs`, `GET /measure-runs/{run_id}`, `GET /measure-compare` | AI 노출 진단·전후 비교 |
| `GET /shops`, `POST /shops`, `GET /shops/{shop_id}` | 판매자 소유 스토어 |
| `POST /shops/{shop_id}/manager` | 판매자 초대 요청. 확인·권한 회수 기록은 관리자만 가능 |
| `POST /shops/{shop_id}/cafe24/authorize`, `GET /cafe24/callback` | 계정·쇼핑몰에 묶인 10분짜리 일회용 OAuth state |
| `POST /shops/{shop_id}/smartstore/seller` | 관리자가 공식 연결로 확인한 판매자 ID를 등록. 서버 앱 설정 필요 |
| `POST /shops/{shop_id}/disconnect` | seelo의 API 접근 중단·로컬 토큰 폐기. 플랫폼 측 앱 삭제와는 별개 |
| `GET /shops/{shop_id}/products`, `POST /shops/{shop_id}/products/import` | 수집된 상품 조회·API 원본 수집 |
| `POST /shops/{shop_id}/products/manual-snapshot` | API 연결 전 판매자 제공 원본. API 검증 증거로 사용하지 않음 |
| `GET /products/{product_id}` | 상품 원본·사실 |
| `POST /products/{product_id}/research` | 기존 자료·지정 URL에서 AI 사실 추출 |
| `POST /products/{product_id}/facts`, `POST /products/{product_id}/answers` | 근거 보완·실제로 요청받은 사실 답변 |
| `GET /products/{product_id}/plans`, `POST /products/{product_id}/plans` | 정비안 목록·새 정비안 생성 |
| `GET /plans/{plan_id}`, `POST /plans/{plan_id}/approve` | 정비안 조회·선택 승인 |
| `POST /plans/{plan_id}/apply`, `POST /plans/{plan_id}/verify` | 승인한 변경 저장·재조회 |
| `POST /plans/{plan_id}/rollback` | 수정 전 값 복구 |
| `GET /plans/{plan_id}/instructions`, `POST /plans/{plan_id}/manual-result` | 승인 범위 수동 작업 지침·관리자 기록 |
| `POST /plans/{plan_id}/publication`, `GET /plans/{plan_id}/writes` | 관리자 공개 확인·저장/복구 이력 |

`POST /shops`는 `storeUrl`만 받아도 플랫폼·스토어 ID·쇼핑몰 번호를 판별한다. 연결 도메인이면 `custom_domain_requires_mall_id`로 직접 입력을 요구한다. 상품 가져오기는 상품번호 또는 같은 몰의 카페24 상품 주소를 받는다. 스마트스토어 공개 주소의 번호는 원상품번호가 아니므로 받지 않는다. `GET /shops/{id}/products`는 `query`·`page`·`pageSize`로 seelo에 가져온 상품만 서버에서 검색한다(`scope=imported`). 정비안은 최근 50개를 반환한다.

## 설정과 실행

1. `uv sync --frozen`으로 잠금 파일의 의존성을 설치한다. 네이버 공식 서명에 `bcrypt`를 사용한다.
2. 별도 개발 DB에서 `alembic upgrade head`로 `0002_commerce`를 적용한다. 쇼핑몰 전용 테이블 네 개를 추가한다. 기존 지도 데이터는 변경하지 않는다.
3. 카페24 개발자 앱의 `CAFE24_CLIENT_ID`, `CAFE24_CLIENT_SECRET`, `CAFE24_API_VERSION`을 보호 환경에 설정한다. callback은 `/api/commerce/cafe24/callback`이다.
4. 앱에서 `mall.read_product`, `mall.write_product`를 동의받는다. 토큰 발급은 `authorized`, 상품 실제 조회는 `read_verified`, 저장 후 값 일치는 `write_verified`다.
5. 스마트스토어 공식 커머스솔루션 연결을 확보한 뒤 서버의 `SMARTSTORE_SOLUTION_ENABLED`, 앱 ID·시크릿을 설정한다. API 대행사 `/partner` 방식은 별도 계약 검증이 필요하다.
6. AI는 기존 `AI_BACKEND=local_cli` 연결과 `OPENAI_PLAN_MODEL`을 재사용한다. 자동 API 대체는 없다. `useAi=false`는 명시적인 근거 기반 정리이며 실제 AI 실행 결과로 기록하지 않는다.
7. 동의받은 테스트 상품에서만 `COMMERCE_WRITES_ENABLED=true`로 쓰기를 켠다. 기본은 false다. 카페24 시험 상품은 진열·판매 안함 상태를 원본대로 유지한다.

운영 DB에는 이 마이그레이션을 적용하지 않았다. 현재 자동 배포기는 새 DB revision을 발견하면 중단한다. 운영 적용 시에는 백업과 마이그레이션을 별도 수행한 뒤 배포한다.

## 실제 검증과 남은 조건

2026-11-19 Windows·Python 3.13·별도 PostgreSQL 16에서 확인했다.

| 검사 | 결과 |
|---|---|
| 전체 회귀 | 955 통과, 환경 조건 16 건너뜀, 실제 공급자 검사 5 제외 |
| 최신 쇼핑몰·DB 스키마·API 계약 집중 검사 | 62 통과. 전체 회귀와 겹치는 항목이 있어 합산하지 않음 |
| 정적 검사·OpenAPI | ruff 통과, 생성 계약 최신 상태 |

서비스 흐름은 로컬 PostgreSQL과 가짜 HTTP 응답으로 검증한다. 새 브라우저 실행기는 두 플랫폼 실계정에서 별도로 본문 수정·저장·공개 반영·복구를 확인했다. [실계정 증거](../../../03_실험/쇼핑몰_관리자화면_실계정검증_20261124/검증결과.md)를 따른다. 카페24 API 앱 설치·OAuth·API 쓰기와 실제 고객의 관리자 위임 역할은 별도 범위다.

필수 외부 검증 순서는 카페24 테스트몰 1개·상품 1~3개 → 공식 권한·OAuth → 승인 저장·재조회 → PC/모바일 확인 → 복구다. 스마트스토어는 공식 솔루션 연결과 편집기 동작을 확인한 뒤 진행한다.

공식 참고: [카페24 상품 수정](https://apidocs.cafe24.com/docs/admin/put-products-by-product-no), [카페24 OAuth](https://developers.cafe24.com/app/front/app/develop/oauth/process), [네이버 원상품 수정](https://apicenter.commerce.naver.com/docs/commerce-api/current/update-origin-product-product), [네이버 인증](https://apicenter.commerce.naver.com/docs/auth).
