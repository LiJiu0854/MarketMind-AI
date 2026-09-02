"""应用异常到 HTTP 响应的转换。"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """把业务异常转换为不泄露内部信息的 JSON 响应。"""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else {}
    if exc.headers:
        headers.update(exc.headers)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request.state.request_id,
        },
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """把请求参数错误转换为稳定的 422 响应。"""
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "request_id": request.state.request_id,
        },
    )


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """把未处理的数据库异常转换为不泄密的 503 响应。"""
    return JSONResponse(
        status_code=503,
        content={
            "code": "DATABASE_UNAVAILABLE",
            "message": "数据库暂时不可用",
            "request_id": request.state.request_id,
        },
    )
