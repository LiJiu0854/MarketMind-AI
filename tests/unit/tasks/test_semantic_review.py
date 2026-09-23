"""Celery 语义审核任务与状态迁移测试。"""

import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from celery.exceptions import Retry  # type: ignore[import-untyped]
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import app.tasks.semantic_review as review_task
from app.celery_app import create_celery_app
from app.core.config import Settings
from app.core.errors import AppError
from app.models.semantic_review import SemanticReview, SemanticReviewStatus
from app.models.user import Role
from app.schemas.product import ProductCreate
from app.schemas.semantic_review import LLMReviewResult
from app.schemas.user import UserCreate
from app.services.products import create_product
from app.services.semantic_reviews import (
    PROMPT_VERSION,
    ReviewCompletion,
    SemanticReviewCallError,
    create_semantic_review,
    mark_review_failure,
    mark_review_running,
    mark_review_success,
    set_review_task_id,
)
from app.services.users import create_user


def review_result() -> LLMReviewResult:
    return LLMReviewResult.model_validate(
        {
            "score": 88,
            "dimension_scores": {
                "completeness": 90,
                "consistency": 85,
                "clarity": 87,
                "risk": 92,
                "persuasion": 86,
            },
            "summary": "商品信息完整，表达清晰。",
            "issues": [
                {
                    "dimension": "clarity",
                    "severity": "medium",
                    "field": "description",
                    "message": "描述可以更具体。",
                    "suggestion": "补充可验证的使用场景。",
                }
            ],
            "rewrite": {
                "title": "清晰具体的商品标题",
                "description": "面向真实使用场景的商品描述。",
                "bullet_points": [
                    "清楚说明商品的核心使用价值",
                    "使用可验证的信息减少理解成本",
                    "避免夸张承诺并保持表达一致",
                ],
            },
        }
    )


async def pending_review(session: AsyncSession, suffix: str) -> int:
    actor = await create_user(
        session,
        UserCreate(
            email=f"worker-{suffix}@example.com",
            full_name="Worker Reviewer",
            password="correct-horse-battery-staple",
            role=Role.OPERATOR,
        ),
    )
    product = await create_product(
        session,
        ProductCreate(
            sku=f"worker-{suffix}",
            title="Useful Product",
            description="A useful product description",
            bullet_points=["First point", "Second point", "Third point"],
            brand="Brand",
            category="Category",
            price=Decimal("19.90"),
            currency="CNY",
        ),
        actor.id,
    )
    review = await create_semantic_review(
        session,
        product_id=product.id,
        requested_by_id=actor.id,
        provider="openai",
        model="test-model",
    )
    return review.id


@pytest.mark.asyncio
async def test_mark_running_sets_first_start_and_increments_attempts(
    session: AsyncSession,
) -> None:
    review_id = await pending_review(session, "running")

    first = await mark_review_running(session, review_id)
    assert first is not None
    assert first.status is SemanticReviewStatus.RUNNING
    assert first.attempt_count == 1
    assert isinstance(first.started_at, datetime)
    first_started_at = first.started_at

    second = await mark_review_running(session, review_id)
    assert second is not None
    assert second.attempt_count == 2
    assert second.started_at == first_started_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [SemanticReviewStatus.SUCCESS, SemanticReviewStatus.FAILURE],
)
async def test_mark_running_ignores_terminal_review(
    session: AsyncSession,
    status: SemanticReviewStatus,
) -> None:
    review_id = await pending_review(session, f"terminal-{status.value}")
    review = await session.get_one(SemanticReview, review_id)
    review.status = status
    await session.commit()

    assert await mark_review_running(session, review_id) is None


