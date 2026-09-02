import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from hashlib import sha256
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import AppError
from app.services.redis_guards import (
    LOCK_RELEASE_SCRIPT,
    begin_idempotent_request,
    enforce_login_rate_limit,
    redis_lock,
)


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


@pytest.mark.asyncio
async def test_set_nx_allows_only_first_owner(redis_client: Redis) -> None:
    key = unique_key("atomic-lock")
    try:
        first = await redis_client.set(key, "A", nx=True, px=5_000)
        second = await redis_client.set(key, "B", nx=True, px=5_000)

        assert first is True
        assert second is None

        assert await redis_client.pttl(key) > 0
    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_lock_script_deletes_only_matching_owner(redis_client: Redis) -> None:
    key = unique_key("owner-delete")
    try:
        await redis_client.set(key, "owner-a", px=5_000)

        wrong = await cast(
            Awaitable[object],
            redis_client.eval(LOCK_RELEASE_SCRIPT, 1, key, "owner-b"),
        )
        assert wrong == 0
        assert await redis_client.get(key) == "owner-a"

        correct = await cast(
            Awaitable[object],
            redis_client.eval(LOCK_RELEASE_SCRIPT, 1, key, "owner-a"),
        )
        assert correct == 1
        assert await redis_client.get(key) is None
    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_concurrent_idempotent_requests_allow_one_owner(
    redis_client: Redis,
) -> None:
    key = unique_key("idempotency")

    async def begin() -> str:
        try:
            result = await begin_idempotent_request(redis_client, key, "same-fp", 5)
        except AppError as exc:
            return str(exc.status_code)
        return "owner" if result is None else "replay"

    try:
        results = await asyncio.gather(begin(), begin())
        assert results.count("owner") == 1
        assert results.count("409") == 1
    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_rate_limit_window_expires(redis_client: Redis) -> None:
    identity = unique_key("rate-limit")
    digest = sha256(identity.encode()).hexdigest()
    key = f"marketmind:rate-limit:login:{digest}"

    try:
        await enforce_login_rate_limit(redis_client, identity, 2, 1)
        await enforce_login_rate_limit(redis_client, identity, 2, 1)
        with pytest.raises(AppError) as exc_info:
            await enforce_login_rate_limit(redis_client, identity, 2, 1)
        assert exc_info.value.status_code == 429

        await asyncio.sleep(1.1)
        await enforce_login_rate_limit(redis_client, identity, 2, 1)
    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_concurrent_lock_allows_one_owner(redis_client: Redis) -> None:
    key = unique_key("concurrent-lock")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        async with redis_lock(redis_client, key, 5_000) as acquired:
            assert acquired is True
            entered.set()
            await release.wait()

    owner = asyncio.create_task(hold_lock())
    try:
        await entered.wait()
        async with redis_lock(redis_client, key, 5_000) as acquired:
            assert acquired is False
    finally:
        release.set()
        await owner
        await redis_client.delete(key)
