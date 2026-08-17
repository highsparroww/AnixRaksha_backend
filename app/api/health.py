from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.realtime.redis_bus import redis_bus

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/health/redis")
async def health_redis():
    ok = await redis_bus.ping()
    return {"status": "ok" if ok else "error"}


@router.get("/health/ml")
async def health_ml(request: Request):
    return await request.app.state.prediction_registry.service.health()
