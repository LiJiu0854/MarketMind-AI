"""语义审核 Service 的真实 MySQL 集成测试。"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.models.product import Product
from app.models.semantic_review import SemanticReview, SemanticReviewStatus
from app.models.user import Role, User
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.user import UserCreate
from app.services.products import create_product, update_product
from app.services.semantic_reviews import (
    create_semantic_review,
    get_semantic_review,
    get_semantic_review_by_id,
    list_semantic_reviews,
)
from app.services.users import create_user


async def make_actor_and_product(
    session: AsyncSession,
    *,
    suffix: str = "default",
    description: str = "A useful product description",
) -> tuple[User, Product]:
    actor = await create_user(
        session,
        UserCreate(
            email=f"semantic-review-{suffix}@example.com",
            full_name="Semantic Reviewer",
            password="correct-horse-battery-staple",
            role=Role.OPERATOR,
        ),
    )
    product = await create_product(
        session,
        ProductCreate(
            sku=f"review-{suffix}",
            title="Useful Product",
            description=description,
            bullet_points=["First point", "Second point", "Third point"],
            brand="Brand",
            category="Category",
            price=Decimal("19.90"),
            currency="CNY",
        ),
        actor.id,
    )
    return actor, product


@pytest.mark.asyncio
async def test_create_review_freezes_snapshot_and_lists_newest_first(
    session: AsyncSession,
) -> None:
    actor, product = await make_actor_and_product(session)

    first = await create_semantic_review(
        session,
        product_id=product.id,
        requested_by_id=actor.id,
        provider="openai",
        model="test-model",
    )
    original_snapshot = dict(first.product_snapshot)
    assert first.status is SemanticReviewStatus.PENDING
    assert first.product_snapshot["price"] == "19.90"
    assert first.requested_by_id == actor.id

    await update_product(session, product, ProductUpdate(title="Changed Later"))
    first.status = SemanticReviewStatus.SUCCESS
    await session.commit()
    second = await create_semantic_review(
        session,
        product_id=product.id,
        requested_by_id=actor.id,
        provider="openai",
        model="test-model",
    )

    items, total = await list_semantic_reviews(
        session, product.id, page=1, page_size=20
    )
    assert total == 2
    assert [item.id for item in items] == [second.id, first.id]
    assert first.product_snapshot == original_snapshot
    assert second.product_snapshot["title"] == "Changed Later"
    assert await get_semantic_review_by_id(session, first.id) is first


@pytest.mark.asyncio
async def test_active_review_conflicts_but_failure_allows_new_history(
    session: AsyncSession,
) -> None:
    actor, product = await make_actor_and_product(session, suffix="active")
    actor_id = actor.id
    product_id = product.id
    first = await create_semantic_review(
        session,
        product_id=product_id,
        requested_by_id=actor_id,
        provider="openai",
        model="test-model",
    )

    with pytest.raises(AppError) as exc_info:
        await create_semantic_review(
            session,
            product_id=product_id,
            requested_by_id=actor_id,
            provider="openai",
            model="test-model",
        )
    assert exc_info.value.code == "SEMANTIC_REVIEW_ALREADY_ACTIVE"
    assert exc_info.value.status_code == 409

    first.status = SemanticReviewStatus.FAILURE
    await session.commit()
    assert await create_semantic_review(
        session,
        product_id=product_id,
        requested_by_id=actor_id,
        provider="openai",
        model="test-model",
    )


@pytest.mark.asyncio
async def test_review_must_belong_to_product(session: AsyncSession) -> None:
    actor, product = await make_actor_and_product(session, suffix="owner")
    _, other_product = await make_actor_and_product(session, suffix="other")
    review = await create_semantic_review(
        session,
        product_id=product.id,
        requested_by_id=actor.id,
        provider="openai",
        model="test-model",
    )

    with pytest.raises(AppError) as exc_info:
        await get_semantic_review(session, other_product.id, review.id)

    assert exc_info.value.code == "SEMANTIC_REVIEW_NOT_FOUND"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_oversized_snapshot_returns_422_without_writing(
    session: AsyncSession,
) -> None:
    actor, product = await make_actor_and_product(
        session,
        suffix="large",
        description="x" * 20_001,
    )

    with pytest.raises(AppError) as exc_info:
        await create_semantic_review(
            session,
            product_id=product.id,
            requested_by_id=actor.id,
            provider="openai",
            model="test-model",
        )

    assert exc_info.value.code == "SEMANTIC_REVIEW_INPUT_TOO_LARGE"
    assert exc_info.value.status_code == 422
    assert await session.scalar(select(func.count()).select_from(SemanticReview)) == 0


@pytest.mark.asyncio
async def test_two_sessions_create_only_one_active_review(
    test_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        actor, product = await make_actor_and_product(setup_session, suffix="concurrent")

    async def create_with_independent_session() -> SemanticReview:
        async with session_factory() as independent_session:
            return await create_semantic_review(
                independent_session,
                product_id=product.id,
                requested_by_id=actor.id,
                provider="openai",
                model="test-model",
            )

    try:
        results = await asyncio.gather(
            create_with_independent_session(),
            create_with_independent_session(),
            return_exceptions=True,
        )
        reviews = [item for item in results if isinstance(item, SemanticReview)]
        errors = [item for item in results if isinstance(item, AppError)]
        assert len(reviews) == 1
        assert len(errors) == 1
        assert errors[0].code == "SEMANTIC_REVIEW_ALREADY_ACTIVE"

        async with session_factory() as check_session:
            total = await check_session.scalar(
                select(func.count()).select_from(SemanticReview)
            )
            assert total == 1
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(SemanticReview).where(SemanticReview.product_id == product.id)
            )
            await cleanup_session.execute(delete(Product).where(Product.id == product.id))
            await cleanup_session.execute(delete(User).where(User.id == actor.id))
            await cleanup_session.commit()
