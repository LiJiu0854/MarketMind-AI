"""商品语义审核 Celery 任务。"""

import asyncio

from celery import Task  # type: ignore[import-untyped]
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from app.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import AppError
from app.db.redis import close_redis_client, create_redis_client
from app.db.session import create_engine, create_session_factory
from app.schemas.semantic_review import ProductSnapshot
from app.services.redis_guards import redis_lock
from app.services.semantic_reviews import (
    SemanticReviewCallError,
    mark_review_failure,
    mark_review_running,
    mark_review_success,
    request_semantic_review,
)

SEMANTIC_REVIEW_LOCK_PREFIX = "marketmind:lock:semantic-review"
MAX_REVIEW_RETRIES = 3


async def run_semantic_review_attempt(review_id: int) -> dict[str, int | str]:
    """在独立 Worker 资源中执行一次模型审核尝试。"""
    settings = Settings()
    if settings.database_url is None or settings.redis_url is None:
        raise SemanticReviewCallError(
            "REVIEW_CONFIG_ERROR",
            "审核基础设施配置缺失",
            retryable=False,
        )

    redis = create_redis_client(settings.redis_url)
    try:
        engine = create_engine(settings.database_url)
        try:
            session_factory = create_session_factory(engine)
            lock_key = f"{SEMANTIC_REVIEW_LOCK_PREFIX}:{review_id}"
            lock_ttl_ms = (settings.llm_timeout_seconds + 30) * 1_000

            async with redis_lock(redis, lock_key, lock_ttl_ms) as acquired:
                if not acquired:
                    return {"review_id": review_id, "status": "already_running"}

                async with session_factory() as session:
                    review = await mark_review_running(session, review_id)
                if review is None:
                    return {"review_id": review_id, "status": "ignored"}

                snapshot = ProductSnapshot.model_validate(review.product_snapshot)
                completion = request_semantic_review(snapshot, settings)

                async with session_factory() as session:
                    await mark_review_success(session, review_id, completion)
                return {"review_id": review_id, "status": "success"}
        finally:
            await engine.dispose()
    finally:
        await close_redis_client(redis)


async def persist_review_failure(
    review_id: int,
    code: str,
    message: str,
) -> None:
    """使用新的短 Session 保存安全失败状态。"""
    database_url = Settings().database_url
    if database_url is None:
        raise RuntimeError("无法保存审核失败状态")
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            await mark_review_failure(session, review_id, code, message)
    except Exception:
        raise RuntimeError("无法保存审核失败状态") from None
    finally:
        await engine.dispose()


def run_review_task(task: Task, review_id: int) -> dict[str, int | str]:
    """执行异步协调器，并在同步 Celery 边界处理有限重试。"""
    try:
        return asyncio.run(run_semantic_review_attempt(review_id))
    except SemanticReviewCallError as error:
        retries = int(task.request.retries)
        if error.retryable and retries < MAX_REVIEW_RETRIES:
            raise task.retry(exc=error, countdown=2**retries) from error
        asyncio.run(persist_review_failure(review_id, error.code, error.message))
        return {"review_id": review_id, "status": "failure"}
    except (OperationalError, RedisError, AppError):
        retries = int(task.request.retries)
        if retries < MAX_REVIEW_RETRIES:
            safe_error = RuntimeError("审核基础设施暂时不可用")
            raise task.retry(exc=safe_error, countdown=2**retries) from None
        asyncio.run(
            persist_review_failure(
                review_id,
                "REVIEW_INTERNAL_ERROR",
                "审核基础设施暂时不可用",
            )
        )
        return {"review_id": review_id, "status": "failure"}
    except Exception:
        asyncio.run(
            persist_review_failure(
                review_id,
                "REVIEW_INTERNAL_ERROR",
                "审核任务执行失败",
            )
        )
        return {"review_id": review_id, "status": "failure"}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.tasks.semantic_review.generate_semantic_review",
    max_retries=MAX_REVIEW_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_semantic_review(
    self: Task,
    review_id: int,
) -> dict[str, int | str]:
    """Celery 可发现的同步任务入口。"""
    return run_review_task(self, review_id)
