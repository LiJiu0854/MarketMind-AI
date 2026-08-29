"""FastAPI 应用工厂。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router
from app.core.config import Settings
from app.core.errors import AppError
from app.core.exception_handlers import (
    app_error_handler,
    database_error_handler,
    validation_error_handler,
)
from app.middleware.request_id import RequestIDMiddleware


def create_app() -> FastAPI:
    """创建并组装一个独立的 FastAPI 应用实例。"""
    settings = Settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        validation_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        SQLAlchemyError,
        database_error_handler,  # type: ignore[arg-type]
    )
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    return app
