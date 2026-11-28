"""/api/admin(04 8장, A01). 모두 관리자만(아니면 403 FORBIDDEN).

신청 목록·상세·승인·거절(9단계), 연결 확인(10단계), 정비안 다시 생성(11단계), 처리 완료·수동 칸 목록(12단계).
보고서 다시 생성·지금 재측정(14단계).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_admin
from seelo.db import get_db
from seelo.models.user import User
from seelo.schemas.admin import (
    AdminFilter,
    AdminListItem,
    AdminRequestDetail,
    ManualDoneRequest,
    ManualItem,
    RejectRequest,
    StatusResponse,
    VerifyConnectionRequest,
)
from seelo.schemas.common import Page
from seelo.schemas.run import RunIdResponse
from seelo.services import (
    admin_service,
    connection_service,
    fix_apply_service,
    fix_plan_service,
    fix_request_service,
    remeasure_service,
    report_service,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/fix-requests", response_model=Page[AdminListItem])
async def list_requests(
    db: AsyncSession = Depends(get_db),
    filter_: Annotated[AdminFilter | None, Query(alias="filter")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> Page[AdminListItem]:
    return await admin_service.list_requests(db, filter_, page, page_size)


@router.get("/fix-requests/{request_id}", response_model=AdminRequestDetail)
async def detail(request_id: int, db: AsyncSession = Depends(get_db)) -> AdminRequestDetail:
    return await admin_service.detail(db, request_id)


@router.post("/fix-requests/{request_id}/approve", response_model=StatusResponse)
async def approve(
    request_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> StatusResponse:
    """E9. 처리된 신청이면 409 INVALID_STATE."""
    return await fix_request_service.approve(db, admin, request_id)


@router.post("/fix-requests/{request_id}/reject", response_model=StatusResponse)
async def reject(
    request_id: int,
    body: RejectRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """E10. 빈 사유는 422 REJECT_REASON_REQUIRED."""
    return await fix_request_service.reject(db, admin, request_id, body.reason)


@router.post("/connections/{connection_id}/verify", responses={200: {"model": StatusResponse}, 202: {}})
async def verify_connection(
    connection_id: int,
    body: VerifyConnectionRequest | None = Body(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """09 5장. 본문 manualResult가 있으면 바로 처리(200 {status}, 수동 확인 모드).
    없으면 verifyConnection 작업 등록(202 {}). AUTO_FIX_ENABLED=false인데 본문이 없으면 422."""
    status, payload = await connection_service.admin_verify(
        db, admin, connection_id, body or VerifyConnectionRequest()
    )
    return JSONResponse(payload, status_code=status)


@router.post("/fix-plans/{plan_id}/regenerate", status_code=202)
async def regenerate_plan(
    plan_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    """E23. generation_failed 정비안만(아니면 409). 칸이 없으면 지금 값 읽기부터."""
    await fix_plan_service.regenerate(db, admin, plan_id)
    return {}


@router.get("/manual-items", response_model=list[ManualItem])
async def manual_items(db: AsyncSession = Depends(get_db)) -> list[ManualItem]:
    """manual_required 칸 전체(오래된 것 먼저)."""
    return await admin_service.manual_items(db)


@router.post("/fix-logs/{fix_log_id}/manual-done", response_model=StatusResponse)
async def manual_done(
    fix_log_id: int,
    body: ManualDoneRequest | None = Body(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """E30. 관리자가 직접 고친 뒤 누른다. manual_required가 아니면 409, 없으면 404."""
    return await fix_apply_service.manual_done(db, admin, fix_log_id, body or ManualDoneRequest())


@router.post("/fix-requests/{request_id}/remeasure-now", status_code=202, response_model=RunIdResponse)
async def remeasure_now(
    request_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> RunIdResponse:
    """E20. 예약을 바로 시작하고 같은 트랜잭션에 측정·감사·작업을 등록한다."""
    return await remeasure_service.remeasure_now(db, admin, request_id)


@router.post("/fix-requests/{request_id}/report/regenerate", status_code=202)
async def regenerate_report(
    request_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    """E24. 최근 실패 보고서를 새 버전으로 만든다."""
    return await report_service.regenerate(db, admin, request_id)
