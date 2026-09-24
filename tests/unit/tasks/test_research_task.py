"""Research Worker lock, resource and safe retry contract."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from celery.exceptions import Retry  # type: ignore[import-untyped]
from pydantic import SecretStr

import app.tasks.research as research_task
from app.core.config import Settings
from app.services.research_agent import ResearchCallError


def configured_settings() -> Settings:
    return Settings(
        database_url=SecretStr("mysql+asyncmy://test:test@127.0.0.1/marketmind_test"),
        redis_url=SecretStr("redis://127.0.0.1/0"),
        llm_provider="test",
        llm_model="research-model",
        llm_api_key=SecretStr("private"),
        embedding_model="embedding-model",
        embedding_api_key=SecretStr("private"),
    )


def fake_resources(
    monkeypatch: pytest.MonkeyPatch, *, acquired: bool = True
) -> tuple[AsyncMock, AsyncMock, list[int], AsyncMock]:
    redis = AsyncMock()
    engine = AsyncMock()
    ttls: list[int] = []

    @asynccontextmanager
    async def session_context() -> AsyncIterator[object]:
        yield object()

    @asynccontextmanager
    async def lock_context(_redis: object, _key: str, ttl: int) -> AsyncIterator[bool]:
        ttls.append(ttl)
        yield acquired

    monkeypatch.setattr(research_task, "Settings", Mock(return_value=configured_settings()))
    monkeypatch.setattr(research_task, "create_redis_client", Mock(return_value=redis))
    close = AsyncMock()
    monkeypatch.setattr(research_task, "close_redis_client", close)
    monkeypatch.setattr(research_task, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(research_task, "create_session_factory", Mock(return_value=session_context))
    monkeypatch.setattr(research_task, "redis_lock", lock_context)
    return redis, engine, ttls, close


@pytest.mark.asyncio
async def test_lock_not_acquired_skips_actions_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, engine, ttls, close = fake_resources(monkeypatch, acquired=False)
    running = AsyncMock()
    monkeypatch.setattr(research_task, "mark_research_running", running)
    result = await research_task.run_research_attempt(7)
    assert result == {"run_id": 7, "status": "already_running"}
    running.assert_not_awaited()
    assert ttls[0] >= (4 * (60 + 60 + 30) + 60 + 60) * 1000
    engine.dispose.assert_awaited_once()
    close.assert_awaited_once_with(redis)


@pytest.mark.asyncio
async def test_terminal_run_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_resources(monkeypatch)
    monkeypatch.setattr(research_task, "mark_research_running", AsyncMock(return_value=None))
    actions = AsyncMock()
    monkeypatch.setattr(research_task, "run_research_actions", actions)
    result = await research_task.run_research_attempt(7)
    assert result["status"] == "ignored"
    actions.assert_not_awaited()


def test_retryable_error_gets_two_extra_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ResearchCallError("RESEARCH_PROVIDER_UNAVAILABLE", "暂不可用", retryable=True)
    monkeypatch.setattr(research_task, "run_research_attempt", AsyncMock(side_effect=error))
    persist = AsyncMock()
    monkeypatch.setattr(research_task, "persist_research_failure", persist)
    task = Mock()
    task.request.retries = 0
    task.retry.return_value = Retry()
    with pytest.raises(Retry):
        research_task.run_research_task(task, 7)
    assert task.retry.call_args.kwargs["countdown"] == 1
    persist.assert_not_awaited()
    task.request.retries = 2
    assert research_task.run_research_task(task, 7)["status"] == "failure"
    persist.assert_awaited_once_with(7, error.code, error.message)


def test_permanent_error_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ResearchCallError("RESEARCH_INVALID_RESPONSE", "动作无效", retryable=False)
    monkeypatch.setattr(research_task, "run_research_attempt", AsyncMock(side_effect=error))
    persist = AsyncMock()
    monkeypatch.setattr(research_task, "persist_research_failure", persist)
    task = Mock()
    task.request.retries = 0
    assert research_task.run_research_task(task, 7)["status"] == "failure"
    task.retry.assert_not_called()
    persist.assert_awaited_once()


def test_celery_registration_is_late_ack() -> None:
    assert research_task.run_research.name == "app.tasks.research.run_research"
    assert research_task.run_research.acks_late
    assert research_task.run_research.max_retries == 2
