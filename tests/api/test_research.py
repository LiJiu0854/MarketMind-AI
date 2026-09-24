"""Research API permissions, dispatch and history."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from kombu.exceptions import OperationalError  # type: ignore[import-untyped]
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.models.research import ResearchRun, ResearchStatus
from app.models.user import Role, User
from app.schemas.research import ResearchCreate
from app.schemas.user import UserCreate
from app.services.research import create_research_run
from app.services.users import create_user
from tests.integration.db.test_research import setup_rows

JWT_SECRET = "research-test-secret-at-least-32-bytes"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


def configured_settings() -> Settings:
    return Settings(
        llm_provider="test",
        llm_model="research-model",
        llm_api_key=SecretStr("test-key"),
        embedding_provider="test",
        embedding_base_url="https://example.invalid/v1",
        embedding_model="embedding-model",
        embedding_api_key=SecretStr("test-key"),
    )


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app(configured_settings())

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as value:
        yield value


def headers(actor: User) -> dict[str, str]:
    token = create_access_token(actor.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


async def actor(session: AsyncSession, suffix: str, role: Role) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"research-api-{suffix}@example.com",
            full_name="Test",
            password="correct-horse-battery-staple",
            role=role,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
async def test_managers_create_and_dispatch(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _, product_id, base_id = await setup_rows(session, role.value)
    manager = await actor(session, role.value, role)
    sent = Mock(return_value=SimpleNamespace(id="research-task-1"))
    monkeypatch.setattr("app.api.v1.research.celery_app.send_task", sent)
    response = await client.post(
        f"/api/v1/products/{product_id}/research-runs",
        headers=headers(manager),
        json={"goal": "Compare", "knowledge_base_ids": [base_id]},
    )
    assert response.status_code == 202, response.text
    run = await session.get_one(ResearchRun, response.json()["run_id"])
    assert run.celery_task_id == "research-task-1"
    assert run.requested_by_id == manager.id
    sent.assert_called_once_with("app.tasks.research.run_research", args=[run.id])


@pytest.mark.asyncio
async def test_analyst_and_anonymous_cannot_create(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, product_id, base_id = await setup_rows(session, "forbidden")
    analyst = await actor(session, "analyst", Role.ANALYST)
    path = f"/api/v1/products/{product_id}/research-runs"
    payload = {"goal": "Compare", "knowledge_base_ids": [base_id]}
    assert (await client.post(path, json=payload)).status_code == 401
    assert (await client.post(path, json=payload, headers=headers(analyst))).status_code == 403


@pytest.mark.asyncio
async def test_missing_rows_unready_and_duplicate_are_rejected(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "invalid-api")
    manager = await session.get_one(User, actor_id)
    authorization = headers(manager)
    sent = Mock(return_value=SimpleNamespace(id="research-task-2"))
    monkeypatch.setattr("app.api.v1.research.celery_app.send_task", sent)
    payload = {"goal": "Compare", "knowledge_base_ids": [base_id]}
    path = f"/api/v1/products/{product_id}/research-runs"
    assert (
        await client.post(
            "/api/v1/products/999999/research-runs", json=payload, headers=authorization
        )
    ).status_code == 404
    assert (
        await client.post(
            path,
            json={"goal": "Compare", "knowledge_base_ids": [999999]},
            headers=authorization,
        )
    ).status_code == 404
    assert (await client.post(path, json=payload, headers=authorization)).status_code == 202
    assert (await client.post(path, json=payload, headers=authorization)).status_code == 409
    assert sent.call_count == 1


@pytest.mark.asyncio
async def test_dispatch_failure_is_persisted(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "broker")
    manager = await session.get_one(User, actor_id)
    monkeypatch.setattr(
        "app.api.v1.research.celery_app.send_task",
        Mock(side_effect=OperationalError("private broker detail")),
    )
    response = await client.post(
        f"/api/v1/products/{product_id}/research-runs",
        json={"goal": "Compare", "knowledge_base_ids": [base_id]},
        headers=headers(manager),
    )
    assert response.status_code == 503
    run = await session.scalar(select(ResearchRun).where(ResearchRun.product_id == product_id))
    assert run is not None
    assert run.status is ResearchStatus.FAILURE
    assert "private broker detail" not in (run.error_message or "")


@pytest.mark.asyncio
async def test_history_readable_to_all_roles_but_product_scoped(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "history-api")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        configured_settings(),
    )
    for role in (Role.ADMIN, Role.OPERATOR, Role.ANALYST):
        reader = await actor(session, f"reader-{role.value}", role)
        listed = await client.get(
            f"/api/v1/products/{product_id}/research-runs", headers=headers(reader)
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        detail = await client.get(
            f"/api/v1/products/{product_id}/research-runs/{run.id}", headers=headers(reader)
        )
        assert detail.status_code == 200
        assert detail.json()["product_snapshot"]["title"] == "Original title"
        wrong = await client.get(
            f"/api/v1/products/{product_id + 999}/research-runs/{run.id}",
            headers=headers(reader),
        )
        assert wrong.status_code == 404
