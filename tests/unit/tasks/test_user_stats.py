"""用户统计后台任务测试。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.tasks.user_stats as user_stats
from app.models.user import Role, User


def make_user(index: int, role: Role, *, active: bool = True) -> User:
    return User(
        email=f"stats-{index}@example.com",
        full_name=f"Stats User {index}",
        password_hash="test-hash",
        role=role,
        is_active=active,
    )


@pytest.mark.asyncio
async def test_query_user_stats_counts_users(session: AsyncSession) -> None:
    session.add_all(
        [
            make_user(1, Role.ADMIN),
            make_user(2, Role.ADMIN, active=False),
            make_user(3, Role.OPERATOR),
            make_user(4, Role.ANALYST),
            make_user(5, Role.ANALYST, active=False),
        ]
    )
    await session.flush()

    assert await user_stats.query_user_stats(session) == {
        "total": 5,
        "active": 3,
        "inactive": 2,
        "admin": 2,
        "operator": 1,
        "analyst": 2,
    }


@pytest.mark.asyncio
async def test_query_user_stats_returns_zero_for_empty_table(
    session: AsyncSession,
) -> None:
    assert await user_stats.query_user_stats(session) == {
        "total": 0,
        "active": 0,
        "inactive": 0,
        "admin": 0,
        "operator": 0,
        "analyst": 0,
    }


@pytest.mark.asyncio
async def test_missing_lock_skips_database(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def missing_lock(
        *args: object, **kwargs: object
    ) -> AsyncIterator[bool]:
        yield False

    redis = AsyncMock()
    collect = AsyncMock()
    monkeypatch.setattr(user_stats, "redis_lock", missing_lock)
    monkeypatch.setattr(user_stats, "create_redis_client", Mock(return_value=redis))
    monkeypatch.setattr(user_stats, "close_redis_client", AsyncMock())
    monkeypatch.setattr(user_stats, "collect_user_stats", collect)

    assert await user_stats.run_user_stats_with_lock() == {
        "status": "already_running"
    }
    collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_acquired_lock_returns_completed_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def acquired_lock(
        *args: object, **kwargs: object
    ) -> AsyncIterator[bool]:
        yield True

    redis = AsyncMock()
    close = AsyncMock()
    collect = AsyncMock(return_value={"total": 3})
    monkeypatch.setattr(user_stats, "redis_lock", acquired_lock)
    monkeypatch.setattr(user_stats, "create_redis_client", Mock(return_value=redis))
    monkeypatch.setattr(user_stats, "close_redis_client", close)
    monkeypatch.setattr(user_stats, "collect_user_stats", collect)

    assert await user_stats.run_user_stats_with_lock() == {
        "total": 3,
        "status": "completed",
    }
    collect.assert_awaited_once_with()
    close.assert_awaited_once_with(redis)


def test_generate_user_stats_runs_async_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = AsyncMock(return_value={"status": "completed", "total": 2})
    monkeypatch.setattr(user_stats, "run_user_stats_with_lock", coordinator)

    result = user_stats.generate_user_stats.run()

    assert result == {"status": "completed", "total": 2}
    coordinator.assert_awaited_once_with()
