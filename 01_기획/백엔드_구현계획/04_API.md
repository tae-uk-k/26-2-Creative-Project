# 04. API 계약

- 모든 경로는 `/api`로 시작한다. JSON 필드는 camelCase다.
- 이 파일의 요청·응답 형태를 바꾸지 않는다. 화면(React)은 이 계약만 보고 만든다.
- 표기: `T | null`은 값이 없을 수 있음, `T[]`는 배열, `"a"|"b"`는 그 문자열 중 하나.

## 1. 공통

| 항목 | 규칙 |
|---|---|
| 인증 | 세션 쿠키 `seelo_session`(05 2장). 표의 "권한"이 `owner`면 로그인 필요(없으면 401 `AUTH_REQUIRED`). `admin`이면 관리자만(아니면 403 `FORBIDDEN`) |
| CSRF | POST·PUT·PATCH·DELETE는 헤더 `X-CSRF-Token` 필수(05 3장). 예외: 없음(OAuth 콜백은 GET) |
| 소유 확인 | 경로의 ID가 가리키는 대상이 현재 사용자 것이 아니면 **404 `NOT_FOUND`**(존재 여부를 드러내지 않음). 관리자는 모두 볼 수 있다 |
| 시각 | ISO 8601, UTC, 예: `2026-11-02T03:15:00Z`. 날짜만 필요한 곳(재측정일)은 KST 날짜 `YYYY-MM-DD` |
| 비율 | `rate`는 0~1 소수(소수점 4자리 반올림). 화면이 %로 바꾼다. 계산 불가면 `null` |
| 평균 순서 | `avgRank`는 소수점 1자리. 등장이 없으면 `null` |
| 목록 | 관리자 목록은 `?page=1&pageSize=20` → `{items, page, pageSize, total}` |
| 오류 | `{"error": {"code", "message", "details"}}`(01 7.6) |

공통 조각(여러 응답에서 씀)

```text
RateSummary { successCount: int, appearanceCount: int, rate: float|null, avgRank: float|null }
ProviderRates { openai: RateSummary, gemini: RateSummary }      # 화면 표기: openai=ChatGPT, gemini=Gemini
SourceMark = "found" | "not_found" | "candidate"
StoreSummary {
  id: int, name: str, address: str|null,
  category: "restaurant"|"cafe"|"bar",
  status: "collecting"|"collected"|"measuring"|"diagnosed"|"measure_failed"|"archived",
  sources: { google: SourceMark, kakao: SourceMark, naver: SourceMark, website: SourceMark, instagram: SourceMark }
}
ConnectionStatus = "not_connected"|"invited"|"connected"|"needs_attention"|"revoked"
```

- `StoreSummary.address`: 가장 최근 Google 스냅샷의 `formattedAddress`. 없으면 카카오 로컬 API를 그 자리에서 다시 불러 `road_address_name`(없으면 `address_name`). 둘 다 없으면 `null`.
- `sources`: `store_sources`에 행이 없으면 `"not_found"`.

## 2. 오류 코드

