"""商品 CRUD API 与 RBAC 测试。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.main import create_app
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def make_user(session: AsyncSession, index: int, role: Role) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"product-api-{index}@example.com",
            full_name=f"Product API User {index}",
            password=PASSWORD,
            role=role,
        ),
    )


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


def product_json() -> dict[str, object]:
    return {
        "sku": " sku-1 ",
        "title": "Product 1",
        "price": "19.90",
        "currency": "cny",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
async def test_writer_can_create_product(
    client: AsyncClient,
    session: AsyncSession,
    role: Role,
) -> None:
    actor = await make_user(session, 1, role)

    response = await client.post(
        "/api/v1/products",
        headers=auth_headers(actor),
        json=product_json(),
    )

    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-1"
    assert response.json()["created_by_id"] == actor.id


@pytest.mark.asyncio
async def test_analyst_cannot_write_but_can_read(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    analyst = await make_user(session, 2, Role.ANALYST)
    created = await client.post(
        "/api/v1/products",
        headers=auth_headers(operator),
        json=product_json(),
    )
    product_id = created.json()["id"]

    blocked = await client.patch(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(analyst),
        json={"title": "Blocked"},
    )
    read = await client.get(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(analyst),
    )

    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PERMISSION_DENIED"
    assert read.status_code == 200


@pytest.mark.asyncio
async def test_products_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/products")).status_code == 401


@pytest.mark.asyncio
async def test_writer_lists_updates_and_deactivates_product(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    headers = auth_headers(operator)
    created = await client.post(
        "/api/v1/products",
        headers=headers,
        json=product_json(),
    )
    product_id = created.json()["id"]

    listed = await client.get(
        "/api/v1/products?sku=sku-1",
        headers=headers,
    )
    updated = await client.patch(
        f"/api/v1/products/{product_id}",
        headers=headers,
        json={"title": "Updated Product"},
    )
    deactivated = await client.delete(
        f"/api/v1/products/{product_id}",
        headers=headers,
    )

    assert listed.json()["total"] == 1
    assert updated.json()["title"] == "Updated Product"
    assert deactivated.json()["is_active"] is False
