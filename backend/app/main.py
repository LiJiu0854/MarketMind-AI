"""FastAPI 应用工厂。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.users import router as users_router
from app.core.config import Settings
from app.core.errors import AppError
from app.core.exception_handlers import (
    app_error_handler,
    database_error_handler,
    validation_error_handler,
)
from app.db.redis import close_redis_client, create_redis_client
from app.middleware.request_id import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings

    if settings.redis_url is not None:
        app.state.redis = create_redis_client(settings.redis_url)
    else:
        app.state.redis = None

    try:
        yield
    finally:
        if app.state.redis is not None:
            await close_redis_client(app.state.redis)


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建并组装一个独立的 FastAPI 应用实例。"""
    resolver_settings = settings or Settings()

    app = FastAPI(
        title=resolver_settings.app_name,
        version=resolver_settings.app_version,
        lifespan=lifespan,
    )

    app.state.settings = resolver_settings

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
    app.include_router(tasks_router, prefix="/api/v1")
    return app