@pytest.mark.asyncio
async def test_mark_success_persists_validated_result_and_usage(
    session: AsyncSession,
) -> None:
    review_id = await pending_review(session, "success")
    await mark_review_running(session, review_id)
    completion = ReviewCompletion(
        result=review_result(),
        prompt_tokens=120,
        completion_tokens=80,
        total_tokens=200,
    )

    review = await mark_review_success(session, review_id, completion)

    assert review is not None
    assert review.status is SemanticReviewStatus.SUCCESS
    assert review.score == 88
    assert review.dimension_scores == review_result().dimension_scores.model_dump(mode="json")
    assert review.issues == [
        issue.model_dump(mode="json") for issue in review_result().issues
    ]
    assert review.rewrite == review_result().rewrite.model_dump(mode="json")
    assert (review.prompt_tokens, review.completion_tokens, review.total_tokens) == (
        120,
        80,
        200,
    )
    assert review.error_code is None
    assert review.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failure_persists_safe_error_from_running(
    session: AsyncSession,
) -> None:
    review_id = await pending_review(session, "failure")
    await mark_review_running(session, review_id)

    review = await mark_review_failure(
        session,
        review_id,
        "REVIEW_INVALID_RESPONSE",
        "模型返回格式无效",
    )

    assert review is not None
    assert review.status is SemanticReviewStatus.FAILURE
    assert review.score is None
    assert review.dimension_scores is None
    assert review.summary is None
    assert review.issues is None
    assert review.rewrite is None
    assert review.prompt_tokens is None
    assert review.error_code == "REVIEW_INVALID_RESPONSE"
    assert review.error_message == "模型返回格式无效"
    assert review.completed_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "transition"),
    [
        (SemanticReviewStatus.SUCCESS, "failure"),
        (SemanticReviewStatus.FAILURE, "success"),
    ],
)
async def test_terminal_review_cannot_be_overwritten(
    session: AsyncSession,
    terminal_status: SemanticReviewStatus,
    transition: str,
) -> None:
    review_id = await pending_review(session, f"immutable-{terminal_status.value}")
    await mark_review_running(session, review_id)
    if terminal_status is SemanticReviewStatus.SUCCESS:
        await mark_review_success(
            session,
            review_id,
            ReviewCompletion(review_result(), 120, 80, 200),
        )
    else:
        await mark_review_failure(
            session,
            review_id,
            "REVIEW_INVALID_RESPONSE",
            "模型返回格式无效",
        )

    if transition == "success":
        changed = await mark_review_success(
            session,
            review_id,
            ReviewCompletion(review_result(), 120, 80, 200),
        )
    else:
        changed = await mark_review_failure(
            session,
            review_id,
            "REVIEW_INTERNAL_ERROR",
            "不应覆盖终态",
        )

    assert changed is None
    stored = await session.get_one(SemanticReview, review_id)
    await session.refresh(stored)
    assert stored.status is terminal_status


@pytest.mark.asyncio
async def test_set_review_task_id_and_missing_review_contract(
    session: AsyncSession,
) -> None:
    review_id = await pending_review(session, "task-id")

    review = await set_review_task_id(session, review_id, "celery-task-123")

    assert review.celery_task_id == "celery-task-123"
    with pytest.raises(AppError) as exc_info:
        await set_review_task_id(session, 999_999, "missing")
    assert exc_info.value.code == "SEMANTIC_REVIEW_NOT_FOUND"
    assert exc_info.value.status_code == 404


def worker_settings() -> Settings:
    return Settings(
        database_url=SecretStr(
            "mysql+asyncmy://test:test@127.0.0.1:3306/marketmind_test"
        ),
        redis_url=SecretStr("redis://127.0.0.1:6379/0"),
        llm_model="test-model",
        llm_api_key=SecretStr("test-api-key"),
    )


def detached_review() -> SimpleNamespace:
    return SimpleNamespace(
        provider="openai",
        model="persisted-model",
        prompt_version=PROMPT_VERSION,
        product_snapshot={
            "sku": "SKU-1",
            "title": "Useful Product",
            "description": "A useful product description",
            "bullet_points": ["First point", "Second point", "Third point"],
            "brand": "Brand",
            "category": "Category",
            "price": "19.90",
            "currency": "CNY",
            "is_active": True,
        }
    )


def configure_worker_resources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lock_acquired: bool = True,
) -> tuple[AsyncMock, AsyncMock, Mock]:
    redis = AsyncMock()
    engine = AsyncMock()
    close_redis = AsyncMock()
    session_factory = Mock()

    @asynccontextmanager
    async def session_context() -> AsyncIterator[object]:
        yield object()

    session_factory.side_effect = session_context

    @asynccontextmanager
    async def lock_context(*args: object, **kwargs: object) -> AsyncIterator[bool]:
        yield lock_acquired

    monkeypatch.setattr(review_task, "Settings", Mock(return_value=worker_settings()))
    monkeypatch.setattr(review_task, "create_redis_client", Mock(return_value=redis))
    monkeypatch.setattr(review_task, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        review_task,
        "create_session_factory",
        Mock(return_value=session_factory),
    )
    monkeypatch.setattr(review_task, "close_redis_client", close_redis)
    monkeypatch.setattr(review_task, "redis_lock", lock_context)
    return engine, close_redis, session_factory


