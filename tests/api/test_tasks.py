"""后台任务 API 测试。"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.db.redis import get_redis
from app.main import create_app
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "task-api-test-secret-with-32-bytes"
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
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def make_headers(session: AsyncSession, role: Role) -> dict[str, str]:
    user = await create_user(
        session,
        UserCreate(
            email=f"task-{role.value}@example.com",
            full_name=f"Task {role.value}",
            password=PASSWORD,
            role=role,
        ),
    )
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_queues_user_stats(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = Mock(return_value=SimpleNamespace(id="task-123"))
    monkeypatch.setattr("app.api.v1.tasks.generate_user_stats.delay", delay)

    response = await client.post(
        "/api/v1/tasks/user-stats",
        headers=await make_headers(session, Role.ADMIN),
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-123"}
    delay.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
async def test_non_admin_cannot_queue_user_stats(
    role: Role,
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    response = await client.post(
        "/api/v1/tasks/user-stats",
        headers=await make_headers(session, role),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_queue_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/tasks/user-stats")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_broker_failure_returns_503_without_task_id(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.tasks.generate_user_stats.delay",
        Mock(side_effect=BrokerOperationalError("broker unavailable")),
    )

    response = await client.post(
        "/api/v1/tasks/user-stats",
        headers=await make_headers(session, Role.ADMIN),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "TASK_DISPATCH_FAILED"
    assert "task_id" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["PENDING", "STARTED", "RETRY"])
async def test_task_progress_states_are_mapped_safely(
    state: str,
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = "STARTED" if state == "RETRY" else state
    monkeypatch.setattr(
        "app.api.v1.tasks.celery_app.AsyncResult",
        Mock(return_value=SimpleNamespace(state=state, result=None)),
    )

    response = await client.get(
        "/api/v1/tasks/task-123",
        headers=await make_headers(session, Role.ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["state"] == expected


@pytest.mark.asyncio
async def test_success_status_returns_json_result(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stats = {"total": 2, "active": 1, "inactive": 1}
    monkeypatch.setattr(
        "app.api.v1.tasks.celery_app.AsyncResult",
        Mock(return_value=SimpleNamespace(state="SUCCESS", result=stats)),
    )

    response = await client.get(
        "/api/v1/tasks/task-123",
        headers=await make_headers(session, Role.ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["result"] == stats


@pytest.mark.asyncio
async def test_failure_status_hides_internal_error(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_error = "mysql://user:password@production-db"
    monkeypatch.setattr(
        "app.api.v1.tasks.celery_app.AsyncResult",
        Mock(
            return_value=SimpleNamespace(
                state="FAILURE",
                result=RuntimeError(internal_error),
            )
        ),
    )

    response = await client.get(
        "/api/v1/tasks/task-123",
        headers=await make_headers(session, Role.ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["error"] == "任务执行失败"
    assert internal_error not in response.text
