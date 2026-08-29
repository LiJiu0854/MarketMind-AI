"""统一 HTTP 错误边界测试。"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.main import create_app
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"


@pytest.mark.asyncio
async def test_validation_error_has_stable_contract(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    admin = await create_user(
        session,
        UserCreate(
            email="errors@example.com",
            full_name="Errors Admin",
            password="correct-horse-battery-staple",
            role=Role.ADMIN,
        ),
    )
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    token = create_access_token(admin.id, SecretStr(JWT_SECRET), 30)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/users?page=0",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["message"] == "请求参数校验失败"
    assert response.json()["request_id"]


@pytest.mark.asyncio
async def test_database_error_does_not_leak_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    app = create_app()

    async def broken_session() -> AsyncIterator[AsyncSession]:
        raise SQLAlchemyError("secret database details")
        yield

    app.dependency_overrides[get_db_session] = broken_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    token = create_access_token(1, SecretStr(JWT_SECRET), 30)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["message"] == "数据库暂时不可用"
    assert "secret database details" not in response.text
    assert response.json()["request_id"]
