"""商品 Excel 导入的真实 MySQL 集成测试。"""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.products as products_service
from app.core.errors import AppError
from app.models.product import Product
from app.models.user import Role
from app.schemas.product import (
    ProductCreate,
    ProductImportError,
    ProductImportResult,
)
from app.schemas.user import UserCreate
from app.services.product_excel import ProductImportCandidate
from app.services.products import (
    create_product,
    find_existing_skus,
    import_products,
)
from app.services.users import create_user


async def make_actor(session: AsyncSession) -> int:
    user = await create_user(
        session,
        UserCreate(
            email="product-import@example.com",
            full_name="Product Importer",
            password="correct-horse-battery-staple",
            role=Role.OPERATOR,
        ),
    )
    return user.id


def candidate(row: int, sku: str) -> ProductImportCandidate:
    return ProductImportCandidate(
        row=row,
        data=ProductCreate(
            sku=sku,
            title=f"Product {sku}",
            description="A useful product description",
            bullet_points=["First point", "Second point", "Third point"],
            brand="Brand",
            category="Category",
            price=Decimal("19.90"),
            currency="CNY",
        ),
    )


def row_error(row: int = 3) -> ProductImportError:
    return ProductImportError(
        row=row,
        field="price",
        code="INVALID_PRICE",
        message="价格格式无效",
    )


def test_product_import_result_keeps_counts_and_errors() -> None:
    error = row_error()
    result = ProductImportResult(
        total_rows=2,
        imported_rows=1,
        failed_rows=1,
        errors=[error],
    )

    assert result.model_dump() == {
        "total_rows": 2,
        "imported_rows": 1,
        "failed_rows": 1,
        "errors": [error.model_dump()],
    }


def test_product_import_result_rejects_inconsistent_totals() -> None:
    with pytest.raises(ValidationError):
        ProductImportResult(
            total_rows=3,
            imported_rows=1,
            failed_rows=1,
            errors=[],
        )


@pytest.mark.asyncio
async def test_find_existing_skus_returns_only_matches(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)
    await create_product(session, candidate(2, "SKU-1").data, actor_id)

    assert await find_existing_skus(session, {"SKU-1", "SKU-2"}) == {"SKU-1"}
    assert await find_existing_skus(session, set()) == set()


@pytest.mark.asyncio
async def test_import_products_writes_valid_rows_and_preserves_row_errors(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)

    result = await import_products(
        session,
        [candidate(2, "SKU-1"), candidate(4, "SKU-2")],
        [row_error(3)],
        actor_id,
    )

    products = (await session.scalars(select(Product).order_by(Product.id))).all()
    assert result == ProductImportResult(
        total_rows=3,
        imported_rows=2,
        failed_rows=1,
        errors=[row_error(3)],
    )
    assert [product.sku for product in products] == ["SKU-1", "SKU-2"]
    assert {product.created_by_id for product in products} == {actor_id}


@pytest.mark.asyncio
async def test_import_products_reports_database_duplicate_and_keeps_other_rows(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)
    await create_product(session, candidate(2, "SKU-1").data, actor_id)

    result = await import_products(
        session,
        [candidate(2, "SKU-1"), candidate(3, "SKU-2")],
        [],
        actor_id,
    )

    products = (await session.scalars(select(Product).order_by(Product.id))).all()
    assert [product.sku for product in products] == ["SKU-1", "SKU-2"]
    assert result.imported_rows == 1
    assert result.failed_rows == 1
    assert result.errors == [
        ProductImportError(
            row=2,
            field="sku",
            code="DUPLICATE_SKU_IN_DATABASE",
            message="SKU 已存在",
        )
    ]


@pytest.mark.asyncio
async def test_import_products_with_only_errors_writes_nothing(
    session: AsyncSession,
) -> None:
    actor_id = await make_actor(session)

    result = await import_products(session, [], [row_error()], actor_id)

    assert result == ProductImportResult(
        total_rows=1,
        imported_rows=0,
        failed_rows=1,
        errors=[row_error()],
    )
    assert (await session.scalars(select(Product))).all() == []


@pytest.mark.asyncio
async def test_import_products_rolls_back_concurrent_sku_conflict(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = await make_actor(session)
    await create_product(session, candidate(2, "SKU-1").data, actor_id)

    async def miss_existing_skus(
        session: AsyncSession,
        skus: set[str],
    ) -> set[str]:
        del session, skus
        return set()

    monkeypatch.setattr(products_service, "find_existing_skus", miss_existing_skus)

    with pytest.raises(AppError) as exc_info:
        await import_products(
            session,
            [candidate(2, "SKU-1"), candidate(3, "SKU-2")],
            [],
            actor_id,
        )

    assert exc_info.value.code == "PRODUCT_IMPORT_CONFLICT"
    assert exc_info.value.status_code == 409
    assert [
        product.sku
        for product in (await session.scalars(select(Product).order_by(Product.id))).all()
    ] == ["SKU-1"]
