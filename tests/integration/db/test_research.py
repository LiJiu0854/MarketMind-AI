"""Research creation uses the real MySQL test schema."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentStatus
from app.models.product import Product
from app.models.research import ResearchRun, ResearchStatus
from app.models.user import Role
from app.schemas.knowledge import RetrievedChunk
from app.schemas.product import ProductCreate
from app.schemas.research import ResearchAction, ResearchCreate
from app.schemas.user import UserCreate
from app.services.document_ingestion import EmbeddingCompletion
from app.services.products import create_product
from app.services.research import (
    ResearchUsage,
    append_research_step,
    create_research_run,
    get_research_run,
    list_research_runs,
    mark_research_running,
)
from app.services.research_agent import ActionCompletion, run_research_actions
from app.services.research_tools import search_knowledge
from app.services.users import create_user


def settings() -> Settings:
    return Settings(
        llm_provider="test",
        llm_model="research-model",
        llm_api_key=SecretStr("test-key"),
        embedding_provider="test",
        embedding_base_url="https://example.invalid/v1",
        embedding_model="embedding-model",
        embedding_api_key=SecretStr("test-key"),
    )


async def setup_rows(session: AsyncSession, suffix: str) -> tuple[int, int, int]:
    actor = await create_user(
        session,
        UserCreate(
            email=f"research-{suffix}@example.com",
            full_name="Research Test",
            password="correct-horse-battery-staple",
            role=Role.ADMIN,
        ),
    )
    product = await create_product(
        session,
        ProductCreate(
            sku=f"research-{suffix}",
            title="Original title",
            description="Original text",
            bullet_points=["Useful"],
            brand="Brand",
            category="Category",
            price=Decimal("12.00"),
            currency="CNY",
        ),
        actor.id,
    )
    base = KnowledgeBase(
        name=f"Research base {suffix}",
        created_by_id=actor.id,
        embedding_provider="test",
        embedding_base_url="https://example.invalid/v1",
        embedding_model="embedding-model",
        embedding_dimensions=3,
    )
    session.add(base)
    await session.flush()
    document = KnowledgeDocument(
        knowledge_base_id=base.id,
        uploaded_by_id=actor.id,
        original_name="source.txt",
        media_type="text/plain",
        size_bytes=4,
        sha256="a" * 64,
        storage_path=f"{base.id}/source.txt",
        status=KnowledgeDocumentStatus.READY,
    )
    session.add(document)
    await session.commit()
    return actor.id, product.id, base.id


@pytest.mark.asyncio
async def test_create_snapshots_and_rejects_active_duplicate(session: AsyncSession) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "snapshot")
    payload = ResearchCreate(goal=" Compare ", knowledge_base_ids=[base_id])
    run = await create_research_run(session, product_id, actor_id, payload, settings())
    assert run.goal == "Compare"
    assert run.product_snapshot["title"] == "Original title"
    assert run.status == ResearchStatus.PENDING
    assert (
        run.prompt_tokens == run.completion_tokens == run.embedding_tokens == run.total_tokens == 0
    )
    product = await session.get_one(Product, product_id)
    product.title = "Later title"
    await session.commit()
    assert (await get_research_run(session, product_id, run.id)).product_snapshot[
        "title"
    ] == "Original title"
    with pytest.raises(AppError) as failure:
        await create_research_run(session, product_id, actor_id, payload, settings())
    assert failure.value.status_code == 409
    assert await session.scalar(select(func.count()).select_from(ResearchRun)) == 1


@pytest.mark.asyncio
async def test_create_rejects_missing_unready_and_mismatched_bases(session: AsyncSession) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "invalid")
    payload = ResearchCreate(goal="Compare", knowledge_base_ids=[base_id])
    with pytest.raises(AppError) as missing:
        await create_research_run(session, 999999, actor_id, payload, settings())
    assert missing.value.status_code == 404
    with pytest.raises(AppError) as missing_base:
        await create_research_run(
            session,
            product_id,
            actor_id,
            ResearchCreate(goal="Compare", knowledge_base_ids=[999999]),
            settings(),
        )
    assert missing_base.value.status_code == 404
    base = await session.get_one(KnowledgeBase, base_id)
    base.embedding_model = "another-model"
    await session.commit()
    with pytest.raises(AppError) as mismatch:
        await create_research_run(session, product_id, actor_id, payload, settings())
    assert mismatch.value.status_code == 503
    base.embedding_model = "embedding-model"
    document = await session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base_id)
    )
    assert document is not None
    document.status = KnowledgeDocumentStatus.FAILURE
    await session.commit()
    with pytest.raises(AppError) as unready:
        await create_research_run(session, product_id, actor_id, payload, settings())
    assert unready.value.status_code == 409


@pytest.mark.asyncio
async def test_history_is_product_scoped_and_descending(session: AsyncSession) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "history")
    first = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="First", knowledge_base_ids=[base_id]),
        settings(),
    )
    first.status = ResearchStatus.FAILURE
    await session.commit()
    second = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Second", knowledge_base_ids=[base_id]),
        settings(),
    )
    items, total = await list_research_runs(session, product_id, 1, 20)
    assert total == 2
    assert [item.id for item in items] == [second.id, first.id]
    with pytest.raises(AppError) as failure:
        await get_research_run(session, product_id + 999, first.id)
    assert failure.value.status_code == 404


@pytest.mark.asyncio
async def test_product_row_lock_serializes_independent_sessions(test_engine: AsyncEngine) -> None:
    # This case uses committed setup rows, so both independent connections can see them.
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        actor_id, product_id, base_id = await setup_rows(setup, "concurrent")
    payload = ResearchCreate(goal="Compare", knowledge_base_ids=[base_id])

    async def attempt() -> int:
        async with AsyncSession(test_engine, expire_on_commit=False) as connection:
            try:
                await create_research_run(connection, product_id, actor_id, payload, settings())
                return 202
            except AppError as exc:
                return exc.status_code

    try:
        assert sorted(await asyncio.gather(attempt(), attempt())) == [202, 409]
        async with AsyncSession(test_engine) as check:
            count = await check.scalar(
                select(func.count())
                .select_from(ResearchRun)
                .where(ResearchRun.product_id == product_id)
            )
        assert count == 1
    finally:
        # Exact IDs only; never clean unrelated user rows.
        from sqlalchemy import delete

        from app.models.user import User

        async with AsyncSession(test_engine) as cleanup:
            await cleanup.execute(delete(ResearchRun).where(ResearchRun.product_id == product_id))
            await cleanup.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base_id)
            )
            await cleanup.execute(delete(KnowledgeBase).where(KnowledgeBase.id == base_id))
            await cleanup.execute(delete(Product).where(Product.id == product_id))
            await cleanup.execute(delete(User).where(User.id == actor_id))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_search_rechecks_mysql_document_and_filename(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "tool")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        settings(),
    )
    ready = await session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base_id)
    )
    assert ready is not None
    unready = KnowledgeDocument(
        knowledge_base_id=base_id,
        uploaded_by_id=actor_id,
        original_name="not-ready.txt",
        media_type="text/plain",
        size_bytes=4,
        sha256="b" * 64,
        storage_path=f"{base_id}/not-ready.txt",
        status=KnowledgeDocumentStatus.FAILURE,
    )
    session.add(unready)
    await session.commit()
    ready_id = ready.id
    unready_id = unready.id
    monkeypatch.setattr(
        "app.services.research_tools.request_embeddings",
        AsyncMock(return_value=EmbeddingCompletion([[0.1, 0.2, 0.3]], 5, 3)),
    )
    monkeypatch.setattr(
        "app.services.research_tools.create_chroma_client",
        AsyncMock(return_value=object()),
    )
    close = AsyncMock()
    monkeypatch.setattr("app.services.research_tools.close_chroma_client", close)
    chunks = [
        RetrievedChunk(
            document_id=document_id,
            original_name="forged.txt",
            chunk_id=f"document:{document_id}:chunk:0",
            chunk_index=0,
            page_number=1,
            text="verified",
            distance=0.1,
        )
        for document_id in (ready_id, unready_id)
    ]
    monkeypatch.setattr(
        "app.services.research_tools.retrieve_chunks",
        AsyncMock(return_value=chunks),
    )
    result = await search_knowledge(session, run, base_id, "price", settings())
    assert len(result.evidence) == 1
    assert result.evidence[0].original_name == "source.txt"
    assert result.evidence[0].source_id == f"kb:{base_id}:document:{ready_id}:chunk:0"
    assert result.embedding_tokens == 5
    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_rejects_configuration_drift_before_embedding(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "drift")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        settings(),
    )
    embedding = AsyncMock()
    monkeypatch.setattr("app.services.research_tools.request_embeddings", embedding)
    changed = settings().model_copy(update={"embedding_model": "other"})
    with pytest.raises(AppError) as failure:
        await search_knowledge(session, run, base_id, "price", changed)
    assert failure.value.status_code == 503
    embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_records_step_and_unknown_usage(session: AsyncSession) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "checkpoint")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        settings(),
    )
    running = await mark_research_running(session, run.id)
    assert running is not None
    assert running.attempt_count == 1
    step = {"number": 1, "action": {"action": "read_product"}, "source_ids": []}
    saved = await append_research_step(
        session,
        run.id,
        step,
        [],
        ResearchUsage(prompt_tokens=None, completion_tokens=2, embedding_tokens=0),
    )
    assert saved is not None
    assert len(saved.steps) == 1
    assert saved.prompt_tokens is None
    assert saved.completion_tokens == 2
    assert saved.embedding_tokens == 0
    assert saved.total_tokens is None
    saved = await append_research_step(
        session,
        run.id,
        {"number": 2, "action": {"action": "finish"}, "source_ids": []},
        [],
        ResearchUsage(prompt_tokens=3, completion_tokens=1, embedding_tokens=0),
    )
    assert saved is not None
    assert saved.prompt_tokens is None
    assert saved.completion_tokens == 3
    assert saved.total_tokens is None


@pytest.mark.asyncio
async def test_terminal_research_is_not_restarted(session: AsyncSession) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "terminal")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        settings(),
    )
    run.status = ResearchStatus.FAILURE
    await session.commit()
    assert await mark_research_running(session, run.id) is None


@pytest.mark.asyncio
async def test_action_loop_resumes_after_committed_finish_without_repeating_tool(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_id, product_id, base_id = await setup_rows(session, "loop")
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="Compare", knowledge_base_ids=[base_id]),
        settings(),
    )
    await mark_research_running(session, run.id)
    decisions = AsyncMock(
        side_effect=[
            ActionCompletion(ResearchAction(action="read_product"), 4, 1),
            ActionCompletion(ResearchAction(action="finish"), 3, 1),
        ]
    )
    monkeypatch.setattr("app.services.research_agent.request_research_action", decisions)
    sessions = async_sessionmaker(
        await session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first = await run_research_actions(run.id, sessions, settings())
    assert first is not None
    assert [step["action"] for step in first.steps] == [
        {"action": "read_product"},
        {"action": "finish"},
    ]
    assert len(first.evidence) == 1
    assert first.prompt_tokens == 7
    assert first.completion_tokens == 2
    assert first.total_tokens == 9
    second = await run_research_actions(run.id, sessions, settings())
    assert second is not None
    assert len(second.steps) == 2
    assert decisions.await_count == 2