| 코드 | HTTP | 문구(그대로 응답) | details |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | 입력값을 확인해 주세요 | `{fields: {필드: 코드}}` 필드 코드: `invalid_email`, `weak_password`, `password_mismatch`, `required`, `too_long`, `terms_required` |
| `EMAIL_TAKEN` | 409 | 이 이메일은 {구글/카카오/이메일}로 가입되어 있어요 | `{provider}` |
| `INVALID_CREDENTIALS` | 401 | 이메일 또는 비밀번호가 맞지 않아요 | — |
| `ACCOUNT_LOCKED` | 423 | 로그인을 5번 잘못해서 10분 동안 로그인할 수 없어요 | `{lockedUntil}` |
| `SOCIAL_ACCOUNT` | 409 | 이 이메일은 {구글/카카오}로 가입되어 있어요 | `{provider}` |
| `EMAIL_NOT_VERIFIED` | 403 | 이메일 인증을 먼저 마쳐 주세요 | `{email}` |
| `TOKEN_EXPIRED` | 410 | 링크가 만료됐어요 | — (만료·사용·없는 토큰 모두 이 코드) |
| `RATE_LIMITED` | 429 | 요청이 너무 많아요. 잠시 후 다시 시도해 주세요 | `{retryAfterSeconds}` |
| `RESEND_COOLDOWN` | 429 | 잠시 후 다시 보낼 수 있어요 | `{retryAfterSeconds}` |
| `AUTH_REQUIRED` | 401 | 로그인이 필요해요 | — |
| `TERMS_REQUIRED` | 403 | 약관 동의가 필요해요 | — |
| `FORBIDDEN` | 403 | 권한이 없어요 | — |
| `CSRF_FAILED` | 403 | 페이지를 새로고침한 뒤 다시 시도해 주세요 | — |
| `NOT_FOUND` | 404 | 찾을 수 없어요 | — |
| `INVALID_STATE` | 409 | 이미 처리됐거나 지금은 할 수 없는 요청이에요 | `{currentStatus}` |
| `WRONG_PASSWORD` | 400 | 지금 비밀번호가 맞지 않아요 | — |
| `PASSWORD_LOGIN_UNAVAILABLE` | 409 | {구글/카카오}로 가입한 계정은 비밀번호를 바꿀 수 없어요 | `{provider}` |
| `CONFIRM_TEXT_MISMATCH` | 400 | 확인 문구가 맞지 않아요 | — |
| `NO_LINK` | 422 | Google 지도·카카오맵·네이버 지도 링크를 넣어 주세요 | — |
| `UNSUPPORTED_LINK` | 422 | Google 지도·카카오맵·네이버 지도 링크만 넣을 수 있어요 | — |
| `LINK_UNRESOLVED` | 422 | 링크를 확인하지 못했어요. 다른 링크를 넣어 주세요 | — |
| `STORE_NOT_FOUND` | 422 | 가게를 찾지 못했어요. 다른 지도 링크를 넣어 주세요 | — |
| `NOT_TARGET_CATEGORY` | 422 | 지금은 음식점·카페·바만 진단할 수 있어요 | — |
| `FIX_IN_PROGRESS` | 409 | 정비가 끝나기 전에는 가게를 바꿀 수 없어요 | — |
| `CONFIRM_REPLACE_REQUIRED` | 409 | 가게를 바꾸면 지금 가게의 결과는 지난 기록으로 옮겨져요 | `{usedFree: bool}` → true면 화면이 "무료 진단은 다시 할 수 없어요"도 보여 줌 |
| `CANDIDATE_EXPIRED` | 410 | 시간이 지나 다시 찾아야 해요. 링크를 다시 넣어 주세요 | — |
| `TRY_LATER` | 503 | 잠시 후 다시 시도해 주세요 | — |
| `RETRY_LIMIT` | 429 | 내일 다시 시도해 주세요 | — |
| `NO_STORE` | 409 | 먼저 가게를 등록해 주세요 | — |
| `NOT_ELIGIBLE` | 409 | 지금은 자동 정비를 신청할 수 없어요 | `{reason: "store_not_ready"}` |
| `ALREADY_REQUESTED` | 409 | 이 가게는 이미 자동 정비를 신청했어요 | — |
| `CONNECTION_NOT_CONNECTED` | 409 | 지도가 연결된 뒤에 승인할 수 있어요 | `{provider}` |
| `ITEMS_MISMATCH` | 400 | 정비안이 바뀌었어요. 새로고침해 주세요 | — |
| `NEEDS_OWNER_INPUT` | 400 | "확인 필요" 칸을 채우거나 빼 주세요 | `{itemIds}` |
| `SENSITIVE_NOT_CONFIRMED` | 400 | 알레르기·할랄 정보를 확인해 주세요 | `{itemIds}` |
| `FIELD_INVALID` | 400 | 입력한 값이 이 칸의 규칙에 맞지 않아요 | `{itemId, reason}` reason: `too_long`, `bad_format`, `too_many`, `placeholder_left` |
| `REPORT_NOT_READY` | 404 | 보고서가 아직 준비되지 않았어요 | — |
| `REJECT_REASON_REQUIRED` | 422 | 거절 사유를 넣어 주세요 | — |
| `INTERNAL_ERROR` | 500 | 잠시 후 다시 시도해 주세요 | — |

## 3. 화면 경로 표(메일 링크·리디렉션용)

백엔드는 아래 경로로만 보낸다. 화면 구현은 이번 범위가 아니다.

