"""GET /api/health(04 9장)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.db import get_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse | JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # DB 연결 실패는 503으로 알린다
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return HealthResponse(status="ok", db="ok")
