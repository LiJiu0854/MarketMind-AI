"""Admin 用户管理 API 测试。"""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.users as users_api
from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.db.redis import get_redis
from app.main import create_app
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.users import create_user, list_users

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest.fixture
def redis_client() -> AsyncMock:
    client = AsyncMock()
    client.get.return_value = None
    client.set.return_value = True
    client.eval.return_value = 1
    return client


@pytest_asyncio.fixture
async def client(
    session: AsyncSession,
    redis_client: AsyncMock,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_redis] = lambda: redis_client

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def make_user(session: AsyncSession, index: int, role: Role) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"user-{index}@example.com",
            full_name=f"User {index}",
            password=PASSWORD,
            role=role,
        ),
    )


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


class TestAdminUserReads:
    """单元 2：创建、列表、读取和路由级 RBAC。"""

    @pytest.mark.asyncio
    async def test_admin_creates_safe_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)

        response = await client.post(
            "/api/v1/users",
            headers={
                **auth_headers(admin),
                "Idempotency-Key": "create-safe-user",
            },
            json={
                "email": "NEW@EXAMPLE.COM",
                "full_name": "New User",
                "password": PASSWORD,
                "role": "analyst",
            },
        )

        assert response.status_code == 201
        assert response.json()["email"] == "new@example.com"
        assert "password_hash" not in response.json()

    @pytest.mark.asyncio
    async def test_admin_lists_users_with_pagination(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        await make_user(session, 2, Role.ANALYST)

        response = await client.get(
            "/api/v1/users?page=1&page_size=1",
            headers=auth_headers(admin),
        )

        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert len(response.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_admin_reads_user_by_id(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        target = await make_user(session, 2, Role.ANALYST)

        response = await client.get(
            f"/api/v1/users/{target.id}", headers=auth_headers(admin)
        )

        assert response.status_code == 200
        assert response.json()["id"] == target.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
    async def test_non_admin_cannot_access_users(
        self, client: AsyncClient, session: AsyncSession, role: Role
    ) -> None:
        user = await make_user(session, 1, role)

        response = await client.get("/api/v1/users", headers=auth_headers(user))

        assert response.status_code == 403
        assert response.json()["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_admin_cannot_create_duplicate_email(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        await make_user(session, 2, Role.ANALYST)

        response = await client.post(
            "/api/v1/users",
            headers={
                **auth_headers(admin),
                "Idempotency-Key": "create-duplicate-user",
            },
            json={
                "email": "USER-2@EXAMPLE.COM",
                "full_name": "Duplicate User",
                "password": PASSWORD,
                "role": "operator",
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "USER_EMAIL_CONFLICT"

    @pytest.mark.asyncio
    async def test_create_user_requires_idempotency_key(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)

        response = await client.post(
            "/api/v1/users",
            headers=auth_headers(admin),
            json={
                "email": "new@example.com",
                "full_name": "New User",
                "password": PASSWORD,
                "role": "analyst",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_same_idempotent_request_replays_without_second_insert(
        self,
        client: AsyncClient,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        begin = AsyncMock(return_value=None)
        complete = AsyncMock()
        monkeypatch.setattr(users_api, "begin_idempotent_request", begin)
        monkeypatch.setattr(users_api, "complete_idempotent_request", complete)
        headers = {**auth_headers(admin), "Idempotency-Key": "same-request-key"}
        payload = {
            "email": "new@example.com",
            "full_name": "New User",
            "password": PASSWORD,
            "role": "analyst",
        }

        first = await client.post("/api/v1/users", headers=headers, json=payload)
        begin.return_value = json.dumps(first.json())
        second = await client.post("/api/v1/users", headers=headers, json=payload)

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json() == first.json()
        assert (await list_users(session, 1, 100)).total == 2

    @pytest.mark.asyncio
    async def test_create_user_rejects_when_idempotency_redis_is_unavailable(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client: AsyncMock,
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        redis_client.set.side_effect = RedisError("down")

        response = await client.post(
            "/api/v1/users",
            headers={**auth_headers(admin), "Idempotency-Key": "redis-down-key"},
            json={
                "email": "new@example.com",
                "full_name": "New User",
                "password": PASSWORD,
                "role": "analyst",
            },
        )

        assert response.status_code == 503
        assert response.json()["code"] == "IDEMPOTENCY_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_users_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/users")

        assert response.status_code == 401


class TestAdminUserWrites:
    """单元 3：部分更新、重新启用与软停用。"""

    @pytest.mark.asyncio
    async def test_admin_partially_updates_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client: AsyncMock,
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        target = await make_user(session, 2, Role.ANALYST)

        response = await client.patch(
            f"/api/v1/users/{target.id}",
            headers=auth_headers(admin),
            json={"full_name": "Updated User", "role": "operator"},
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated User"
        assert response.json()["role"] == "operator"
        redis_client.delete.assert_awaited_once_with(
            f"marketmind:user:v1:{target.id}"
        )

    @pytest.mark.asyncio
    async def test_admin_reactivates_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        target = await make_user(session, 2, Role.ANALYST)
        target.is_active = False
        await session.commit()

        response = await client.patch(
            f"/api/v1/users/{target.id}",
            headers=auth_headers(admin),
            json={"is_active": True},
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_admin_soft_deletes_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client: AsyncMock,
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)
        target = await make_user(session, 2, Role.ANALYST)

        response = await client.delete(
            f"/api/v1/users/{target.id}", headers=auth_headers(admin)
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False
        assert await session.get(User, target.id) is target
        redis_client.delete.assert_awaited_once_with(
            f"marketmind:user:v1:{target.id}"
        )

    @pytest.mark.asyncio
    async def test_admin_cannot_deactivate_self(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)

        response = await client.delete(
            f"/api/v1/users/{admin.id}", headers=auth_headers(admin)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "USER_SELF_DEACTIVATE_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_admin_cannot_change_own_role(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        admin = await make_user(session, 1, Role.ADMIN)

        response = await client.patch(
            f"/api/v1/users/{admin.id}",
            headers=auth_headers(admin),
            json={"role": "analyst"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "USER_SELF_ROLE_CHANGE_FORBIDDEN"
