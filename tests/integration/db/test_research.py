"""Research creation uses the real MySQL test schema."""

import asyncio
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentStatus
from app.models.product import Product
from app.models.research import ResearchRun, ResearchStatus
from app.models.user import Role
from app.schemas.product import ProductCreate
from app.schemas.research import ResearchCreate
from app.schemas.user import UserCreate
from app.services.products import create_product
from app.services.research import create_research_run, get_research_run, list_research_runs
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
