from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import AppError
from app.db.redis import close_redis_client, create_redis_client, get_redis
from app.main import create_app


def make_request(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


def test_create_redis_client_decodes_responses() -> None:
    client = create_redis_client(SecretStr("redis://127.0.0.1:6379/0"))

    assert isinstance(client, Redis)
    assert client.connection_pool.connection_kwargs["decode_responses"] is True


@pytest.mark.asyncio
async def test_close_redis_client_closes_pool() -> None:
    client = AsyncMock()

    await close_redis_client(client)

    client.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_creates_and_closes_one_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock()
    create_client = Mock(return_value=client)
    close_client = AsyncMock()
    monkeypatch.setattr("app.main.create_redis_client", create_client)
    monkeypatch.setattr("app.main.close_redis_client", close_client)
    settings = Settings(redis_url=SecretStr("redis://127.0.0.1:6379/0"))
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert app.state.redis is client

    create_client.assert_called_once_with(settings.redis_url)
    close_client.assert_awaited_once_with(client)


def test_get_redis_returns_app_client() -> None:
    app = FastAPI()
    client = object()
    app.state.redis = client

    assert get_redis(make_request(app)) is client


def test_get_redis_rejects_missing_client() -> None:
    app = FastAPI()
    app.state.redis = None

    with pytest.raises(AppError) as error:
        get_redis(make_request(app))

    assert error.value.code == "REDIS_NOT_CONFIGURED"
    assert error.value.status_code == 503