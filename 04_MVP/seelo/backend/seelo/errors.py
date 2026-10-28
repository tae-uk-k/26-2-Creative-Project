"""업무 오류와 응답 형식(01 7.6, 04 2장, 13 3장)."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = structlog.get_logger()

PROVIDER_LABEL = {"google": "구글", "kakao": "카카오", "email": "이메일"}

# 코드: (HTTP 상태, 문구). 문구의 {provider}는 details.provider를 PROVIDER_LABEL로 바꿔 넣는다.
ERRORS: dict[str, tuple[int, str]] = {
    "VALIDATION_ERROR": (422, "입력값을 확인해 주세요"),
    "EMAIL_TAKEN": (409, "이 이메일은 {provider}로 가입되어 있어요"),
    "INVALID_CREDENTIALS": (401, "이메일 또는 비밀번호가 맞지 않아요"),
    "ACCOUNT_LOCKED": (423, "로그인을 5번 잘못해서 10분 동안 로그인할 수 없어요"),
    "SOCIAL_ACCOUNT": (409, "이 이메일은 {provider}로 가입되어 있어요"),
    "EMAIL_NOT_VERIFIED": (403, "이메일 인증을 먼저 마쳐 주세요"),
    "TOKEN_EXPIRED": (410, "링크가 만료됐어요"),
    "RATE_LIMITED": (429, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요"),
    "RESEND_COOLDOWN": (429, "잠시 후 다시 보낼 수 있어요"),
    "AUTH_REQUIRED": (401, "로그인이 필요해요"),
    "TERMS_REQUIRED": (403, "약관 동의가 필요해요"),
    "FORBIDDEN": (403, "권한이 없어요"),
    "CSRF_FAILED": (403, "페이지를 새로고침한 뒤 다시 시도해 주세요"),
    "NOT_FOUND": (404, "찾을 수 없어요"),
    "INVALID_STATE": (409, "이미 처리됐거나 지금은 할 수 없는 요청이에요"),
    "WRONG_PASSWORD": (400, "지금 비밀번호가 맞지 않아요"),
    "PASSWORD_LOGIN_UNAVAILABLE": (409, "{provider}로 가입한 계정은 비밀번호를 바꿀 수 없어요"),
    "CONFIRM_TEXT_MISMATCH": (400, "확인 문구가 맞지 않아요"),
    "NO_LINK": (422, "Google 지도·카카오맵·네이버 지도 링크를 넣어 주세요"),
    "UNSUPPORTED_LINK": (422, "Google 지도·카카오맵·네이버 지도 링크만 넣을 수 있어요"),
    "LINK_UNRESOLVED": (422, "링크를 확인하지 못했어요. 다른 링크를 넣어 주세요"),
    "STORE_NOT_FOUND": (422, "가게를 찾지 못했어요. 다른 지도 링크를 넣어 주세요"),
    "NOT_TARGET_CATEGORY": (422, "지금은 음식점·카페·바만 진단할 수 있어요"),
    "FIX_IN_PROGRESS": (409, "정비가 끝나기 전에는 가게를 바꿀 수 없어요"),
    "CONFIRM_REPLACE_REQUIRED": (409, "가게를 바꾸면 지금 가게의 결과는 지난 기록으로 옮겨져요"),
    "CANDIDATE_EXPIRED": (410, "시간이 지나 다시 찾아야 해요. 링크를 다시 넣어 주세요"),
    "TRY_LATER": (503, "잠시 후 다시 시도해 주세요"),
    "RETRY_LIMIT": (429, "내일 다시 시도해 주세요"),
    "NO_STORE": (409, "먼저 가게를 등록해 주세요"),
    "NOT_ELIGIBLE": (409, "지금은 자동 정비를 신청할 수 없어요"),
    "ALREADY_REQUESTED": (409, "이 가게는 이미 자동 정비를 신청했어요"),
    "CONNECTION_NOT_CONNECTED": (409, "지도가 연결된 뒤에 승인할 수 있어요"),
    "ITEMS_MISMATCH": (400, "정비안이 바뀌었어요. 새로고침해 주세요"),
    "NEEDS_OWNER_INPUT": (400, '"확인 필요" 칸을 채우거나 빼 주세요'),
    "SENSITIVE_NOT_CONFIRMED": (400, "알레르기·할랄 정보를 확인해 주세요"),
    "FIELD_INVALID": (400, "입력한 값이 이 칸의 규칙에 맞지 않아요"),
    "REPORT_NOT_READY": (404, "보고서가 아직 준비되지 않았어요"),
    "REJECT_REASON_REQUIRED": (422, "거절 사유를 넣어 주세요"),
    "INTERNAL_ERROR": (500, "잠시 후 다시 시도해 주세요"),
}


class AppError(Exception):
    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        if code not in ERRORS:
            raise ValueError(f"unknown error code {code}")
        self.code = code
        self.status, template = ERRORS[code]
        self.details = details or {}
        provider = self.details.get("provider")
        self.message = template.format(provider=PROVIDER_LABEL.get(provider, provider or ""))
        super().__init__(code)


def error_body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


# Pydantic 오류 type → 04 2장 필드 코드
FIELD_CODE = {
    "missing": "required",
    "string_too_long": "too_long",
    "string_too_short": "required",
    "too_long": "too_long",
    "bool_type": "required",
    "literal_error": "invalid",
}
# 모델 검사(model_validator)에서 낸 오류는 loc이 비어 있어 필드 이름(camelCase)을 정해 준다
CUSTOM_FIELD = {"password_mismatch": "passwordConfirm", "terms_required": "agreeTerms"}
CUSTOM_CODES = {"invalid_email", "weak_password", "password_mismatch", "terms_required"}


def validation_fields(errors: list[dict[str, Any]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for err in errors:
        loc = [str(x) for x in err.get("loc", ()) if x not in ("body", "query", "path")]
        name = loc[-1] if loc else "_"
        t = err.get("type", "")
        if t in CUSTOM_FIELD:
            name = CUSTOM_FIELD[t]
        if t in CUSTOM_CODES:
            code = t
        elif name.lower().endswith("email") and t == "value_error":
            code = "invalid_email"
        else:
            code = FIELD_CODE.get(t, "invalid")
        fields.setdefault(name, code)
    return fields


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError) -> JSONResponse:
        return JSONResponse(error_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        status, msg = ERRORS["VALIDATION_ERROR"]
        body = error_body("VALIDATION_ERROR", msg, {"fields": validation_fields(list(e.errors()))})
        return JSONResponse(body, status_code=status)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(e).__name__)
        status, msg = ERRORS["INTERNAL_ERROR"]
        return JSONResponse(error_body("INTERNAL_ERROR", msg, {}), status_code=status)
