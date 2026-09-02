"""Redis 接口保护单元测试。"""

import json
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from app.core.errors import AppError
from app.services.redis_guards import (
    begin_idempotent_request,
    complete_idempotent_request,
    enforce_login_rate_limit,
    redis_lock,
    request_fingerprint,
)


def test_fingerprint_ignores_dictionary_key_order() -> None:
    first = request_fingerprint(1, "/api/v1/users", {"role": "analyst", "x": 1})
    second = request_fingerprint(1, "/api/v1/users", {"x": 1, "role": "analyst"})
    assert first == second


def test_fingerprint_changes_when_request_changes() -> None:
    first = request_fingerprint(1, "/api/v1/users", {"role": "analyst"})
    second = request_fingerprint(1, "/api/v1/users", {"role": "operator"})
    assert first != second


@pytest.mark.asyncio
async def test_first_idempotent_request_gets_execution_right() -> None:
    redis = AsyncMock()
    redis.set.return_value = True

    result = await begin_idempotent_request(redis, "idem:key", "fp", 30)

    assert result is None


@pytest.mark.asyncio
async def test_completed_request_replays_saved_response() -> None:
    redis = AsyncMock()
    redis.set.return_value = None
    redis.get.return_value = json.dumps(
        {
            "fingerprint": "abc123",
            "status": "completed",
            "response": '{"id":7}',
        }
    )

    result = await begin_idempotent_request(redis, "idem:key", "abc123", 60)

    assert result == '{"id":7}'


@pytest.mark.asyncio
async def test_processing_request_returns_409() -> None:
    redis = AsyncMock()
    redis.set.return_value = None
    redis.get.return_value = json.dumps(
        {"fingerprint": "abc123", "status": "processing"}
    )

    with pytest.raises(AppError) as exc_info:
        await begin_idempotent_request(redis, "idem:key", "abc123", 60)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_reused_key_with_other_payload_returns_409() -> None:
    redis = AsyncMock()
    redis.set.return_value = None
    redis.get.return_value = json.dumps(
        {
            "fingerprint": "different",
            "status": "completed",
            "response": "{}",
        }
    )

    with pytest.raises(AppError) as exc_info:
        await begin_idempotent_request(redis, "idem:key", "new", 60)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_idempotency_redis_failure_returns_503() -> None:
    redis = AsyncMock()
    redis.set.side_effect = RedisError("down")

    with pytest.raises(AppError) as exc_info:
        await begin_idempotent_request(redis, "idem:key", "fp", 30)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_complete_idempotent_request_uses_result_ttl() -> None:
    redis = AsyncMock()
    redis.eval.return_value = 1

    await complete_idempotent_request(redis, "idem:key", "fp", '{"id":7}', 3600)

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_below_limit_is_allowed() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [2, 50]

    await enforce_login_rate_limit(redis, "ip|email", 5, 60)


@pytest.mark.asyncio
async def test_login_over_limit_returns_429_and_retry_after() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [6, 42]

    with pytest.raises(AppError) as exc_info:
        await enforce_login_rate_limit(redis, "ip|email", 5, 60)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "42"}


@pytest.mark.asyncio
async def test_rate_limit_redis_failure_returns_503() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = RedisError("down")

    with pytest.raises(AppError) as exc_info:
        await enforce_login_rate_limit(redis, "ip|email", 5, 60)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_lock_owner_enters_and_releases() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    redis.eval.return_value = 1

    async with redis_lock(redis, "lock:stats", 5_000) as acquired:
        assert acquired is True

    _, owner = redis.set.await_args.args
    assert isinstance(owner, str)
    redis.set.assert_awaited_once_with("lock:stats", owner, nx=True, px=5_000)
    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_second_owner_does_not_release_lock() -> None:
    redis = AsyncMock()
    redis.set.return_value = None

    async with redis_lock(redis, "lock:stats", 5_000) as acquired:
        assert acquired is False

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_exception_still_releases_owned_lock() -> None:
    redis = AsyncMock()
    redis.set.return_value = True

    with pytest.raises(RuntimeError):
        async with redis_lock(redis, "lock:stats", 5_000):
            raise RuntimeError("business failed")

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_redis_failure_returns_503() -> None:
    redis = AsyncMock()
    redis.set.side_effect = RedisError("down")

    with pytest.raises(AppError) as exc_info:
        async with redis_lock(redis, "lock:stats", 5_000):
            pass

    assert exc_info.value.status_code == 503
