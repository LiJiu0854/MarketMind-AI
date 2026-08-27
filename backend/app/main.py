"""FastAPI 应用工厂。"""

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import Settings
from app.middleware.request_id import RequestIDMiddleware


def create_app() -> FastAPI:
    """创建并组装一个独立的 FastAPI 应用实例。"""
    settings = Settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(RequestIDMiddleware)
    app.include_router(health_router, prefix="/api/v1")
    return app
