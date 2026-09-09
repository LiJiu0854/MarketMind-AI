"""商品 Service 的真实 MySQL 集成测试。"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.user import Role
from app.schemas.product import ProductCreate, ProductFilters, ProductUpdate
from app.schemas.user import UserCreate
from app.services.products import (
    create_product,
    deactivate_product,
    get_product,
    list_products,
    update_product,
)
from app.services.users import create_user


async def make_actor(session: AsyncSession) -> int:
    user = await create_user(
        session,
        UserCreate(
            email="product-owner@example.com",
            full_name="Product Owner",
            password="correct-horse-battery-staple",
            role=Role.OPERATOR,
        ),
    )
    return user.id


def product_data(index: int, **changes: object) -> ProductCreate:
    payload: dict[str, object] = {
        "sku": f"sku-{index}",
        "title": f"Product {index}",
        "price": "19.90",
        "currency": "cny",
    }
    payload.update(changes)
    return ProductCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_create_product_records_actor_and_normalized_values(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)

    product = await create_product(session, product_data(1), actor_id)

    assert product.id is not None
    assert product.sku == "SKU-1"
    assert product.price == Decimal("19.90")
    assert product.created_by_id == actor_id


@pytest.mark.asyncio
async def test_duplicate_sku_rolls_back_session(session: AsyncSession) -> None:
    actor_id = await make_actor(session)
    await create_product(session, product_data(1), actor_id)

    with pytest.raises(AppError) as exc_info:
        await create_product(session, product_data(2, sku=" SKU-1 "), actor_id)

    assert exc_info.value.code == "PRODUCT_SKU_CONFLICT"
    assert await create_product(session, product_data(3), actor_id)


@pytest.mark.asyncio
async def test_get_product_rejects_missing_id(session: AsyncSession) -> None:
    with pytest.raises(AppError) as exc_info:
        await get_product(session, 999999)

    assert exc_info.value.code == "PRODUCT_NOT_FOUND"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_products_filters_and_pages(session: AsyncSession) -> None:
    actor_id = await make_actor(session)
    await create_product(session, product_data(1), actor_id)
    second = await create_product(
        session,
        product_data(2, brand="Brand B", category="Category B"),
        actor_id,
    )
    await create_product(session, product_data(3, is_active=False), actor_id)

    result = await list_products(
        session,
        ProductFilters(brand="Brand B", category="Category B", is_active=True),
        page=1,
        page_size=1,
    )

    assert result.total == 1
    assert [item.id for item in result.items] == [second.id]


@pytest.mark.asyncio
async def test_update_product_is_partial_and_rejects_duplicate_sku(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)
    first = await create_product(session, product_data(1), actor_id)
    second = await create_product(session, product_data(2), actor_id)

    updated = await update_product(session, second, ProductUpdate(title="Updated"))
    assert updated.title == "Updated"
    assert updated.sku == "SKU-2"

    with pytest.raises(AppError) as exc_info:
        await update_product(session, second, ProductUpdate(sku=first.sku))

    assert exc_info.value.code == "PRODUCT_SKU_CONFLICT"


@pytest.mark.asyncio
async def test_deactivate_product_keeps_record(session: AsyncSession) -> None:
    actor_id = await make_actor(session)
    product = await create_product(session, product_data(1), actor_id)

    result = await deactivate_product(session, product)

    assert result.is_active is False
    assert await get_product(session, product.id) is product
