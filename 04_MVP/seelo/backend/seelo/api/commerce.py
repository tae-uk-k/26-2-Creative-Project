"""스마트스토어·카페24 전용 API. 기존 로그인·CSRF·계정 권한을 사용한다."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.api.deps import require_admin, require_user
from seelo.config import get_settings
from seelo.db import get_db
from seelo.domain import commerce as rules
from seelo.errors import AppError
from seelo.models.commerce import (
    CommerceJob,
    CommerceMeasureRun,
    CommerceMeasureSet,
    CommercePlan,
    CommerceProduct,
    CommerceShop,
    CommerceWrite,
)
from seelo.models.user import User
from seelo.schemas import commerce as schema
from seelo.services import commerce_jobs as jobs_service
from seelo.services import commerce_measure as measure
from seelo.services import commerce_operator as operator
from seelo.services import commerce_service as service


async def check_ownership(
    request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> None:
    # 다른 판매자 ID는 본문 형식 검사보다 먼저 거부한다.
    params = request.path_params
    try:
        if "shop_id" in params:
            await service.owned_shop(db, user, int(params["shop_id"]))
        elif "product_id" in params:
            await service.owned_product(db, user, int(params["product_id"]))
        elif "plan_id" in params:
            await service.owned_plan(db, user, int(params["plan_id"]))
        elif "set_id" in params:
            await measure.owned_set(db, user, int(params["set_id"]))
        elif "run_id" in params:
            await measure.owned_run(db, user, int(params["run_id"]))
        elif "job_id" in params:
            job = await db.get(CommerceJob, int(params["job_id"]))
            if job is None:
                raise AppError("NOT_FOUND")
            await service.owned_shop(db, user, job.shop_id, lock=False)
    except ValueError as error:
        raise AppError("NOT_FOUND") from error


router = APIRouter(prefix="/commerce", tags=["쇼핑몰"], dependencies=[Depends(check_ownership)])


@router.get("/capabilities")
async def capabilities(user: User = Depends(require_user)) -> dict:
    mode = get_settings().commerce_edit_mode
    return {
        "editingMode": mode,
        "platforms": [
            {
                "platform": "cafe24",
                "fields": sorted(rules.FIELDS["cafe24"]),
                "fieldSupport": service.support_for("cafe24", mode),
                "apiAuthorization": "oauth",
                "managerPermission": "suboperator_product_only",
            },
            {
                "platform": "smartstore",
                "fields": sorted(rules.FIELDS["smartstore"]),
                "fieldSupport": service.support_for("smartstore", mode),
                "apiAuthorization": "official_solution_seller",
                "managerPermission": "agency_manager",
                "manualFields": sorted(rules.MANUAL_FIELDS["smartstore"]),
                "editorConversionNeedsApproval": mode == "api",
            },
        ],
    }


@router.get("/operator/shops")
async def operator_shops(
    manager_status: str | None = Query(
        default=None, alias="managerStatus", pattern="^(not_requested|invited|verified|revoked)$"
    ),
    query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """운영자용 전체 고객 스토어. 초대 확인 대기를 먼저 보여 준다."""
    return await operator.shops(
        db, manager_status=manager_status, query=query, page=page, page_size=page_size
    )


@router.get("/operator/tasks")
async def operator_tasks(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    """고객 승인 대기와 운영자 실행·결과 확인이 필요한 정비안."""
    return await operator.tasks(db)


@router.post("/shops", status_code=201)
async def register(
    body: schema.ShopCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    return await service.register(db, user, body)


@router.get("/shops")
async def shops(db: AsyncSession = Depends(get_db), user: User = Depends(require_user)) -> dict:
    rows = await db.scalars(
        select(CommerceShop).where(CommerceShop.owner_id == user.id).order_by(CommerceShop.id).limit(100)
    )
    return {"shops": [service.shop_view(row) for row in rows]}


@router.get("/shops/{shop_id}")
async def shop(shop_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)) -> dict:
    return service.shop_view(await service.owned_shop(db, user, shop_id, lock=False))


@router.post("/shops/{shop_id}/manager")
async def manager(
    shop_id: int,
    body: schema.ManagerStatus,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.manager_status(
        db, user, shop_id, body.status, store_name=body.store_name, store_id=body.store_id
    )


@router.post("/shops/{shop_id}/cafe24/authorize")
async def cafe_authorize(
    shop_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    return await service.cafe_start(db, user, shop_id)


@router.get("/cafe24/callback", response_model=None)
async def cafe_callback(
    request: Request,
    state: str = Query(max_length=200),
    code: str = Query(max_length=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict | RedirectResponse:
    result = await service.cafe_callback(db, user, state, code)
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(f"/stores/{result['id']}/products", status_code=303)
    return result


@router.post("/shops/{shop_id}/smartstore/seller")
async def seller(
    shop_id: int,
    body: schema.SellerLink,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    return await service.link_seller(db, admin, shop_id, body)


@router.post("/shops/{shop_id}/disconnect")
async def disconnect(
    shop_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    return await service.disconnect(db, user, shop_id)


@router.post("/shops/{shop_id}/products/import", status_code=201, response_model=None)
async def collect(
    shop_id: int,
    body: schema.ProductImport,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict | JSONResponse:
    shop = await service.owned_shop(db, user, shop_id, lock=False)
    product_no = service.product_number(shop, body)
    kind, view = await service.request_collect(db, user, shop_id, product_no)
    if kind == "job":
        # 브라우저 수집은 worker가 실행한다. 화면은 작업 상태를 조회한 뒤 상품으로 이동한다.
        return JSONResponse(status_code=202, content=jsonable_encoder({"job": view}))
    return view


@router.post("/shops/{shop_id}/products/manual-snapshot", status_code=201)
async def manual_snapshot(
    shop_id: int,
    body: schema.ManualSnapshot,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    row = await service.owned_shop(db, user, shop_id)
    service.owner(row, user)
    rules.check_fields(row.platform, body.fields)
    return await service.save_snapshot(
        db,
        user,
        row,
        body.external_id,
        body.name,
        body.identity,
        body.fields,
        {"fields": body.fields},
        "seller_supplied",
    )


@router.get("/shops/{shop_id}/products")
async def products(
    shop_id: int,
    query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """seelo에 가져온 상품만 검색한다. 플랫폼의 전체 상품 목록이 아니다."""
    shop = await service.owned_shop(db, user, shop_id, lock=False)
    condition = CommerceProduct.shop_id == shop_id
    text = query.strip()
    if text:
        pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        condition = condition & or_(
            CommerceProduct.name.ilike(pattern, escape="\\"),
            CommerceProduct.external_id.ilike(pattern, escape="\\"),
            CommerceProduct.identity.ilike(pattern, escape="\\"),
        )
    total = await db.scalar(select(func.count()).select_from(CommerceProduct).where(condition))
    rows = await db.scalars(
        select(CommerceProduct)
        .where(condition)
        .order_by(CommerceProduct.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "products": [service.product_view(row, shop) for row in rows],
        "page": page,
        "pageSize": page_size,
        "total": total or 0,
        "scope": "imported",
    }


@router.post("/shops/{shop_id}/catalog", response_model=None)
async def request_catalog(
    shop_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict | JSONResponse:
    """위임받은 관리 화면에서 플랫폼 상품 목록을 읽는다. 가져온 상품 목록과 다르다."""
    kind, view = await service.request_catalog(db, user, shop_id)
    if kind == "job":
        return JSONResponse(status_code=202, content=jsonable_encoder({"job": view}))
    return view


@router.get("/shops/{shop_id}/catalog")
async def latest_catalog(
    shop_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    shop = await service.owned_shop(db, user, shop_id, lock=False)
    job = await db.scalar(
        select(CommerceJob)
        .where(
            CommerceJob.shop_id == shop_id, CommerceJob.kind == "catalog", CommerceJob.status == "succeeded"
        )
        .order_by(CommerceJob.id.desc())
        .limit(1)
    )
    return await service.catalog_view(db, shop, job.result if job else None)


@router.get("/products/{product_id}")
async def product(
    product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    shop, row = await service.owned_product(db, user, product_id)
    prepare_job = await db.scalar(
        select(CommerceJob)
        .where(CommerceJob.product_id == product_id, CommerceJob.kind == "prepare")
        .order_by(CommerceJob.id.desc())
        .limit(1)
    )
    # 마지막 AI 준비 작업. 원본 수집 뒤 자동으로 조사·필요 정보 판단·정비안 생성을 이어 간다.
    return {**service.product_view(row, shop), "prepareJob": jobs_service.job_view(prepare_job)}


@router.post("/products/{product_id}/prepare", response_model=None)
async def prepare(
    product_id: int,
    body: schema.PrepareInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict | JSONResponse:
    kind, view = await service.request_prepare(db, user, product_id, body)
    if kind == "job":
        return JSONResponse(status_code=202, content=jsonable_encoder({"job": view}))
    return {"result": view}


@router.post("/products/{product_id}/facts")
async def facts(
    product_id: int,
    body: schema.FactsInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.facts(db, user, product_id, body)


@router.post("/products/{product_id}/research")
async def research(
    product_id: int,
    body: schema.ResearchInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.research(db, user, product_id, body)


@router.post("/products/{product_id}/answers")
async def answers(
    product_id: int,
    body: schema.AnswerInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.answers(db, user, product_id, body)


@router.post("/products/{product_id}/plans", status_code=201)
async def generate(
    product_id: int,
    body: schema.PlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.generate(db, user, product_id, body)


@router.get("/products/{product_id}/plans")
async def plans(
    product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    await service.owned_product(db, user, product_id)
    rows = await db.scalars(
        select(CommercePlan)
        .where(CommercePlan.product_id == product_id)
        .order_by(CommercePlan.id.desc())
        .limit(50)
    )
    return {"plans": await service.plan_views(db, list(rows))}


@router.get("/plans/{plan_id}")
async def plan(plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)) -> dict:
    _, _, row = await service.owned_plan(db, user, plan_id)
    return (await service.plan_views(db, [row]))[0]


@router.post("/plans/{plan_id}/approve")
async def approve(
    plan_id: int,
    body: schema.PlanApprove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await service.approve(db, user, plan_id, body)


async def plan_job(db: AsyncSession, user: User, plan_id: int, kind: str) -> dict | JSONResponse:
    queued, view = await service.request_plan_job(db, user, plan_id, kind)
    if queued:
        return JSONResponse(status_code=202, content=jsonable_encoder(view))
    return view


@router.post("/plans/{plan_id}/apply", response_model=None)
async def apply(
    plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict | JSONResponse:
    return await plan_job(db, user, plan_id, "apply")


@router.post("/plans/{plan_id}/rollback", response_model=None)
async def rollback(
    plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict | JSONResponse:
    return await plan_job(db, user, plan_id, "rollback")


@router.post("/plans/{plan_id}/verify", response_model=None)
async def verify(
    plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict | JSONResponse:
    return await plan_job(db, user, plan_id, "verify")


@router.post("/products/{product_id}/measure-sets", status_code=201)
async def create_measure_set(
    product_id: int,
    body: schema.MeasureSetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    return await measure.create_set(db, user, product_id, body)


@router.get("/products/{product_id}/measure-sets")
async def measure_sets(
    product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    await service.owned_product(db, user, product_id)
    rows = await db.scalars(
        select(CommerceMeasureSet)
        .where(CommerceMeasureSet.product_id == product_id)
        .order_by(CommerceMeasureSet.id.desc())
        .limit(20)
    )
    return {"sets": [measure.set_view(row) for row in rows]}


@router.post("/measure-sets/{set_id}/runs", status_code=202)
async def create_measure_run(
    set_id: int,
    body: schema.MeasureRunCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """같은 질문 세트·조건으로 측정한다. 호출 실패는 노출 0이 아니라 무효로 남긴다."""
    return await measure.request_run(db, user, set_id, body)


@router.get("/products/{product_id}/measure-runs")
async def measure_runs(
    product_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    await service.owned_product(db, user, product_id)
    rows = await db.scalars(
        select(CommerceMeasureRun)
        .where(CommerceMeasureRun.product_id == product_id)
        .order_by(CommerceMeasureRun.id.desc())
        .limit(50)
    )
    return {"runs": [await measure.run_view(db, row) for row in rows]}


@router.get("/measure-runs/{run_id}")
async def measure_run(
    run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    return await measure.run_view(db, await measure.owned_run(db, user, run_id), answers=True)


@router.get("/measure-compare")
async def measure_compare(
    before: int = Query(ge=1),
    after: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """같은 질문 세트·측정 조건의 두 회차만 비교한다."""
    return await measure.compare(db, user, before, after)


@router.get("/jobs/{job_id}")
async def job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)) -> dict:
    row = await db.get(CommerceJob, job_id)
    return jobs_service.job_view(row)


@router.get("/shops/{shop_id}/jobs")
async def shop_jobs(
    shop_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    await service.owned_shop(db, user, shop_id, lock=False)
    rows = await db.scalars(
        select(CommerceJob).where(CommerceJob.shop_id == shop_id).order_by(CommerceJob.id.desc()).limit(limit)
    )
    return {"jobs": [jobs_service.job_view(row) for row in rows]}


@router.post("/plans/{plan_id}/manual-result")
async def manual_result(
    plan_id: int,
    body: schema.ManualResult,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    return await service.manual_result(db, admin, plan_id, body)


@router.post("/plans/{plan_id}/publication")
async def publication(
    plan_id: int,
    body: schema.PublicationCheck,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    return await service.publication(db, admin, plan_id, body)


@router.get("/plans/{plan_id}/writes")
async def writes(
    plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    await service.owned_plan(db, user, plan_id)
    rows = await db.scalars(
        select(CommerceWrite).where(CommerceWrite.plan_id == plan_id).order_by(CommerceWrite.id).limit(100)
    )
    return {
        "writes": [
            {
                "id": r.id,
                "planId": r.plan_id,
                "action": r.action,
                "status": r.status,
                "before": r.before,
                "after": r.after,
                "errorCode": r.error_code,
                "createdAt": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/plans/{plan_id}/instructions")
async def instructions(
    plan_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_user)
) -> dict:
    shop, product, row = await service.owned_plan(db, user, plan_id)
    if row.status not in {"approved", "manual_required", "manual_recorded", "applied"}:
        raise AppError("INVALID_STATE")
    return {
        "platform": shop.platform,
        "productNo": product.external_id,
        "changes": service.approved_changes(row),
        "managerStatus": shop.manager_status,
        "apiStatus": shop.api_status,
    }