| 화면 | 경로 |
|---|---|
| S01 랜딩 | `/` |
| S02 회원가입 | `/signup` (오류: `/signup?error=oauth_canceled|oauth_failed|email_taken&provider=google|kakao|email`) |
| 소셜 약관 동의 | `/signup/terms` |
| S03 인증 안내 | `/signup/sent` |
| S04 카카오 이메일 입력 | `/signup/kakao-email` |
| S05 로그인 | `/login` (오류: `/login?error=oauth_canceled|oauth_failed`) |
| S06 재설정 요청·새 비밀번호 | `/password/forgot`, `/password/reset/{token}` |
| 인증 링크 | `/verify-email/{token}` |
| S07 홈 | `/home` |
| S08 가게 등록·변경 | `/store/new`, `/store/new?mode=change` |
| S09 후보 선택 | `/store/candidates` |
| S10 진행 | `/runs/{runId}` |
| S11 무료 진단 결과 | `/diagnosis/{runId}` |
| S12 자동 정비 | `/fix` |
| S13 정비안 | `/fix/plans/{planId}` |
| S14 계정 설정 | `/account` |
| S15 연결 | `/fix/connect` |
| S16 보고서 | `/fix/report`, 지난 기록 `/reports/{reportId}` |
| A01 | `/admin/fix-requests`, `/admin/fix-requests/{id}` |

## 4. 인증·계정(F-01, 상세 처리는 05)

