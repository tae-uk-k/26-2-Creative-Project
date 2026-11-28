"""GET 방식 연결 해제 웹훅. 쿠키가 아닌 카카오 인증 헤더만 신뢰한다."""

import asyncio
import re

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.config import get_settings
from seelo.db import get_db
from seelo.services import kakao_unlink

router = APIRouter(prefix="/webhooks/kakao", tags=["webhooks"])
log = structlog.get_logger()
REFERRERS = {
    "ACCOUNT_DELETE",
    "FORCED_ACCOUNT_DELETE",
    "UNLINK_FROM_ADMIN",
    "UNLINK_FROM_APPS",
    "INCOMPLETE_SIGN_UP",
}


@router.get("/unlink", status_code=200)
async def unlink(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    settings = get_settings()
    expected = settings.kakao_unlink_admin_key_sha256.get_secret_value()
    if not expected or not settings.kakao_app_id:
        return Response(status_code=404)
    if not kakao_unlink.authorized(request.headers.get("Authorization", ""), expected):
        return Response(status_code=401)
    query = request.query_params
    valid = (
        all(len(query.getlist(key)) == 1 for key in ("app_id", "user_id", "referrer_type"))
        and query.get("app_id") == settings.kakao_app_id
        and re.fullmatch(r"[0-9]{1,20}", query.get("user_id", ""))
        and query.get("referrer_type") in REFERRERS
    )
    if not valid:
        log.warning("kakao_unlink_ignored", reason="invalid_payload")
        return Response(status_code=200)
    try:
        # 카카오 규격: 3초 내 200. 사용자 없음도 성공으로 응답한다.
        async with asyncio.timeout(2.0):
            await kakao_unlink.disconnect(db, query["user_id"])
    except Exception as error:
        await db.rollback()
        # 인증 헤더·회원번호·쿼리 원문은 로그에 넣지 않는다.
        log.error("kakao_unlink_failed", error_type=type(error).__name__)
    return Response(status_code=200)
