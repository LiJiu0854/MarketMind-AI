from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from app.models.user import Role, User
from app.schemas.user import UserRead
from app.services.user_cache import (
    get_user_with_cache,
    invalidate_user_cache,
    user_cache_key,
)


def make_user_read(user_id: int = 7) -> UserRead:
    now = datetime.now(UTC)
    return UserRead(
        id=user_id,
        email="cache@example.com",
        full_name="Cache User",
        role=Role.ANALYST,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_user_cache_key_is_stable_and_versioned() -> None:
    assert user_cache_key(7) == "marketmind:user:v1:7"


def test_user_read_json_does_not_expose_password() -> None:
    user = make_user_read()
    payload = user.model_dump_json()
    assert "password" not in payload
    assert UserRead.model_validate_json(payload) == user


def make_user_model(user_id: int = 7) -> User:
    schema = make_user_read(user_id)
    return User(
        id=schema.id,
        email=schema.email,
        full_name=schema.full_name,
        password_hash="must-not-enter-cache",
        role=schema.role,
        is_active=schema.is_active,
        created_at=schema.created_at,
        updated_at=schema.updated_at,
    )


@pytest.mark.asyncio
async def test_cache_hit_does_not_query_database() -> None:
    expected = make_user_read()
    session = AsyncMock()
    redis = AsyncMock()
    redis.get.return_value = expected.model_dump_json()

    result = await get_user_with_cache(session, redis, 7, 60)

    assert result == expected
    session.get.assert_not_awaited()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_miss_queries_database_and_sets_ttl() -> None:
    session = AsyncMock()
    session.get.return_value = make_user_model()
    redis = AsyncMock()
    redis.get.return_value = None

    result = await get_user_with_cache(session, redis, 7, 60)

    assert result.id == 7

    session.get.assert_awaited_once_with(User, 7)
    redis.set.assert_awaited_once_with(
        "marketmind:user:v1:7",
        result.model_dump_json(),
        ex=60,
    )


@pytest.mark.asyncio
async def test_cache_read_failure_falls_back_to_database() -> None:
    session = AsyncMock()
    session.get.return_value = make_user_model()
    redis = AsyncMock()
    redis.get.side_effect = RedisError("read failed")

    result = await get_user_with_cache(session, redis, 7, 60)

    assert result.id == 7
    session.get.assert_awaited_once_with(User, 7)


@pytest.mark.asyncio
async def test_cache_write_failure_still_returns_database_user() -> None:
    session = AsyncMock()
    session.get.return_value = make_user_model()
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.side_effect = RedisError("write failed")

    result = await get_user_with_cache(session, redis, 7, 60)

    assert result.id == 7


@pytest.mark.asyncio
async def test_cache_delete_failure_does_not_change_database_result() -> None:
    redis = AsyncMock()
    redis.delete.side_effect = RedisError("delete failed")

    await invalidate_user_cache(redis, 7)

    redis.delete.assert_awaited_once_with("marketmind:user:v1:7")
