"""健康检查 API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.middleware.request_id import REQUEST_ID_HEADER


@pytest.mark.asyncio
async def test_live_health_returns_contract_and_request_id() -> None:
    """健康响应字段、状态码或请求 ID 集成损坏时应失败。"""
    request_id = "health-test-request"
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/health/live",
            headers={REQUEST_ID_HEADER: request_id},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MarketMind AI"}
    assert response.headers[REQUEST_ID_HEADER] == request_id


@pytest.mark.asyncio
async def test_docs_are_available() -> None:
    """应用工厂关闭或错误配置接口文档时应失败。"""
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ready_health_returns_ok() -> None:
    """就绪检查响应不符合公开契约时应失败。"""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MarketMind AI",
    }
