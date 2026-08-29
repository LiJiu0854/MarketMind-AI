"""应用异常到 HTTP 响应的转换。"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """把业务异常转换为不泄露内部信息的 JSON 响应。"""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request.state.request_id,
        },
        headers=headers,
    )
