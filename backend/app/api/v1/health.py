"""健康检查路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.errors import AppError
from app.db.redis import get_redis
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/live", response_model=HealthResponse, summary="存活检查")
async def live_health() -> HealthResponse:
    """确认 API 进程能够正常响应请求。"""
    return HealthResponse(status="ok", service="MarketMind AI")


@router.get("/ready", response_model=HealthResponse, summary="准备检查")
async def ready_health(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> HealthResponse:
    """确认 API 进程是否准备就绪。"""
    await session.execute(text("SELECT 1"))
    try:
        await redis.ping()
    except RedisError as exc:
        raise AppError(
            code="REDIS_UNAVAILABLE",
            message="Redis 暂时不可用",
            status_code=503,
        ) from exc

    return HealthResponse(status="ok", service="MarketMind AI")