@pytest.mark.asyncio
async def test_missing_lock_skips_model_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, close_redis, _ = configure_worker_resources(
        monkeypatch,
        lock_acquired=False,
    )
    request_review = Mock()
    mark_running = AsyncMock()
    monkeypatch.setattr(review_task, "request_semantic_review", request_review)
    monkeypatch.setattr(review_task, "mark_review_running", mark_running)

    result = await review_task.run_semantic_review_attempt(7)

    assert result == {"review_id": 7, "status": "already_running"}
    request_review.assert_not_called()
    mark_running.assert_not_awaited()
    engine.dispose.assert_awaited_once_with()
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_or_missing_review_is_idempotently_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, close_redis, _ = configure_worker_resources(monkeypatch)
    request_review = Mock()
    monkeypatch.setattr(review_task, "request_semantic_review", request_review)
    monkeypatch.setattr(review_task, "mark_review_running", AsyncMock(return_value=None))

    result = await review_task.run_semantic_review_attempt(8)

    assert result == {"review_id": 8, "status": "ignored"}
    request_review.assert_not_called()
    engine.dispose.assert_awaited_once_with()
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_success_calls_model_between_short_database_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, close_redis, session_factory = configure_worker_resources(monkeypatch)
    running = AsyncMock(return_value=detached_review())
    success = AsyncMock()
    completion = ReviewCompletion(review_result(), 120, 80, 200)
    request_review = Mock(return_value=completion)
    monkeypatch.setattr(review_task, "mark_review_running", running)
    monkeypatch.setattr(review_task, "mark_review_success", success)
    monkeypatch.setattr(review_task, "request_semantic_review", request_review)

    result = await review_task.run_semantic_review_attempt(9)

    assert result == {"review_id": 9, "status": "success"}
    assert session_factory.call_count == 2
    running.assert_awaited_once()
    request_review.assert_called_once()
    request_settings = request_review.call_args.args[1]
    assert request_settings.llm_model == "persisted-model"
    success.assert_awaited_once()
    engine.dispose.assert_awaited_once_with()
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_success_race_reports_ignored_when_terminal_state_won(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_worker_resources(monkeypatch)
    monkeypatch.setattr(
        review_task,
        "mark_review_running",
        AsyncMock(return_value=detached_review()),
    )
    monkeypatch.setattr(
        review_task,
        "request_semantic_review",
        Mock(return_value=ReviewCompletion(review_result(), 120, 80, 200)),
    )
    monkeypatch.setattr(
        review_task,
        "mark_review_success",
        AsyncMock(return_value=None),
    )

    result = await review_task.run_semantic_review_attempt(19)

    assert result == {"review_id": 19, "status": "ignored"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "different-provider"),
        ("prompt_version", "retired-prompt"),
    ],
)
async def test_worker_rejects_audit_identity_drift_before_model_call(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    engine, close_redis, _ = configure_worker_resources(monkeypatch)
    review = detached_review()
    setattr(review, field, value)
    request_review = Mock()
    monkeypatch.setattr(
        review_task,
        "mark_review_running",
        AsyncMock(return_value=review),
    )
    monkeypatch.setattr(review_task, "request_semantic_review", request_review)

    with pytest.raises(SemanticReviewCallError) as exc_info:
        await review_task.run_semantic_review_attempt(18)

    assert exc_info.value.code == "REVIEW_CONFIG_ERROR"
    assert exc_info.value.retryable is False
    request_review.assert_not_called()
    engine.dispose.assert_awaited_once_with()
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_error_still_releases_engine_and_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, close_redis, _ = configure_worker_resources(monkeypatch)
    error = SemanticReviewCallError(
        "REVIEW_PROVIDER_UNAVAILABLE",
        "模型服务暂时不可用",
        retryable=True,
    )
    monkeypatch.setattr(
        review_task,
        "mark_review_running",
        AsyncMock(return_value=detached_review()),
    )
    monkeypatch.setattr(review_task, "request_semantic_review", Mock(side_effect=error))

    with pytest.raises(SemanticReviewCallError):
        await review_task.run_semantic_review_attempt(10)

    engine.dispose.assert_awaited_once_with()
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_infrastructure_config_creates_no_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_engine = Mock()
    create_redis = Mock()
    monkeypatch.setattr(
        review_task,
        "Settings",
        Mock(return_value=Settings(database_url=None, redis_url=None)),
    )
    monkeypatch.setattr(review_task, "create_engine", create_engine)
    monkeypatch.setattr(review_task, "create_redis_client", create_redis)

    with pytest.raises(SemanticReviewCallError) as exc_info:
        await review_task.run_semantic_review_attempt(11)

    assert exc_info.value.code == "REVIEW_CONFIG_ERROR"
    assert exc_info.value.retryable is False
    create_engine.assert_not_called()
    create_redis.assert_not_called()


@pytest.mark.asyncio
async def test_persist_failure_uses_short_session_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, session_factory = configure_worker_resources(monkeypatch)
    mark_failure = AsyncMock()
    monkeypatch.setattr(review_task, "mark_review_failure", mark_failure)

    await review_task.persist_review_failure(12, "REVIEW_INVALID_RESPONSE", "安全消息")

    session_factory.assert_called_once_with()
    assert mark_failure.await_args is not None
    assert mark_failure.await_args.args[1:] == (
        12,
        "REVIEW_INVALID_RESPONSE",
        "安全消息",
    )
    engine.dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_persist_failure_masks_database_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, _ = configure_worker_resources(monkeypatch)
    monkeypatch.setattr(
        review_task,
        "mark_review_failure",
        AsyncMock(side_effect=RuntimeError("secret database url")),
    )

    with pytest.raises(RuntimeError, match="^无法保存审核失败状态$"):
        await review_task.persist_review_failure(13, "REVIEW_INTERNAL_ERROR", "安全消息")

    engine.dispose.assert_awaited_once_with()


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_retryable_provider_error_uses_bounded_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
    retries: int,
) -> None:
    error = SemanticReviewCallError(
        "REVIEW_PROVIDER_UNAVAILABLE",
        "模型服务暂时不可用",
        retryable=True,
    )

    async def fail_attempt(review_id: int) -> dict[str, int | str]:
        assert review_id == 14
        raise error

    task = MagicMock()
    task.request.retries = retries
    task.retry.return_value = Retry()
    monkeypatch.setattr(review_task, "run_semantic_review_attempt", fail_attempt)

    with pytest.raises(Retry):
        review_task.run_review_task(task, 14)

    task.retry.assert_called_once_with(
        exc=error,
        countdown=2**retries,
        throw=False,
    )


