"""Document indexing state, resource ownership, and retry behavior."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from celery.exceptions import Retry  # type: ignore[import-untyped]
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

import app.tasks.knowledge as knowledge_task
from app.celery_app import create_celery_app
from app.core.config import Settings
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentStatus
from app.models.user import Role
from app.schemas.knowledge import KnowledgeBaseCreate
from app.schemas.user import UserCreate
from app.services.document_ingestion import (
    DocumentChunk,
    DocumentIngestionError,
    EmbeddingCompletion,
    ParsedSection,
)
from app.services.knowledge import (
    ValidatedUpload,
    create_knowledge_base,
    mark_document_failure,
    mark_document_processing,
    mark_document_ready,
    stage_knowledge_document,
)
from app.services.users import create_user


def worker_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=SecretStr("mysql+asyncmy://test:test@127.0.0.1/marketmind_test"),
        redis_url=SecretStr("redis://127.0.0.1/0"),
        embedding_provider="test",
        embedding_base_url="https://provider.invalid/v1",
        embedding_model="embedding-test",
        embedding_api_key=SecretStr("test-only-key"),
        knowledge_file_root=tmp_path,
    )


async def pending_document(session: AsyncSession, tmp_path: Path, suffix: str) -> int:
    actor = await create_user(
        session,
        UserCreate(
            email=f"rag-worker-{suffix}@example.com",
            full_name="RAG Worker",
            password="correct-horse-battery-staple",
            role=Role.ADMIN,
        ),
    )
    base = await create_knowledge_base(
        session,
        KnowledgeBaseCreate(name=f"Worker {suffix}"),
        actor.id,
        worker_settings(tmp_path),
    )
    document = await stage_knowledge_document(
        session,
        base.id,
        actor.id,
        ValidatedUpload("notes.txt", ".txt", "text/plain", b"hello", "a" * 64),
        tmp_path,
    )
    return document.id


@pytest.mark.asyncio
async def test_pending_moves_processing_then_ready_and_saves_dimensions(
    session: AsyncSession, tmp_path: Path
) -> None:
    document_id = await pending_document(session, tmp_path, "ready")
    started = await mark_document_processing(session, document_id)
    assert started is not None
    document, base = started
    assert document.status is KnowledgeDocumentStatus.PROCESSING
    assert document.started_at is not None
    assert base.embedding_dimensions is None

    saved = await mark_document_ready(session, document_id, 2, 9, 3)
    assert saved is not None
    assert saved.status is KnowledgeDocumentStatus.READY
    assert saved.chunk_count == 2
    assert saved.embedding_tokens == 9
    assert base.embedding_dimensions == 3
    assert saved.completed_at is not None
    assert await mark_document_processing(session, document_id) is None


@pytest.mark.asyncio
async def test_terminal_document_is_ignored_and_failure_is_safe(
    session: AsyncSession, tmp_path: Path
) -> None:
    document_id = await pending_document(session, tmp_path, "failure")
    await mark_document_processing(session, document_id)
    failed = await mark_document_failure(session, document_id, "DOCUMENT_PARSE_ERROR", "无法解析")
    assert failed is not None
    assert failed.status is KnowledgeDocumentStatus.FAILURE
    assert failed.error_code == "DOCUMENT_PARSE_ERROR"
    assert await mark_document_processing(session, document_id) is None
    assert await mark_document_ready(session, document_id, 1, 2, 3) is None


@pytest.mark.asyncio
async def test_processing_document_can_resume_after_worker_crash(
    session: AsyncSession, tmp_path: Path
) -> None:
    document_id = await pending_document(session, tmp_path, "resume")
    first = await mark_document_processing(session, document_id)
    second = await mark_document_processing(session, document_id)
    assert first is not None and second is not None
    assert second[0].started_at == first[0].started_at


def configure_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, acquired: bool = True
) -> tuple[AsyncMock, AsyncMock, AsyncMock, Mock]:
    redis = AsyncMock()
    engine = AsyncMock()
    chroma = AsyncMock()
    sessions = Mock()

    @asynccontextmanager
    async def session_context() -> AsyncIterator[object]:
        yield object()

    @asynccontextmanager
    async def lock_context(*args: object, **kwargs: object) -> AsyncIterator[bool]:
        yield acquired

    sessions.side_effect = session_context
    monkeypatch.setattr(knowledge_task, "Settings", Mock(return_value=worker_settings(tmp_path)))
    monkeypatch.setattr(knowledge_task, "create_redis_client", Mock(return_value=redis))
    monkeypatch.setattr(knowledge_task, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(knowledge_task, "create_session_factory", Mock(return_value=sessions))
    monkeypatch.setattr(knowledge_task, "create_chroma_client", AsyncMock(return_value=chroma))
    monkeypatch.setattr(knowledge_task, "close_chroma_client", AsyncMock())
    monkeypatch.setattr(knowledge_task, "close_redis_client", AsyncMock())
    monkeypatch.setattr(knowledge_task, "redis_lock", lock_context)
    return engine, redis, chroma, sessions


def detached_document() -> tuple[SimpleNamespace, SimpleNamespace]:
    document = SimpleNamespace(
        id=7,
        storage_path="42/7.txt",
        original_name="notes.txt",
    )
    base = SimpleNamespace(
        id=42,
        embedding_provider="test",
        embedding_base_url="https://provider.invalid/v1",
        embedding_model="embedding-test",
        embedding_dimensions=None,
    )
    return document, base


@pytest.mark.asyncio
async def test_no_redis_lock_skips_parse_embedding_and_chroma(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine, _, _, _ = configure_resources(monkeypatch, tmp_path, acquired=False)
    parse = Mock()
    mark = AsyncMock()
    chroma = cast(AsyncMock, knowledge_task.create_chroma_client)  # type: ignore[attr-defined]
    monkeypatch.setattr(knowledge_task, "parse_document", parse)
    monkeypatch.setattr(knowledge_task, "mark_document_processing", mark)

    assert await knowledge_task.run_document_index_attempt(7) == {
        "document_id": 7,
        "status": "already_running",
    }
    parse.assert_not_called()
    mark.assert_not_awaited()
    chroma.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_document_is_ignored_without_provider_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_resources(monkeypatch, tmp_path)
    monkeypatch.setattr(knowledge_task, "mark_document_processing", AsyncMock(return_value=None))
    embed = AsyncMock()
    monkeypatch.setattr(knowledge_task, "request_embeddings", embed)
    assert await knowledge_task.run_document_index_attempt(7) == {
        "document_id": 7,
        "status": "ignored",
    }
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_is_written_only_after_chroma_upsert_and_resources_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine, _, chroma, sessions = configure_resources(monkeypatch, tmp_path)
    file_path = tmp_path / "42" / "7.txt"
    file_path.parent.mkdir()
    file_path.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        knowledge_task, "mark_document_processing", AsyncMock(return_value=detached_document())
    )
    monkeypatch.setattr(
        knowledge_task, "parse_document", Mock(return_value=[ParsedSection("hello", None)])
    )
    chunk = DocumentChunk("document:7:chunk:0", 7, 0, "hello", None)
    monkeypatch.setattr(knowledge_task, "split_sections", Mock(return_value=[chunk]))
    monkeypatch.setattr(
        knowledge_task,
        "request_embeddings",
        AsyncMock(return_value=EmbeddingCompletion([[1.0]], 2, 1)),
    )
    events: list[str] = []

    async def index(*args: object) -> None:
        events.append("chroma")

    async def ready(*args: object) -> KnowledgeDocument:
        events.append("ready")
        return KnowledgeDocument(id=7, status=KnowledgeDocumentStatus.READY)

    monkeypatch.setattr(knowledge_task, "index_document_vectors", index)
    monkeypatch.setattr(knowledge_task, "mark_document_ready", ready)

    assert await knowledge_task.run_document_index_attempt(7) == {
        "document_id": 7,
        "status": "ready",
    }
    assert events == ["chroma", "ready"]
    assert sessions.call_count == 2
    engine.dispose.assert_awaited_once()
    cast(AsyncMock, knowledge_task.close_chroma_client).assert_awaited_once_with(chroma)  # type: ignore[attr-defined]
    cast(AsyncMock, knowledge_task.close_redis_client).assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_embedding_contract_drift_fails_before_provider_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_resources(monkeypatch, tmp_path)
    document, base = detached_document()
    base.embedding_model = "other-model"
    monkeypatch.setattr(
        knowledge_task, "mark_document_processing", AsyncMock(return_value=(document, base))
    )
    embed = AsyncMock()
    monkeypatch.setattr(knowledge_task, "request_embeddings", embed)

    with pytest.raises(DocumentIngestionError) as failure:
        await knowledge_task.run_document_index_attempt(7)
    assert failure.value.code == "DOCUMENT_CONFIG_ERROR"
    embed.assert_not_awaited()


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_transient_provider_or_chroma_error_retries_with_backoff(
    monkeypatch: pytest.MonkeyPatch, retries: int
) -> None:
    error = DocumentIngestionError("CHROMA_UNAVAILABLE", "向量服务暂不可用", retryable=True)

    async def fail(document_id: int) -> dict[str, int | str]:
        raise error

    task = MagicMock()
    task.request.retries = retries
    task.retry.return_value = Retry()
    monkeypatch.setattr(knowledge_task, "run_document_index_attempt", fail)
    with pytest.raises(Retry):
        knowledge_task.run_document_index_task(task, 7)
    task.retry.assert_called_once_with(exc=error, countdown=2**retries, throw=False)


def test_permanent_parse_error_is_persisted_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = DocumentIngestionError("DOCUMENT_PARSE_ERROR", "无法解析", retryable=False)

    async def fail(document_id: int) -> dict[str, int | str]:
        raise error

    persist = AsyncMock()
    task = MagicMock()
    task.request.retries = 0
    monkeypatch.setattr(knowledge_task, "run_document_index_attempt", fail)
    monkeypatch.setattr(knowledge_task, "persist_document_failure", persist)
    assert knowledge_task.run_document_index_task(task, 7) == {
        "document_id": 7,
        "status": "failure",
    }
    task.retry.assert_not_called()
    persist.assert_awaited_once_with(7, "DOCUMENT_PARSE_ERROR", "无法解析")


def test_celery_registers_knowledge_task_module() -> None:
    app = create_celery_app(worker_settings(Path("data/knowledge")))
    assert "app.tasks.knowledge" in app.conf.include
