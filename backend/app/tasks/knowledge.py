"""Celery orchestration for at-least-once document indexing."""

import asyncio
from math import ceil
from pathlib import Path

from celery import Task  # type: ignore[import-untyped]
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from app.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import AppError
from app.db.chroma import close_chroma_client, create_chroma_client
from app.db.redis import close_redis_client, create_redis_client
from app.db.session import create_engine, create_session_factory
from app.services.document_ingestion import (
    MAX_CHUNKS_PER_DOCUMENT,
    DocumentIngestionError,
    index_document_vectors,
    parse_document,
    request_embeddings,
    split_sections,
)
from app.services.knowledge import (
    mark_document_failure,
    mark_document_processing,
    mark_document_ready,
)
from app.services.redis_guards import redis_lock

DOCUMENT_LOCK_PREFIX = "marketmind:lock:knowledge-document"
MAX_DOCUMENT_RETRIES = 3


async def run_document_index_attempt(document_id: int) -> dict[str, int | str]:
    """Use one lock and short database sessions around external work."""
    settings = Settings()
    if (
        settings.database_url is None
        or settings.redis_url is None
        or settings.embedding_model is None
        or settings.embedding_api_key is None
    ):
        raise DocumentIngestionError(
            "DOCUMENT_CONFIG_ERROR", "文档索引配置缺失", retryable=False
        )
    redis = create_redis_client(settings.redis_url)
    try:
        engine = create_engine(settings.database_url)
        try:
            sessions = create_session_factory(engine)
            batch_count = ceil(MAX_CHUNKS_PER_DOCUMENT / settings.embedding_batch_size)
            lock_ttl_ms = max(
                settings.redis_lock_ttl_ms,
                (settings.embedding_timeout_seconds * batch_count + 120) * 1_000,
            )
            async with redis_lock(
                redis, f"{DOCUMENT_LOCK_PREFIX}:{document_id}", lock_ttl_ms
            ) as acquired:
                if not acquired:
                    return {"document_id": document_id, "status": "already_running"}
                async with sessions() as session:
                    pending = await mark_document_processing(session, document_id)
                if pending is None:
                    return {"document_id": document_id, "status": "ignored"}
                document, base = pending
                if (
                    base.embedding_provider != settings.embedding_provider
                    or base.embedding_base_url != settings.embedding_base_url
                    or base.embedding_model != settings.embedding_model
                ):
                    raise DocumentIngestionError(
                        "DOCUMENT_CONFIG_ERROR",
                        "Embedding 配置与知识库不一致",
                        retryable=False,
                    )
                root = await asyncio.to_thread(settings.knowledge_file_root.resolve)
                source = await asyncio.to_thread((root / document.storage_path).resolve)
                if not source.is_relative_to(root):
                    raise DocumentIngestionError(
                        "DOCUMENT_PARSE_ERROR", "文档存储路径无效", retryable=False
                    )
                suffix = Path(document.storage_path).suffix.lower()
                sections = await asyncio.to_thread(parse_document, source, suffix)
                chunks = split_sections(
                    document_id, sections, settings.rag_chunk_size, settings.rag_chunk_overlap
                )
                embeddings = await request_embeddings([chunk.text for chunk in chunks], settings)
                if (
                    base.embedding_dimensions is not None
                    and base.embedding_dimensions != embeddings.dimensions
                ):
                    raise DocumentIngestionError(
                        "DOCUMENT_CONFIG_ERROR",
                        "Embedding 向量维度与知识库不一致",
                        retryable=False,
                    )
                try:
                    chroma = await create_chroma_client(settings)
                except Exception:
                    raise DocumentIngestionError(
                        "CHROMA_UNAVAILABLE", "向量服务暂时不可用", retryable=True
                    ) from None
                try:
                    await index_document_vectors(chroma, base, document, chunks, embeddings)
                finally:
                    await close_chroma_client(chroma)
                async with sessions() as session:
                    saved = await mark_document_ready(
                        session,
                        document_id,
                        len(chunks),
                        embeddings.total_tokens,
                        embeddings.dimensions,
                    )
                return {
                    "document_id": document_id,
                    "status": "ready" if saved is not None else "ignored",
                }
        finally:
            await engine.dispose()
    finally:
        await close_redis_client(redis)


async def persist_document_failure(document_id: int, code: str, message: str) -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise RuntimeError("无法保存文档索引失败状态")
    engine = create_engine(database_url)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            await mark_document_failure(session, document_id, code, message)
    except Exception:
        raise RuntimeError("无法保存文档索引失败状态") from None
    finally:
        await engine.dispose()


def run_document_index_task(task: Task, document_id: int) -> dict[str, int | str]:
    try:
        return asyncio.run(run_document_index_attempt(document_id))
    except DocumentIngestionError as error:
        retries = int(task.request.retries)
        if error.retryable and retries < MAX_DOCUMENT_RETRIES:
            retry = task.retry(exc=error, countdown=2**retries, throw=False)
            raise retry from None
        asyncio.run(persist_document_failure(document_id, error.code, error.message))
    except (OperationalError, RedisError, AppError):
        retries = int(task.request.retries)
        if retries < MAX_DOCUMENT_RETRIES:
            safe_error = RuntimeError("文档索引基础设施暂时不可用")
            retry = task.retry(exc=safe_error, countdown=2**retries, throw=False)
            raise retry from None
        asyncio.run(
            persist_document_failure(
                document_id, "DOCUMENT_INTERNAL_ERROR", "文档索引基础设施暂时不可用"
            )
        )
    except Exception:
        asyncio.run(
            persist_document_failure(document_id, "DOCUMENT_INTERNAL_ERROR", "文档索引任务执行失败")
        )
    return {"document_id": document_id, "status": "failure"}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.tasks.knowledge.index_knowledge_document",
    max_retries=MAX_DOCUMENT_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def index_knowledge_document(self: Task, document_id: int) -> dict[str, int | str]:
    return run_document_index_task(self, document_id)
