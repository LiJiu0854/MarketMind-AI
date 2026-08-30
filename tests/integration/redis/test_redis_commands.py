import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.config import Settings


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    settings = Settings()

    if settings.test_redis_url is None:
        pytest.skip("test_redis_url is None")

    redis = Redis.from_url(settings.test_redis_url.get_secret_value(), decode_responses=True)

    try:
        yield redis

    finally:
        await redis.aclose()


def unique_key(name: str) -> str:
    return f"marketmind:test:{name}:{uuid4()}"


@pytest.mark.asyncio
async def test_set_and_get_string(redis_client: Redis) -> None:
    key = unique_key("string")
    try:
        assert await redis_client.set(key, "MarketMind") is True
        assert await redis_client.get(key) == "MarketMind"
    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_store_json_as_string(redis_client: Redis) -> None:
    key = unique_key("json")
    value = {"status": "ok", "count": 2}

    try:
        await redis_client.set(key, json.dumps(value))
        stored = await redis_client.get(key)

        assert stored is not None
        assert json.loads(stored) == value

    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_key_has_ttl(redis_client: Redis) -> None:
    key = unique_key("ttl")

    try:
        await redis_client.set(key, "temporary", ex=5)
        ttl = await redis_client.ttl(key)

        assert 0 < ttl <= 5

    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_set_nx_only_allows_first_writer(redis_client: Redis) -> None:
    key = unique_key("nx")

    try:
        first = await redis_client.set(key, "first", nx=True, ex=5)
        second = await redis_client.set(key, "second", nx=True, ex=5)

        assert first is True
        assert second is None
        assert await redis_client.get(key) == "first"

    finally:
        await redis_client.delete(key)
