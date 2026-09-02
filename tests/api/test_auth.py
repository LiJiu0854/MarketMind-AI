"""登录与当前用户 API 测试。"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.db.redis import get_redis
from app.main import create_app
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """为 API 测试提供独立 JWT 密钥。"""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest.fixture
def redis_client() -> AsyncMock:
    client = AsyncMock()
    client.eval.return_value = [1, 60]
    return client


@pytest_asyncio.fixture
async def client(
    session: AsyncSession,
    redis_client: AsyncMock,
) -> AsyncIterator[AsyncClient]:
    """覆盖生产 Session 依赖，所有请求只访问测试库。"""
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client


async def create_test_user(session: AsyncSession, *, active: bool = True) -> User:
    """创建登录测试用户。"""
    user = await create_user(
        session,
        UserCreate(
            email="login@example.com",
            full_name="Login User",
            password="correct-horse-battery-staple",
            role=Role.ANALYST,
        ),
    )
    if not active:
        user.is_active = False
        await session.commit()
    return user


@pytest.mark.asyncio
async def test_login_returns_bearer_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    """正确邮箱密码应返回可以使用的 Bearer Token。"""
    await create_test_user(session)

    response = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "LOGIN@EXAMPLE.COM",
            "password": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert isinstance(response.json()["access_token"], str)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("missing@example.com", "wrong-password"),
        ("login@example.com", "wrong-password"),
    ],
)
async def test_login_rejects_bad_credentials_with_same_401(
    client: AsyncClient,
    session: AsyncSession,
    username: str,
    password: str,
) -> None:
    """错误邮箱与错误密码不得泄露账号是否存在。"""
    await create_test_user(session)

    response = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_rejects_inactive_account(
    client: AsyncClient, session: AsyncSession
) -> None:
    """已停用账号即使密码正确也不能获得 Token。"""
    await create_test_user(session, active=False)

    response = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "login@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_INACTIVE"


@pytest.mark.asyncio
async def test_login_rate_limit_returns_retry_after(
    client: AsyncClient,
    redis_client: AsyncMock,
) -> None:
    redis_client.eval.return_value = [6, 42]

    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "login@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json()["code"] == "LOGIN_RATE_LIMITED"


@pytest.mark.asyncio
async def test_login_rejects_when_rate_limit_redis_is_unavailable(
    client: AsyncClient,
    redis_client: AsyncMock,
) -> None:
    redis_client.eval.side_effect = RedisError("down")

    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "login@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_me_returns_safe_current_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    """有效 Token 应返回当前用户且不泄露密码哈希。"""
    user = await create_test_user(session)
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert "password_hash" not in response.json()


@pytest.mark.asyncio
async def test_me_rejects_missing_token(client: AsyncClient) -> None:
    """没有 Bearer Token 时必须返回 401。"""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_me_rejects_expired_token(client: AsyncClient) -> None:
    """过期 Token 必须通过业务异常响应为 401。"""
    token = create_access_token(1, SecretStr(JWT_SECRET), -1)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "AUTH_INVALID_TOKEN"
