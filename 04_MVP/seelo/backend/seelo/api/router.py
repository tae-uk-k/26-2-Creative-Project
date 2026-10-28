"""/api 아래 모든 라우터(13 7장). 새 라우터 모듈은 ROUTERS에 순서대로 더한다."""

from fastapi import APIRouter, Depends

from seelo.api import (
    account,
    admin,
    auth,
    diagnosis,
    fix_connect,
    fix_plans,
    fix_requests,
    health,
    home,
    oauth,
    runs,
    stores,
)
from seelo.api.deps import load_session, verify_csrf

# 단계가 진행되면 fix_report, reports 순서로 더한다(12 작업순서).
ROUTERS = [
    health.router,
    auth.router,
    oauth.router,
    account.router,
    home.router,
    stores.router,
    runs.router,
    diagnosis.router,
    fix_requests.router,
    fix_connect.router,
    fix_plans.router,
    admin.router,
]

api_router = APIRouter(dependencies=[Depends(load_session), Depends(verify_csrf)])
for r in ROUTERS:
    api_router.include_router(r)