| 메서드·경로 | 권한 | 요청 | 성공 응답 | 오류 |
|---|---|---|---|---|
| `GET /api/auth/csrf` | 없음 | — | 204, 쿠키 `seelo_csrf` 설정 | — |
| `POST /api/auth/signup` | 없음 | `{email, password, passwordConfirm, agreeTerms: bool, agreePrivacy: bool}` | 201 `{email, mailTicket}` → 화면은 S03 | `VALIDATION_ERROR`, `EMAIL_TAKEN`, `RATE_LIMITED` |
| `GET /api/auth/signup/mail-status?ticket=` | 없음 | — | 200 `{status: "queued"|"sent"|"failed"}` | `NOT_FOUND` |
| `POST /api/auth/verify-email` | 없음 | `{token}` | 200 `{user: Me}` + 세션 쿠키 → S07 | `TOKEN_EXPIRED` |
| `POST /api/auth/verify-email/resend` | 없음 | `{email}` | 202 `{mailTicket}`(가입 여부와 무관하게 같은 응답) | `RESEND_COOLDOWN`, `RATE_LIMITED` |
| `POST /api/auth/login` | 없음 | `{email, password}` | 200 `{user: Me}` + 세션 쿠키 | `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `SOCIAL_ACCOUNT`, `EMAIL_NOT_VERIFIED` |
| `POST /api/auth/logout` | owner | — | 204, 세션 삭제 | — |
| `GET /api/auth/me` | owner | — | 200 `Me` | `AUTH_REQUIRED`, `TERMS_REQUIRED` |
| `POST /api/auth/password/forgot` | 없음 | `{email}` | 202 `{}`(항상 같음) | `RATE_LIMITED` |
| `POST /api/auth/password/reset` | 없음 | `{token, password, passwordConfirm}` | 204 → 화면은 S05 | `TOKEN_EXPIRED`, `VALIDATION_ERROR` |
| `GET /api/oauth/{provider}/start?intent=signup|login` | 없음 | provider: `google`·`kakao` | 302 제공자 동의 화면 | — |
| `GET /api/oauth/{provider}/callback` | 없음 | 제공자가 붙인 `code`, `state` 또는 `error` | 302 화면 경로(05 5장) | — |
| `GET /api/auth/pending-signup` | 쿠키 `seelo_pending` | — | 200 `{provider, email: str|null, needsEmail: bool}` | `NOT_FOUND` |
| `POST /api/auth/pending-signup/complete` | 쿠키 `seelo_pending` | `{agreeTerms, agreePrivacy, email?: str}`(needsEmail이면 필수) | 200 `{next: "/home", user: Me}` + 세션, 또는 202 `{next: "/signup/sent", mailTicket}` | `VALIDATION_ERROR`, `EMAIL_TAKEN`, `NOT_FOUND` |
| `GET /api/account` | owner | — | 200 `{email, provider: "email"|"google"|"kakao", createdAt, canChangePassword: bool}` | — |
| `POST /api/account/password` | owner | `{currentPassword, newPassword, newPasswordConfirm}` | 204 | `WRONG_PASSWORD`, `VALIDATION_ERROR`, `PASSWORD_LOGIN_UNAVAILABLE` |
| `DELETE /api/account` | owner | `{confirmText}` | 204, 쿠키 삭제 → 화면은 S01 | `CONFIRM_TEXT_MISMATCH` |

```text
Me { id: int, email: str, role: "owner"|"admin", provider: "email"|"google"|"kakao", hasStore: bool }
```

- `confirmText`는 상수 `ACCOUNT_DELETE_CONFIRM_TEXT = "탈퇴합니다"`와 같아야 한다 `[기획 확인]`.
- `/api/auth/me`는 약관 미동의 계정이 있을 수 없도록 설계했지만(05 5장), 혹시 `terms_agreed_at IS NULL`이면 403 `TERMS_REQUIRED`.

## 5. 홈·가게(F-02, F-03, S07~S10)

### 5.1 `GET /api/home` (owner)

```text
HomeResponse {
  card: "no_store"|"fix_requested"|"fix_rejected"|"measuring"|"measure_failed"|"diagnosed"
        |"free_used_store_changed"|"plan_needs_approval"|"plan_preparing"|"connect_needed"
        |"fixing"|"remeasure_waiting"|"remeasuring"|"remeasure_failed"|"report_ready"|"unknown",
  store: StoreSummary|null,
  storeChangeBlocked: bool,
  revokedProviders: ("google"|"kakao")[],
  manualInProgress: bool,
  retriesLeftToday: int,
  hasHistory: bool,
  data: object      # 아래 표
}
```

| card | data |
|---|---|
| `no_store`, `free_used_store_changed`, `plan_preparing`, `unknown` | `{}` |
| `fix_requested` | `{requestId, requestedAt}` |
| `fix_rejected` | `{requestId, rejectReason}` |
| `measuring` | `{runId, kind, stage, progressDone, progressTotal, waitingReason}` |
| `measure_failed` | `{runId}` |
| `diagnosed` | `{runId, providers: ProviderRates, findingsCount}` |
| `plan_needs_approval` | `{planIds: int[], itemCount}`(awaiting 정비안의 칸 수) |
| `connect_needed` | `{connections: {google: ConnectionStatus, kakao: ConnectionStatus}}` |
| `fixing` | `{}` |
| `remeasure_waiting` | `{dueDate: "YYYY-MM-DD", changedCount}`(applied + manual_done 칸 수) |
| `remeasuring` | `{runId, stage, progressDone, progressTotal}` |
| `remeasure_failed` | `{requestId}` |
| `report_ready` | `{reportId, providers: {openai: {before: RateSummary, after: RateSummary}, gemini: {...}}}` |

- 구현 메모(2026-10-28, 8단계): `measuring`·`remeasuring`에 진행 중 측정이 없으면(무료 사용 뒤 바꾼 가게의 수집) `runId`·`stage`·`kind`는 `null`, 진행 수는 0. `diagnosed`는 가장 최근 completed 진단. `report_ready`의 전후 값은 보고서 내용 대신 `base_run_id`·`after_run_id`의 지표에서 만든다. 가게가 없을 때 `retriesLeftToday`는 3.

### 5.2 가게

| 메서드·경로 | 권한 | 요청 | 성공 응답 | 오류 |
|---|---|---|---|---|
| `POST /api/stores/identify` | owner | `{name: 1~50자, link: 2000자 이하 문자열, mode: "new"|"change", confirmReplace: bool=false}` | 200 `IdentifyResult` | `VALIDATION_ERROR`, `NO_LINK`, `UNSUPPORTED_LINK`, `LINK_UNRESOLVED`, `STORE_NOT_FOUND`, `NOT_TARGET_CATEGORY`, `FIX_IN_PROGRESS`, `CONFIRM_REPLACE_REQUIRED`, `TRY_LATER`, `RATE_LIMITED`(사용자당 분당 10회) |
| `POST /api/stores/identify/select` | owner | `{candidateToken, candidateId}` | 200 `IdentifyResult`(confirmed만) | `CANDIDATE_EXPIRED`, `NOT_TARGET_CATEGORY`, `FIX_IN_PROGRESS`, `TRY_LATER` |
| `GET /api/stores/current` | owner | — | 200 `{store: StoreSummary|null}` | — |
| `GET /api/stores/history` | owner | — | 200 `{stores: [{storeId, name, archivedAt, diagnosisRunId: int|null, reportId: int|null}]}` | — |
| `POST /api/stores/current/not-mine` | owner | `{runId}` | 204 | `INVALID_STATE` |
| `POST /api/stores/current/retry` | owner | — | 202 `{runId}` | `INVALID_STATE`, `RETRY_LIMIT` |

```text
IdentifyResult =
  { result: "confirmed", storeId: int, runId: int|null, next: str }       # next: "/runs/{runId}" 또는 "/home"(무료 사용 후 가게 변경)
