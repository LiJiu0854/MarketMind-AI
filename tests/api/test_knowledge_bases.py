"""Knowledge-base management and RBAC HTTP tests."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "rag-api-test-secret-with-32-bytes"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(
            embedding_provider="test",
            embedding_base_url="https://provider.invalid/v1",
            embedding_model="embedding-test",
            embedding_api_key=SecretStr("test-only-key"),
        )
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def make_actor(session: AsyncSession, role: Role, suffix: str) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"rag-api-{suffix}@example.com",
            full_name="RAG API",
            password="correct-horse-battery-staple",
            role=role,
        ),
    )


def auth_headers(actor: User) -> dict[str, str]:
    token = create_access_token(actor.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_creates_knowledge_base_and_receives_201(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "admin")
    response = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "  Policies  ", "description": "  Team docs  "},
        headers=auth_headers(actor),
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Policies"
    assert response.json()["embedding_model"] == "embedding-test"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
async def test_non_admin_cannot_create_knowledge_base(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    actor = await make_actor(session, role, role.value)
    response = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Forbidden"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_can_list_and_read_knowledge_bases(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    admin = await make_actor(session, Role.ADMIN, f"create-{role.value}")
    created = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": f"Policy {role.value}"},
        headers=auth_headers(admin),
    )
    actor = await make_actor(session, role, f"read-{role.value}")
    base_id = created.json()["id"]

    listing = await client.get("/api/v1/knowledge-bases", headers=auth_headers(actor))
    detail = await client.get(
        f"/api/v1/knowledge-bases/{base_id}", headers=auth_headers(actor)
    )
    documents = await client.get(
        f"/api/v1/knowledge-bases/{base_id}/documents", headers=auth_headers(actor)
    )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == base_id
    assert detail.status_code == 200
    assert detail.json()["id"] == base_id
    assert documents.status_code == 200
    assert documents.json()["total"] == 0


@pytest.mark.asyncio
async def test_duplicate_name_returns_stable_409(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "duplicate")
    headers = auth_headers(actor)
    first = await client.post("/api/v1/knowledge-bases", json={"name": "Same"}, headers=headers)
    second = await client.post("/api/v1/knowledge-bases", json={"name": "Same"}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "KNOWLEDGE_BASE_NAME_EXISTS"


@pytest.mark.asyncio
async def test_missing_base_returns_stable_404(client: AsyncClient, session: AsyncSession) -> None:
    actor = await make_actor(session, Role.ANALYST, "missing")
    response = await client.get(
        "/api/v1/knowledge-bases/999999", headers=auth_headers(actor)
    )
    assert response.status_code == 404
    assert response.json()["code"] == "KNOWLEDGE_BASE_NOT_FOUND"


@pytest.mark.asyncio
async def test_unauthenticated_management_request_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/knowledge-bases")).status_code == 401
