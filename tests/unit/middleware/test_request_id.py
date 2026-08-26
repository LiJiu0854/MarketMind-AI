"""请求 ID 中间件测试。"""

from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def create_test_app() -> FastAPI:
    """创建只用于观察 request.state 的真实 FastAPI 应用。"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/request-id")
    async def read_request_id(request: Request) -> dict[str, str]:
        return {"request_id": cast(str, request.state.request_id)}

    return app


@pytest.mark.asyncio
async def test_missing_request_id_generates_uuid_and_shares_it_with_state() -> None:
    """复用固定值或未同步 state、响应头时应失败。"""
    transport = ASGITransport(app=create_test_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/request-id")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.status_code == 200
    assert UUID(request_id).version == 4
    assert response.json() == {"request_id": request_id}


@pytest.mark.asyncio
async def test_provided_request_id_is_preserved_everywhere() -> None:
    """客户端 ID 被替换或未同步 state、响应头时应失败。"""
    client_request_id = "client-request-123"
    transport = ASGITransport(app=create_test_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/request-id",
            headers={REQUEST_ID_HEADER: client_request_id},
        )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == client_request_id
    assert response.json() == {"request_id": client_request_id}


@pytest.mark.asyncio
async def test_request_id_different_for_each_request() -> None:
    """连续发送两个未携带 X-Request-ID 的请求时，响应头中的两个 ID 不相同。"""
    transport = ASGITransport(app=create_test_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response1 = await client.get("/request-id")
        response2 = await client.get("/request-id")

    assert response1.headers[REQUEST_ID_HEADER] != response2.headers[REQUEST_ID_HEADER]
