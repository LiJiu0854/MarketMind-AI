"""受控研究的 Celery 入口与资源生命周期。"""

import asyncio

from celery import Task  # type: ignore[import-untyped]
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from app.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import AppError
from app.db.redis import close_redis_client, create_redis_client
from app.db.session import create_engine, create_session_factory
from app.services.redis_guards import redis_lock
from app.services.research import PROMPT_VERSION, mark_research_failure, mark_research_running
from app.services.research_agent import (
    ResearchCallError,
    complete_research_report,
    run_research_actions,
)

RESEARCH_LOCK_PREFIX = "marketmind:lock:research"
MAX_RESEARCH_RETRIES = 2


async def run_research_attempt(run_id: int) -> dict[str, int | str]:
    """一次尝试持有独立锁，数据库事务仅环绕状态与检查点。"""
    settings = Settings()
    if settings.database_url is None or settings.redis_url is None:
        raise ResearchCallError("RESEARCH_CONFIG_ERROR", "研究基础设施配置缺失", retryable=False)
    redis = create_redis_client(settings.redis_url)
    try:
        engine = create_engine(settings.database_url)
        try:
            sessions = create_session_factory(engine)
            ttl_ms = max(
                settings.redis_lock_ttl_ms,
                (
                    settings.research_max_actions
                    * (settings.llm_timeout_seconds + settings.embedding_timeout_seconds + 45)
                    + settings.llm_timeout_seconds
                    + 60
                )
                * 1000,
            )
            async with redis_lock(redis, f"{RESEARCH_LOCK_PREFIX}:{run_id}", ttl_ms) as acquired:
                if not acquired:
                    return {"run_id": run_id, "status": "already_running"}
                async with sessions() as session:
                    run = await mark_research_running(session, run_id)
                if run is None:
                    return {"run_id": run_id, "status": "ignored"}
                if (
                    run.provider != settings.llm_provider
                    or run.model != settings.llm_model
                    or run.prompt_version != PROMPT_VERSION
                ):
                    raise ResearchCallError(
                        "RESEARCH_CONFIG_ERROR",
                        "研究模型配置与创建时不一致",
                        retryable=False,
                    )
                result = await run_research_actions(run_id, sessions, settings)
                if result is None:
                    return {"run_id": run_id, "status": "ignored"}
                saved = await complete_research_report(run_id, sessions, settings)
                return {
                    "run_id": run_id,
                    "status": "success" if saved is not None else "ignored",
                }
        finally:
            await engine.dispose()
    finally:
        await close_redis_client(redis)


async def persist_research_failure(run_id: int, code: str, message: str) -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise RuntimeError("无法保存研究失败状态")
    engine = create_engine(database_url)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            await mark_research_failure(session, run_id, code, message)
    except Exception:
        raise RuntimeError("无法保存研究失败状态") from None
    finally:
        await engine.dispose()


def run_research_task(task: Task, run_id: int) -> dict[str, int | str]:
    """同步 Celery 边界只处理安全错误码与最多两次额外重试。"""
    try:
        return asyncio.run(run_research_attempt(run_id))
    except ResearchCallError as error:
        retries = int(task.request.retries)
        if error.retryable and retries < MAX_RESEARCH_RETRIES:
            retry = task.retry(exc=error, countdown=2**retries, throw=False)
            raise retry from None
        asyncio.run(persist_research_failure(run_id, error.code, error.message))
    except AppError as error:
        retries = int(task.request.retries)
        retryable = error.code in {
            "LOCK_UNAVAILABLE",
            "RESEARCH_EMBEDDING_UNAVAILABLE",
            "RESEARCH_SEARCH_UNAVAILABLE",
        }
        if retryable and retries < MAX_RESEARCH_RETRIES:
            safe_error = RuntimeError(error.message)
            retry = task.retry(exc=safe_error, countdown=2**retries, throw=False)
            raise retry from None
        asyncio.run(persist_research_failure(run_id, error.code, error.message))
    except (OperationalError, RedisError):
        retries = int(task.request.retries)
        if retries < MAX_RESEARCH_RETRIES:
            safe_error = RuntimeError("研究基础设施暂时不可用")
            retry = task.retry(exc=safe_error, countdown=2**retries, throw=False)
            raise retry from None
        asyncio.run(
            persist_research_failure(run_id, "RESEARCH_INTERNAL_ERROR", "研究服务暂时不可用")
        )
    except Exception:
        asyncio.run(persist_research_failure(run_id, "RESEARCH_INTERNAL_ERROR", "研究任务执行失败"))
    return {"run_id": run_id, "status": "failure"}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.tasks.research.run_research",
    max_retries=MAX_RESEARCH_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_research(self: Task, run_id: int) -> dict[str, int | str]:
    return run_research_task(self, run_id)
