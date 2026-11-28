"""운영자(관리자)의 고객 스토어·위임 확인·작업 대기 조회.

조회만 제공한다. 고객 승인을 대신하지 않는다. 실행은 기존 정비안 명령이 고객 승인 기록을 다시 검사한다.
"""

from sqlalchemy import case, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.commerce import CommercePlan, CommerceProduct, CommerceShop
from seelo.models.user import User
from seelo.services import commerce_service as service

# 운영자가 처리할 정비안 상태. draft는 고객 승인 대기라 운영자 작업에 넣지 않는다.
OPERATOR_STATUSES = {
    "approved": "execute",
    "manual_required": "manual_edit",
    "applying": "check_result",
    "uncertain": "check_result",
    "pending_reflection": "check_result",
}
CUSTOMER_STATUSES = {"draft": "customer_approval"}


def _escape(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def shops(
    db: AsyncSession,
    *,
    manager_status: str | None,
    query: str,
    page: int,
    page_size: int,
) -> dict:
    condition = true()
    if manager_status:
        condition = condition & (CommerceShop.manager_status == manager_status)
    if query.strip():
        pattern = _escape(query.strip())
        condition = condition & or_(
            CommerceShop.name.ilike(pattern, escape="\\"),
            CommerceShop.external_id.ilike(pattern, escape="\\"),
            User.email.ilike(pattern, escape="\\"),
        )
    base = select(CommerceShop, User.email).join(User, User.id == CommerceShop.owner_id).where(condition)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(
            base.order_by(
                # 초대 확인 대기를 먼저 보여 준다.
                case((CommerceShop.manager_status == "invited", 0), else_=1),
                CommerceShop.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    ids = [shop.id for shop, _ in rows]
    counts: dict[int, dict[str, int]] = {i: {"products": 0} for i in ids}
    if ids:
        for shop_id, count in await db.execute(
            select(CommerceProduct.shop_id, func.count())
            .where(CommerceProduct.shop_id.in_(ids))
            .group_by(CommerceProduct.shop_id)
        ):
            counts[shop_id]["products"] = count
        for shop_id, status, count in await db.execute(
            select(CommerceProduct.shop_id, CommercePlan.status, func.count())
            .join(CommercePlan, CommercePlan.product_id == CommerceProduct.id)
            .where(CommerceProduct.shop_id.in_(ids))
            .group_by(CommerceProduct.shop_id, CommercePlan.status)
        ):
            counts[shop_id][status] = count
    items = []
    for shop, email in rows:
        c = counts[shop.id]
        items.append(
            {
                **service.shop_view(shop),
                "ownerEmail": email,
                "work": {
                    "products": c["products"],
                    "customerApproval": c.get("draft", 0),
                    "operatorExecute": c.get("approved", 0),
                    "manualEdit": c.get("manual_required", 0),
                    "checkResult": sum(c.get(s, 0) for s in ("applying", "uncertain", "pending_reflection")),
                },
            }
        )
    invited = await db.scalar(
        select(func.count()).select_from(CommerceShop).where(CommerceShop.manager_status == "invited")
    )
    return {"shops": items, "page": page, "pageSize": page_size, "total": total or 0, "invited": invited or 0}


async def tasks(db: AsyncSession, *, limit: int = 100) -> dict:
    statuses = [*OPERATOR_STATUSES, *CUSTOMER_STATUSES]
    rows = (
        await db.execute(
            select(CommercePlan, CommerceProduct, CommerceShop, User.email)
            .join(CommerceProduct, CommerceProduct.id == CommercePlan.product_id)
            .join(CommerceShop, CommerceShop.id == CommerceProduct.shop_id)
            .join(User, User.id == CommerceShop.owner_id)
            .where(CommercePlan.status.in_(statuses))
            .order_by(CommercePlan.id.desc())
            .limit(limit)
        )
    ).all()
    items = []
    for plan, product, shop, email in rows:
        approval = plan.approval or {}
        items.append(
            {
                "planId": plan.id,
                "status": plan.status,
                "next": OPERATOR_STATUSES.get(plan.status) or CUSTOMER_STATUSES[plan.status],
                # 운영자 실행은 고객이 직접 승인한 기록이 있을 때만 가능하다.
                "customerApproved": approval.get("approvedBy") == shop.owner_id,
                "approvedFields": approval.get("fields", []),
                "productId": product.id,
                "productName": product.name,
                "productNo": product.external_id,
                "shopId": shop.id,
                "shopName": shop.name,
                "platform": shop.platform,
                "managerStatus": shop.manager_status,
                "ownerEmail": email,
                "approvedAt": plan.approved_at,
            }
        )
    return {"tasks": items}
