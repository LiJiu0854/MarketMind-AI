"""商品业务服务。"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import AppError
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductFilters,
    ProductImportError,
    ProductImportResult,
    ProductPage,
    ProductRead,
    ProductUpdate,
)
from app.services.product_excel import ProductImportCandidate


def _sku_conflict() -> AppError:
    return AppError(
        code="PRODUCT_SKU_CONFLICT",
        message="SKU 已存在",
        status_code=409,
    )


def _product_filter_conditions(
    filters: ProductFilters,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.sku is not None:
        conditions.append(Product.sku == filters.sku)
    if filters.brand is not None:
        conditions.append(Product.brand == filters.brand)
    if filters.category is not None:
        conditions.append(Product.category == filters.category)
    if filters.is_active is not None:
        conditions.append(Product.is_active == filters.is_active)
    return conditions


async def create_product(
    session: AsyncSession,
    data: ProductCreate,
    created_by_id: int,
) -> Product:
    """创建商品；SKU 冲突时返回稳定业务错误。"""
    try:
        existing = await session.scalar(select(Product).where(Product.sku == data.sku))
        if existing is not None:
            raise _sku_conflict()

        product = Product(**data.model_dump(), created_by_id=created_by_id)
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _sku_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def get_product(session: AsyncSession, product_id: int) -> Product:
    """按 ID 读取商品，不存在时抛 404 AppError。"""
    product = await session.get(Product, product_id)
    if product is None:
        raise AppError(
            code="PRODUCT_NOT_FOUND",
            message="商品不存在",
            status_code=404,
        )
    return product


async def list_products(
    session: AsyncSession,
    filters: ProductFilters,
    page: int,
    page_size: int,
) -> ProductPage:
    """按固定条件筛选，按 ID 稳定分页。"""
    conditions = _product_filter_conditions(filters)
    total = (
        await session.scalar(
            select(func.count()).select_from(Product).where(*conditions)
        )
        or 0
    )
    products = (
        await session.scalars(
            select(Product)
            .where(*conditions)
            .order_by(Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return ProductPage(
        items=[ProductRead.model_validate(product) for product in products],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_products_for_export(
    session: AsyncSession,
    filters: ProductFilters,
) -> list[Product]:
    """返回符合列表筛选语义的全部商品。"""
    return list(
        await session.scalars(
            select(Product)
            .where(*_product_filter_conditions(filters))
            .order_by(Product.id)
        )
    )


async def update_product(
    session: AsyncSession,
    product: Product,
    data: ProductUpdate,
) -> Product:
    """只更新调用者实际提交的非空字段。"""
    updates = data.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return product

    try:
        sku = updates.get("sku")
        if sku is not None:
            existing = await session.scalar(
                select(Product).where(Product.sku == sku, Product.id != product.id)
            )
            if existing is not None:
                raise _sku_conflict()

        for field, value in updates.items():
            setattr(product, field, value)

        await session.commit()
        await session.refresh(product)
        return product
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _sku_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def deactivate_product(
    session: AsyncSession,
    product: Product,
) -> Product:
    """软停用商品并保留数据库记录。"""
    try:
        product.is_active = False
        await session.commit()
        await session.refresh(product)
        return product
    except Exception:
        await session.rollback()
        raise


async def find_existing_skus(
    session: AsyncSession,
    skus: set[str],
) -> set[str]:
    """一次查询返回数据库中已经存在的 SKU。"""
    if not skus:
        return set()
    return set(await session.scalars(select(Product.sku).where(Product.sku.in_(skus))))


async def import_products(
    session: AsyncSession,
    candidates: list[ProductImportCandidate],
    row_errors: list[ProductImportError],
    created_by_id: int,
) -> ProductImportResult:
    """跳过行级错误，在一次事务中写入所有合格商品。"""
    try:
        existing_skus = await find_existing_skus(
            session,
            {candidate.data.sku for candidate in candidates},
        )
        errors = [*row_errors]
        products: list[Product] = []
        for candidate in candidates:
            if candidate.data.sku in existing_skus:
                errors.append(
                    ProductImportError(
                        row=candidate.row,
                        field="sku",
                        code="DUPLICATE_SKU_IN_DATABASE",
                        message="SKU 已存在",
                    )
                )
            else:
                products.append(
                    Product(
                        **candidate.data.model_dump(),
                        created_by_id=created_by_id,
                    )
                )

        if products:
            session.add_all(products)
            await session.commit()

        errors.sort(key=lambda error: error.row)
        return ProductImportResult(
            total_rows=len(products) + len(errors),
            imported_rows=len(products),
            failed_rows=len(errors),
            errors=errors,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            code="PRODUCT_IMPORT_CONFLICT",
            message="导入期间 SKU 发生冲突，请重新导入",
            status_code=409,
        ) from exc
    except Exception:
        await session.rollback()
        raise
