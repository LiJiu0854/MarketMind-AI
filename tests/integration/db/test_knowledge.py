"""Real MySQL knowledge-base contract tests against marketmind_test."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentStatus, KnowledgeQueryStatus
from app.models.user import Role, User
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeCitation,
    KnowledgeQuestionCreate,
    RetrievedChunk,
)
from app.schemas.user import UserCreate
from app.services.knowledge import (
    ValidatedUpload,
    create_knowledge_base,
    create_query_failure,
    create_query_history,
    get_knowledge_document,
    get_knowledge_query,
    list_knowledge_bases,
    list_knowledge_documents,
    list_knowledge_queries,
    stage_knowledge_document,
)
from app.services.rag import (
    RAGCallError,
    RAGCompletion,
    answer_knowledge_question,
)
from app.services.users import create_user


async def make_actor(session: AsyncSession, suffix: str) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"rag-{suffix}@example.com",
            full_name="RAG Test",
            password="correct-horse-battery-staple",
            role=Role.ADMIN,
        ),
    )


def configured_settings() -> Settings:
    return Settings(
        embedding_provider="qwen",
        embedding_base_url="https://example.invalid/v1",
        embedding_model="text-embedding-test",
        embedding_api_key=SecretStr("test-only-key"),
    )


def upload(content: bytes) -> ValidatedUpload:
    from hashlib import sha256

    return ValidatedUpload("notes.txt", ".txt", "text/plain", content, sha256(content).hexdigest())


@pytest.mark.asyncio
async def test_create_base_snapshots_embedding_contract(session: AsyncSession) -> None:
    actor = await make_actor(session, "snapshot")
    base = await create_knowledge_base(
        session,
        KnowledgeBaseCreate(name="Policies", description="Team documents"),
        actor.id,
        configured_settings(),
    )

    assert base.embedding_provider == "qwen"
    assert base.embedding_base_url == "https://example.invalid/v1"
    assert base.embedding_model == "text-embedding-test"
    assert base.embedding_dimensions is None
    assert "test-only-key" not in repr(base)


@pytest.mark.asyncio
async def test_same_hash_in_same_base_is_unique(session: AsyncSession, tmp_path: Path) -> None:
    actor = await make_actor(session, "duplicate")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Duplicate check"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(session, base.id, actor.id, upload(b"same"), tmp_path)
    document_id = document.id

    with pytest.raises(AppError) as failure:
        await stage_knowledge_document(session, base.id, actor.id, upload(b"same"), tmp_path)

    assert failure.value.code == "KNOWLEDGE_DOCUMENT_DUPLICATE"
    assert await session.get(KnowledgeDocument, document_id) is not None


@pytest.mark.asyncio
async def test_same_hash_in_different_bases_is_allowed(
    session: AsyncSession, tmp_path: Path
) -> None:
    actor = await make_actor(session, "isolation")
    first = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="First RAG"), actor.id, configured_settings()
    )
    second = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Second RAG"), actor.id, configured_settings()
    )

    a = await stage_knowledge_document(session, first.id, actor.id, upload(b"same"), tmp_path)
    b = await stage_knowledge_document(session, second.id, actor.id, upload(b"same"), tmp_path)

    assert a.sha256 == b.sha256
    assert a.storage_path != b.storage_path


@pytest.mark.asyncio
async def test_database_unique_constraint_guards_duplicate_hash(session: AsyncSession) -> None:
    actor = await make_actor(session, "constraint")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Constraint RAG"), actor.id, configured_settings()
    )
    fields = dict(
        knowledge_base_id=base.id,
        uploaded_by_id=actor.id,
        original_name="same.txt",
        media_type="text/plain",
        size_bytes=4,
        sha256="a" * 64,
        storage_path="controlled/path.txt",
    )
    session.add(KnowledgeDocument(**fields))
    await session.commit()
    session.add(KnowledgeDocument(**fields))

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_document_must_belong_to_path_base(session: AsyncSession, tmp_path: Path) -> None:
    actor = await make_actor(session, "path")
    first = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Path first"), actor.id, configured_settings()
    )
    second = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Path second"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(session, first.id, actor.id, upload(b"doc"), tmp_path)

    with pytest.raises(AppError) as failure:
        await get_knowledge_document(session, second.id, document.id)
    assert failure.value.code == "KNOWLEDGE_DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_history_pages_are_descending(session: AsyncSession, tmp_path: Path) -> None:
    actor = await make_actor(session, "history")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="History RAG"), actor.id, configured_settings()
    )
    first = await stage_knowledge_document(session, base.id, actor.id, upload(b"first"), tmp_path)
    second = await stage_knowledge_document(session, base.id, actor.id, upload(b"second"), tmp_path)

    items, total = await list_knowledge_documents(session, base.id, page=1, page_size=1)
    bases, base_total = await list_knowledge_bases(session, page=1, page_size=1)

    assert total == 2
    assert [item.id for item in items] == [second.id]
    assert first.id < second.id
    assert base_total == 1
    assert [item.id for item in bases] == [base.id]
    assert (await session.scalars(select(KnowledgeDocument))).all()


def cited_completion() -> RAGCompletion:
    return RAGCompletion(
        answer="30 days",
        status=KnowledgeQueryStatus.SUCCESS,
        citations=[
            KnowledgeCitation(
                document_id=7,
                original_name="policy.pdf",
                chunk_id="document:7:chunk:0",
                chunk_index=0,
                page_number=1,
                excerpt="Return period is 30 days.",
                distance=0.1,
            )
        ],
        embedding_tokens=3,
        prompt_tokens=10,
        completion_tokens=4,
        total_tokens=17,
    )


@pytest.mark.asyncio
async def test_success_query_persists_verified_citations_and_usage(session: AsyncSession) -> None:
    actor = await make_actor(session, "query-success")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query success"), actor.id, configured_settings()
    )
    query = await create_query_history(
        session, base.id, actor.id, "Return period?", "qwen", "chat-test", cited_completion()
    )
    assert query.status is KnowledgeQueryStatus.SUCCESS
    assert query.citations[0]["chunk_id"] == "document:7:chunk:0"
    assert (query.embedding_tokens, query.total_tokens) == (3, 17)
    assert query.prompt_version == "rag-answer-v1"


@pytest.mark.asyncio
async def test_refused_query_persists_empty_citations(session: AsyncSession) -> None:
    actor = await make_actor(session, "query-refused")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query refused"), actor.id, configured_settings()
    )
    completion = RAGCompletion(
        "当前知识库中没有足够依据回答这个问题。",
        KnowledgeQueryStatus.REFUSED,
        [],
        3,
        None,
        None,
        3,
    )
    query = await create_query_history(
        session, base.id, actor.id, "Unknown?", "qwen", "chat-test", completion
    )
    assert query.status is KnowledgeQueryStatus.REFUSED
    assert query.citations == []
    assert query.total_tokens == 3


@pytest.mark.asyncio
async def test_provider_failure_persists_safe_failure_without_secret(session: AsyncSession) -> None:
    actor = await make_actor(session, "query-failure")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query failure"), actor.id, configured_settings()
    )
    query = await create_query_failure(
        session,
        base.id,
        actor.id,
        "Question?",
        "qwen",
        "chat-test",
        "RAG_PROVIDER_UNAVAILABLE",
        "向量服务暂时不可用",
    )
    assert query.status is KnowledgeQueryStatus.FAILURE
    assert query.citations == []
    assert query.error_code == "RAG_PROVIDER_UNAVAILABLE"
    assert "secret" not in repr(query)


@pytest.mark.asyncio
async def test_query_detail_requires_matching_knowledge_base(session: AsyncSession) -> None:
    actor = await make_actor(session, "query-path")
    first = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query path first"), actor.id, configured_settings()
    )
    second = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query path second"), actor.id, configured_settings()
    )
    query = await create_query_history(
        session, first.id, actor.id, "Question?", "qwen", "chat-test", cited_completion()
    )
    with pytest.raises(AppError) as failure:
        await get_knowledge_query(session, second.id, query.id)
    assert failure.value.code == "KNOWLEDGE_QUERY_NOT_FOUND"


@pytest.mark.asyncio
async def test_query_history_is_descending_and_paginated(session: AsyncSession) -> None:
    actor = await make_actor(session, "query-page")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query page"), actor.id, configured_settings()
    )
    first = await create_query_history(
        session, base.id, actor.id, "First?", "qwen", "chat-test", cited_completion()
    )
    second = await create_query_history(
        session, base.id, actor.id, "Second?", "qwen", "chat-test", cited_completion()
    )
    page, total = await list_knowledge_queries(session, base.id, 1, 1)
    assert total == 2
    assert [item.id for item in page] == [second.id]
    assert first.id < second.id


@pytest.mark.asyncio
async def test_external_calls_run_without_open_database_transaction(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, "query-tx")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query transaction"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(
        session, base.id, actor.id, upload(b"ready"), tmp_path
    )
    document.status = KnowledgeDocumentStatus.READY
    await session.commit()
    base_id, actor_id = base.id, actor.id
    document_id = document.id
    settings = configured_settings().model_copy(
        update={"llm_model": "chat-test", "llm_api_key": SecretStr("test-only-key")}
    )

    async def embed(texts: list[str], settings: Settings) -> SimpleNamespace:
        assert not session.in_transaction()
        return SimpleNamespace(vectors=[[0.1, 0.2]], total_tokens=3, dimensions=2)

    async def retrieve(*args: object) -> list[RetrievedChunk]:
        assert not session.in_transaction()
        await session.scalar(
            select(KnowledgeDocument.id).where(KnowledgeDocument.id == document_id)
        )
        assert session.in_transaction()
        return [
            RetrievedChunk(
                document_id=document_id,
                original_name="notes.txt",
                chunk_id=f"document:{document_id}:chunk:0",
                chunk_index=0,
                text="ready",
                distance=0.1,
            )
        ]

    async def chat(*args: object) -> RAGCompletion:
        assert not session.in_transaction()
        return replace(cited_completion(), embedding_tokens=None, total_tokens=14)

    monkeypatch.setattr("app.services.rag.request_embeddings", embed)
    monkeypatch.setattr("app.services.rag.create_chroma_client", AsyncMock(return_value=object()))
    monkeypatch.setattr("app.services.rag.close_chroma_client", AsyncMock())
    monkeypatch.setattr("app.services.rag.retrieve_chunks", retrieve)
    monkeypatch.setattr("app.services.rag.request_rag_answer", chat)

    query = await answer_knowledge_question(
        session, base_id, actor_id, KnowledgeQuestionCreate(question=" Return period? "), settings
    )
    assert query.status is KnowledgeQueryStatus.SUCCESS
    assert query.question == "Return period?"
    assert query.total_tokens == 17


@pytest.mark.asyncio
async def test_weak_evidence_refuses_without_chat_call(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, "query-weak")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query weak"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(
        session, base.id, actor.id, upload(b"ready"), tmp_path
    )
    document.status = KnowledgeDocumentStatus.READY
    await session.commit()
    settings = configured_settings()
    monkeypatch.setattr(
        "app.services.rag.request_embeddings",
        AsyncMock(return_value=SimpleNamespace(vectors=[[0.1]], total_tokens=2, dimensions=1)),
    )
    monkeypatch.setattr("app.services.rag.create_chroma_client", AsyncMock(return_value=object()))
    monkeypatch.setattr("app.services.rag.close_chroma_client", AsyncMock())
    monkeypatch.setattr("app.services.rag.retrieve_chunks", AsyncMock(return_value=[]))
    chat = Mock(side_effect=AssertionError("no evidence must not call Chat"))
    monkeypatch.setattr("app.services.rag.request_rag_answer", chat)

    query = await answer_knowledge_question(
        session, base.id, actor.id, KnowledgeQuestionCreate(question="Unknown?"), settings
    )
    assert query.status is KnowledgeQueryStatus.REFUSED
    assert query.citations == []
    assert query.total_tokens == 2
    chat.assert_not_called()


@pytest.mark.asyncio
async def test_chat_failure_saves_stable_history(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, "query-chat-error")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query chat error"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(
        session, base.id, actor.id, upload(b"ready"), tmp_path
    )
    document.status = KnowledgeDocumentStatus.READY
    await session.commit()
    settings = configured_settings().model_copy(
        update={"llm_model": "chat-test", "llm_api_key": SecretStr("test-only-key")}
    )
    monkeypatch.setattr(
        "app.services.rag.request_embeddings",
        AsyncMock(return_value=SimpleNamespace(vectors=[[0.1]], total_tokens=2, dimensions=1)),
    )
    monkeypatch.setattr("app.services.rag.create_chroma_client", AsyncMock(return_value=object()))
    monkeypatch.setattr("app.services.rag.close_chroma_client", AsyncMock())
    monkeypatch.setattr(
        "app.services.rag.retrieve_chunks",
        AsyncMock(
            return_value=[
                RetrievedChunk(
                    document_id=document.id,
                    original_name="notes.txt",
                    chunk_id=f"document:{document.id}:chunk:0",
                    chunk_index=0,
                    text="ready",
                    distance=0.1,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.rag.request_rag_answer",
        AsyncMock(
            side_effect=RAGCallError("RAG_INVALID_RESPONSE", "模型回答格式无效", status_code=502)
        ),
    )

    with pytest.raises(AppError) as failure:
        await answer_knowledge_question(
            session, base.id, actor.id, KnowledgeQuestionCreate(question="Question?"), settings
        )
    assert failure.value.code == "RAG_INVALID_RESPONSE"
    page, total = await list_knowledge_queries(session, base.id, 1, 20)
    assert total == 1
    assert page[0].status is KnowledgeQueryStatus.FAILURE
    assert page[0].error_message == "模型回答格式无效"


@pytest.mark.asyncio
async def test_embedding_contract_drift_stops_before_provider_call(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, "query-drift")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query drift"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(
        session, base.id, actor.id, upload(b"ready"), tmp_path
    )
    document.status = KnowledgeDocumentStatus.READY
    await session.commit()
    base_id, actor_id = base.id, actor.id
    embed = AsyncMock()
    monkeypatch.setattr("app.services.rag.request_embeddings", embed)
    changed = configured_settings().model_copy(update={"embedding_model": "different-model"})

    with pytest.raises(AppError) as failure:
        await answer_knowledge_question(
            session, base_id, actor_id, KnowledgeQuestionCreate(question="Question?"), changed
        )

    assert failure.value.code == "RAG_CONFIG_MISSING"
    embed.assert_not_awaited()
    history, total = await list_knowledge_queries(session, base_id, 1, 20)
    assert total == 1
    assert history[0].status is KnowledgeQueryStatus.FAILURE


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_stops_before_chroma(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, "query-dimension")
    base = await create_knowledge_base(
        session, KnowledgeBaseCreate(name="Query dimension"), actor.id, configured_settings()
    )
    document = await stage_knowledge_document(
        session, base.id, actor.id, upload(b"ready"), tmp_path
    )
    document.status = KnowledgeDocumentStatus.READY
    base.embedding_dimensions = 3
    await session.commit()
    base_id, actor_id = base.id, actor.id
    monkeypatch.setattr(
        "app.services.rag.request_embeddings",
        AsyncMock(return_value=SimpleNamespace(vectors=[[0.1, 0.2]], total_tokens=2, dimensions=2)),
    )
    chroma = AsyncMock()
    monkeypatch.setattr("app.services.rag.create_chroma_client", chroma)

    with pytest.raises(AppError) as failure:
        await answer_knowledge_question(
            session,
            base_id,
            actor_id,
            KnowledgeQuestionCreate(question="Question?"),
            configured_settings(),
        )

    assert failure.value.code == "RAG_CONFIG_MISSING"
    chroma.assert_not_awaited()
