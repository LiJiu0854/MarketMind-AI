"""Real MySQL knowledge-base contract tests against marketmind_test."""

from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeDocument
from app.models.user import Role, User
from app.schemas.knowledge import KnowledgeBaseCreate
from app.schemas.user import UserCreate
from app.services.knowledge import (
    ValidatedUpload,
    create_knowledge_base,
    get_knowledge_document,
    list_knowledge_bases,
    list_knowledge_documents,
    stage_knowledge_document,
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