| { result: "candidates", candidateToken: str,
    candidates: [{ candidateId: str, name: str, address: str|null, category: str|null, providers: ("google"|"kakao"|"naver")[] }] }  # 최대 5개
```

- `mode = "change"`이고 보관 중이 아닌 가게가 있는데 `confirmReplace = false`면 409 `CONFIRM_REPLACE_REQUIRED`. 화면이 확인을 받고 `true`로 다시 보낸다.
- 처리 순서는 07 3장.

### 5.3 측정 진행(S10)

| 메서드·경로 | 권한 | 응답 |
|---|---|---|
| `GET /api/runs/{runId}/progress` | owner(그 가게 주인) | 200 `RunProgress` |
| `GET /api/runs/{runId}/collected` | owner | 200 `CollectedInfo` |

```text
RunProgress {
  runId, kind: "diagnosis"|"remeasure",
  status: "queued"|"running"|"parsing"|"completed"|"failed"|"canceled",
  stage: "collecting"|"generating_questions"|"calling_ai"|"finalizing"|"done",
  progressDone: int, progressTotal: int,
  waitingReason: "cost_limit"|null,
  failureReason: "failure_rate"|"collect_insufficient"|"enqueue_failed"|"stuck"|null,
  canCancel: bool,                       # [내 가게가 아니에요] 노출 여부: 진단·trigger initial·신청 없음
  next: str|null                         # completed면 진단 "/diagnosis/{runId}", 재측정 "/fix/report"
}
CollectedInfo {
  rows: [{ key: str, label: str, values: { google?: str, kakao?: str, naver?: str, website?: str, instagram?: str } }]
}
```

- 실패율 숫자는 응답에 넣지 않는다.
- `CollectedInfo`는 값이 있는 칸만 넣는다. 행 키와 이름: `name` 가게 이름, `address` 주소, `phone` 전화, `hours` 영업시간, `website` 웹사이트, `price` 가격대, `category` 업종, `menu` 메뉴, `intro` 소개, `amenities` 편의 정보, `instagram` 인스타그램. 카카오·네이버 열은 요청 때마다 다시 불러온 값이다(07 6장).
- 진행률 API는 DB 조회 1~2번으로 끝내 200ms 이내로 응답한다(외부 호출 금지). `collected`는 외부 호출이 있으므로 별도 경로다.

## 6. 무료 진단(S11, F-07)

`GET /api/diagnosis/{runId}` (owner, 관리자) — 측정이 `kind = diagnosis`이고 `completed`일 때만. 아니면 404.

```text
DiagnosisResponse {
  runId, storeId, storeName, measuredAt,
  providers: ProviderRates,                          # successCount = m(보통 30)
  target: { name: str, providers: ProviderRates },
  competitors: [{ rankOrder: 1~5, name: str, providers: ProviderRates }],   # 5곳 미만이면 있는 만큼
  questions: [{
    orderNo, lang: "en"|"ko", text, textKo: str|null,
    providers: { openai: {appearanceCount, successCount}|null, gemini: {...}|null }   # null = 측정하지 못함
  }],
  sources: {
    top: [{ domain, count }],                        # 많이 인용된 사이트 5개
    targetSources: [{ domain, count }]               # 우리 가게 추천에 붙은 사이트. 없으면 []
  },
  findingsCount: int,                                # stage=diagnosis 개수만
  conditions: { questionCount: 3, repeatCount: 10, providers: ["openai","gemini"], measuredAt }
}
```

- **`findings` 내용 필드를 응답 모델에 두지 않는다.** `findingsCount`만 있다(W-06-2).
- 구현 메모(2026-10-28): 최상위 `providers`는 `target.providers`와 같은 값이다. `measuredAt`은 측정 `completed_at`. `repeatCount`는 그 측정 실행의 최대 `repeat_no`. 질문별 값은 성공 답변이 0이면 `null`. 관리자는 남의 진단도 볼 수 있다.

## 7. 자동 정비(S12, S13, S15, S16)

### 7.1 신청(S12)

| 메서드·경로 | 권한 | 요청 | 성공 응답 | 오류 |
|---|---|---|---|---|
| `GET /api/fix/requests/current` | owner | — | 200 `FixRequestState` | — |
| `POST /api/fix/requests` | owner | — | 201 `{requestId}` | `NO_STORE`, `NOT_ELIGIBLE`, `ALREADY_REQUESTED` |
| `POST /api/fix/requests/current/remeasure/retry` | owner | — | 202 `{runId}` | `INVALID_STATE`, `RETRY_LIMIT` |

```text
FixRequestState {
  request: null | {
    id, status, createdAt, rejectReason: str|null,
    hasBaseRun: bool,                                  # false면 "신청이 승인되면 측정부터 다시 진행해요"
    steps: [{ key: "received"|"approved"|"connect"|"review"|"fixing"|"remeasure_waiting"|"report",
              state: "done"|"current"|"todo", actionPath: str|null }],   # connect → "/fix/connect", review → "/fix/plans/{planId}"
    remeasureDueDate: "YYYY-MM-DD"|null,
    reportId: int|null
  },
  canRequest: bool,                                    # 03 7장 can_request_fix
  needsMeasurementFirst: bool                          # 가게가 collected
}
```

`steps` 판정: `received` 항상 done. `approved`: 신청이 approved 이후면 done, requested면 current. `connect`: connected 연결이 하나라도 있으면 done, connecting이면 current. `review`: approved 정비안이 있으면 done, awaiting_approval이면 current. `fixing`: remeasure_scheduled 이후면 done, fixing이면 current. `remeasure_waiting`: remeasuring 이후면 done, remeasure_scheduled면 current. `report`: report_ready면 done, remeasuring·remeasure_failed면 current. 거절이면 `received`만 done이고 나머지 todo.

### 7.2 연결(S15)

| 메서드·경로 | 권한 | 요청 | 성공 응답 | 오류 |
|---|---|---|---|---|
| `GET /api/fix/connect` | owner | — | 200 `ConnectState` | `NOT_FOUND`(승인된 신청 없음) |
| `POST /api/fix/connect/{provider}/invited` | owner | provider: `google`·`kakao` | 200 `ConnectionView` | `INVALID_STATE`(connected 상태 등) |

```text
ConnectState {
  requestId,
  seeloAccounts: { google: str, kakao: str },          # SEELO_GOOGLE_ACCOUNT_EMAIL, SEELO_KAKAO_ACCOUNT_ID
  google: ConnectionView, kakao: ConnectionView
}
ConnectionView {
  provider, status: ConnectionStatus,
  attentionReason: str|null,
  invitedAt: str|null,
  inviteNotArrived: bool,                               # status=invited이고 invite_reminder_sent_at 있음
  storeFoundOnMap: bool,                                # store_sources 그 지도 found. false면 화면이 등록 방법 안내
  canInvite: bool                                       # 상태가 not_connected·needs_attention·revoked
}
```

접근 조건: 현재 가게의 신청이 approved 이후 상태(`approved`~`report_ready`, `remeasure_failed` 포함).

- 구현 메모(2026-10-28, 10단계): [초대했어요]는 신청이 report_ready면 409. 다시 초대하면 `inviteReminderSentAt`·`attentionReason`을 비운다. `seeloAccounts`는 설정 `SEELO_GOOGLE_ACCOUNT_EMAIL`·`SEELO_KAKAO_ACCOUNT_ID`(비어 있으면 빈 문자열). 관리자 연결 확인 응답: 수동 200 `{status}`, 작업 등록 202 `{}`.

### 7.3 정비안(S13, F-09)

| 메서드·경로 | 권한 | 요청 | 성공 응답 | 오류 |
|---|---|---|---|---|
| `GET /api/fix/plans` | owner | — | 200 `{plans: [{planId, provider, status, version}]}` 지도별 최신 버전만 | — |
| `GET /api/fix/plans/{planId}` | owner, admin | — | 200 `PlanDetail` | `NOT_FOUND` |
| `GET /api/fix/plans/{planId}/evidence` | owner, admin | — | 200 `PlanEvidence` | `NOT_FOUND` |
| `POST /api/fix/plans/{planId}/approve` | owner | `ApproveRequest` | 202 `{planId, status: "approved"}` | `ITEMS_MISMATCH`, `NEEDS_OWNER_INPUT`, `SENSITIVE_NOT_CONFIRMED`, `FIELD_INVALID`, `CONNECTION_NOT_CONNECTED`, `INVALID_STATE` |

**응답 조건(명세서 2장)**: 신청이 승인됐고 그 지도 연결이 한 번이라도 connected였을 때(`connected_at IS NOT NULL`)만 응답한다. 아니면 404. 정비안이 generating·generation_failed면 `items: []`, `findings: []`로 상태만 준다.

```text
PlanDetail {
  planId, provider: "google"|"kakao", status, version, createdAt, approvedAt: str|null, readOnly: bool,
  summary: {
    providers: ProviderRates,                           # 기준 측정
    competitorPosition: { position: int, total: int },  # 08 5.5
    itemCounts: { google: int, kakao: int },            # 지도별 최신 정비안의 칸 수(제외 전)
    connections: { google: ConnectionStatus, kakao: ConnectionStatus }
  },
  findings: [{
    findingId, category, categoryLabel, title, provider, field,
    questionCount, competitorCount, priority,
    relatedResponseIds: int[], itemId: int|null          # 이 문제를 고치는 칸
  }],
  items: [{
    itemId, orderNo, field, fieldLabel,
    currentValue: json|null, proposedValue: json|null, approvedValue: json|null,
    reason, findingIds: int[],
    needsOwnerInput: bool, sensitive: bool, ownerConfirmed: bool, ownerEdited: bool, excluded: bool,
    constraints: { type: "text"|"hours"|"url"|"phone"|"menu"|"tags"|"services"|"attributes", maxLength?: int, maxItems?: int },
    result: null | { status: "queued"|"applied"|"pending_reflection"|"manual_required"|"manual_done"|"disconnected",
                     statusLabel: "정비 중"|"완료"|"반영 대기"|"seelo 팀 처리 중"|"완료"|"연결 끊김",
                     appliedAt, verifiedAt }
  }],
  ownerOnlyFields: [{ field: "name"|"address"|"category", guide: str }],   # 이름·주소·업종이 다를 때 사장님이 직접 고치는 방법
  mapNotFound: bool                                     # 이 지도에서 가게를 못 찾음 → 등록·인증 방법 안내
}
PlanEvidence {
  questions: [{ orderNo, text, answers: [{ responseId, provider, repeatNo, rawText, highlightNames: str[] }] }]
}
ApproveRequest {
  items: [{ itemId: int, excluded: bool, approvedValue?: json, ownerConfirmed?: bool }]   # 정비안의 모든 칸을 정확히 한 번씩
}
```

- 승인 처리 규칙은 09 7장. 상태 라벨 `statusLabel`은 위 순서대로 상태와 1:1이다.
- `PlanEvidence.highlightNames`: 우리 가게 이름 후보와 주변 가게 5곳의 원래 이름.
- 구현 메모(2026-10-28, 11단계)
  - `highlightNames`의 이름 후보 = 입력 이름·Google 이름·기준 측정에서 우리 가게로 판정된 추천 이름. 답변 원문에 들어 있는 이름만 준다.
  - `readOnly`는 관리자이거나, 정비안이 awaiting_approval이 아니거나, 신청이 connecting·fixing·remeasure_scheduled가 아닐 때 참. 관리자의 승인 요청은 404.
  - 승인 오류 details: `NEEDS_OWNER_INPUT`·`SENSITIVE_NOT_CONFIRMED` `{itemIds}`, `FIELD_INVALID` `{itemId, reason}`(too_long·bad_format·too_many·placeholder_left), `CONNECTION_NOT_CONNECTED` `{provider}`, `INVALID_STATE` `{currentStatus}`.
  - 관리자 `POST /api/admin/fix-plans/{planId}/regenerate`: generation_failed일 때만 202 `{}`(아니면 409 `INVALID_STATE`).

### 7.4 보고서(S16, F-11)

| 메서드·경로 | 권한 | 성공 응답 | 오류 |
|---|---|---|---|
| `GET /api/fix/report` | owner | 200 `ReportResponse`(현재 가게 신청이 report_ready일 때) | `REPORT_NOT_READY` |
| `GET /api/reports/{reportId}` | owner, admin | 200 `ReportResponse`(completed만) | `NOT_FOUND` |

```text
ReportResponse { reportId, fixRequestId, version, createdAt, content: ReportContent }   # ReportContent는 10 3장
```

구현 메모(2026-10-29, 14단계)
- `api/fix_report.py`, `api/reports.py`, `schemas/report.py`. 현재 가게의 완료 보고서가 없으면 404 `REPORT_NOT_READY`. 개별 ID는 완료 상태·소유권을 함께 검사하며 없는 것·남의 것·생성 중·실패는 모두 404 `NOT_FOUND`. 관리자는 개별 ID로 조회한다. 보관된 가게도 소유자는 개별 ID 조회 가능.
- 관리자 `remeasure-now`는 예약·신청을 잠그고 측정·큐·감사 기록(`remeasure.now`)을 함께 커밋한다. 중복 호출 409. E24는 최신 실패 보고서만 새 버전으로 만들고 `report.regenerate`를 기록한다.

구현 메모(2026-10-29, 16단계): 카카오 칸 값은 보고서에 중복 저장하지 않고, 권한 검사 뒤 `fix_logs`에서 채워 응답한다(10 3.4). API의 `beforeValue`·`appliedValue` 형식은 같다. 저장 JSON만 카카오 두 값이 null이다.

## 8. 관리자(A01)

모두 권한 `admin`. 처리할 수 없는 상태면 409 `INVALID_STATE`.

| 메서드·경로 | 요청 | 성공 응답 | 처리 |
|---|---|---|---|
| `GET /api/admin/fix-requests?filter=&page=&pageSize=` | filter: 03 5장 키(없으면 전체) | 200 목록 `[{id, createdAt, ownerEmail, storeName, diagnosisStatus, status, displayStatus}]` | 최신 신청 먼저 |
| `GET /api/admin/fix-requests/{id}` | — | 200 `AdminRequestDetail` | — |
| `POST /api/admin/fix-requests/{id}/approve` | — | 200 `{status}` | E9 |
| `POST /api/admin/fix-requests/{id}/reject` | `{reason: 1~500자}` | 200 `{status}` | E10. 빈 사유 422 `REJECT_REASON_REQUIRED` |
| `POST /api/admin/connections/{connectionId}/verify` | 선택 `{manualResult: "connected"|"needs_attention", attentionReason?, externalRef?}` | 본문 없음: 202 `{}`(`verifyConnection` 등록) / 본문 있음: 200 `{status}`(바로 처리) | 09 5장 수동 확인 모드 |
| `POST /api/admin/fix-logs/{fixLogId}/manual-done` | `{beforeValue?: json}`(자동으로 읽지 못해 `before_value`가 비었을 때만) | 200 `{status: "manual_done"}` | E30 |
| `POST /api/admin/fix-plans/{planId}/regenerate` | — | 202 `{}` | E23(generation_failed만) |
| `POST /api/admin/fix-requests/{id}/report/regenerate` | — | 202 `{reportId}` | E24(최신 보고서 generation_failed만) |
| `POST /api/admin/fix-requests/{id}/remeasure-now` | — | 202 `{runId}` | E20(remeasure_scheduled만) |
| `GET /api/admin/manual-items` | — | 200 `[{fixLogId, fixRequestId, storeName, provider, field, fieldLabel, approvedValue, manualReason, adminUrl, createdAt}]` | manual_required 칸 전체 |

```text
AdminRequestDetail {
  request: { id, status, displayStatus, createdAt, rejectReason, decidedAt, fixCompletedAt },
  owner: { userId, email },
  store: { id, name, status, sources },
  baseRun: { id, status }|null,
  runs: [{ id, kind, status, trigger, createdAt, completedAt, failureRate, costUsd }],   # 관리자에게는 실패율·비용을 보인다
  connections: [{ id, provider, status, attentionReason, invitedAt, inviteReminderSentAt, connectedAt, revokedAt }],
  plans: [{ id, provider, version, status, lastError, createdAt, approvedAt }],
  manualItems: [같은 형식: manual-items 항목],
  schedule: { id, dueAt, status, triggeredBy }|null,
  reports: [{ id, version, status, lastError, createdAt }]
}
```

- `adminUrl`: Google은 `https://business.google.com/` + 프로필 경로 `[PoC]`, 카카오는 파트너센터 매장정보 화면 주소 `[PoC]`. 정해지기 전에는 각 서비스 첫 화면 주소를 준다.
- 구현 메모(2026-10-28, 9단계): 목록 `filter`가 03 5장 키가 아니면 422, `pageSize`는 1~100. `diagnosisStatus`는 그 가게의 가장 최근 진단 측정 상태. 상세의 `runs`는 그 가게의 모든 측정(최신 먼저)이고 `failureRate`·`costUsd`는 숫자. `adminUrl` 기본값은 Google `https://business.google.com/`, 카카오 `https://business.kakao.com/`(카카오는 `[PoC]`로 확인).
- 구현 메모(2026-10-28, 12단계)
  - manual-done: 본문 생략 가능. 없는 칸 404, manual_required가 아니면 409 `{currentStatus}`. `beforeValue`는 `before_value`가 비었을 때만 저장한다.
  - manual-items: 오래된 것 먼저, 모든 신청의 칸.

## 9. 기타

| 메서드·경로 | 권한 | 응답 |
|---|---|---|
| `GET /api/health` | 없음 | 200 `{status: "ok", db: "ok"}`. DB 연결 실패면 503 `{status: "error", db: "error"}` |
