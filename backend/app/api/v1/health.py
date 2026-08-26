"""健康检查路由。"""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/live", response_model=HealthResponse, summary="存活检查")
async def live_health() -> HealthResponse:
    """确认 API 进程能够正常响应请求。"""
    return HealthResponse(status="ok", service="MarketMind AI")