@pytest.mark.parametrize(
    ("error", "retries", "expected_code", "expected_message"),
    [
        (
            SemanticReviewCallError(
                "REVIEW_INVALID_RESPONSE",
                "模型返回格式无效",
                retryable=False,
            ),
            0,
            "REVIEW_INVALID_RESPONSE",
            "模型返回格式无效",
        ),
        (
            SemanticReviewCallError(
                "REVIEW_PROVIDER_UNAVAILABLE",
                "模型服务暂时不可用",
                retryable=True,
            ),
            3,
            "REVIEW_PROVIDER_UNAVAILABLE",
            "模型服务暂时不可用",
        ),
    ],
)
def test_permanent_or_exhausted_provider_error_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
    error: SemanticReviewCallError,
    retries: int,
    expected_code: str,
    expected_message: str,
) -> None:
    async def fail_attempt(review_id: int) -> dict[str, int | str]:
        assert review_id == 15
        raise error

    task = MagicMock()
    task.request.retries = retries
    persist = AsyncMock()
    monkeypatch.setattr(review_task, "run_semantic_review_attempt", fail_attempt)
    monkeypatch.setattr(review_task, "persist_review_failure", persist)

    result = review_task.run_review_task(task, 15)

    assert result == {"review_id": 15, "status": "failure"}
    task.retry.assert_not_called()
    persist.assert_awaited_once_with(15, expected_code, expected_message)


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, RuntimeError("secret database url")),
        RedisError("secret redis url"),
        AppError("LOCK_UNAVAILABLE", "锁服务暂时不可用", 503),
    ],
)
def test_transient_infrastructure_error_retries_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    async def fail_attempt(review_id: int) -> dict[str, int | str]:
        assert review_id == 16
        raise error

    task = MagicMock()
    task.request.retries = 0
    task.retry.return_value = Retry()
    monkeypatch.setattr(review_task, "run_semantic_review_attempt", fail_attempt)

    with pytest.raises(Retry) as exc_info:
        review_task.run_review_task(task, 16)

    retry_error = task.retry.call_args.kwargs["exc"]
    assert str(retry_error) == "审核基础设施暂时不可用"
    assert "secret" not in str(retry_error)
    assert "secret" not in "".join(traceback.format_exception(exc_info.value))
    assert task.retry.call_args.kwargs["countdown"] == 1
    assert task.retry.call_args.kwargs["throw"] is False


def test_generate_task_delegates_to_testable_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Mock(return_value={"review_id": 17, "status": "success"})
    monkeypatch.setattr(review_task, "run_review_task", runner)

    result = review_task.generate_semantic_review.run(17)

    assert result == {"review_id": 17, "status": "success"}
    runner.assert_called_once()


def test_celery_app_registers_task_modules() -> None:
    app = create_celery_app(worker_settings())

    assert app.conf.include == [
        "app.tasks.user_stats",
        "app.tasks.semantic_review",
        "app.tasks.knowledge",
    ]
