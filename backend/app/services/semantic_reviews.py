"""商品语义审核的快照和数据库服务。"""

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.product import Product
from app.models.semantic_review import SemanticReview, SemanticReviewStatus
from app.schemas.semantic_review import ProductSnapshot

PROMPT_VERSION = "semantic-review-v1"
MAX_REVIEW_INPUT_CHARS = 20_000
ACTIVE_REVIEW_STATUSES = (
    SemanticReviewStatus.PENDING,
    SemanticReviewStatus.RUNNING,
)


def build_product_snapshot(product: Product) -> ProductSnapshot:
    """把可变 ORM 商品转换成独立、可序列化的审核输入。"""
    return ProductSnapshot(
        sku=product.sku,
        title=product.title,
        description=product.description,
        bullet_points=product.bullet_points,
        brand=product.brand,
        category=product.category,
        price=product.price,
        currency=product.currency,
        is_active=product.is_active,
    )


async def create_semantic_review(
    session: AsyncSession,
    product_id: int,
    requested_by_id: int,
    provider: str,
    model: str,
) -> SemanticReview:
    """在商品行锁内验证边界并创建一条待处理审核。"""
    try:
        product = await session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            raise AppError("PRODUCT_NOT_FOUND", "商品不存在", 404)

        snapshot_json = build_product_snapshot(product).model_dump(mode="json")
        if len(json.dumps(snapshot_json, ensure_ascii=False)) > MAX_REVIEW_INPUT_CHARS:
            raise AppError(
                "SEMANTIC_REVIEW_INPUT_TOO_LARGE",
                "商品内容过长，无法发起语义审核",
                422,
            )

        active_id = await session.scalar(
            select(SemanticReview.id).where(
                SemanticReview.product_id == product_id,
                SemanticReview.status.in_(ACTIVE_REVIEW_STATUSES),
            )
        )
        if active_id is not None:
            raise AppError(
                "SEMANTIC_REVIEW_ALREADY_ACTIVE",
                "商品已有进行中的语义审核",
                409,
            )

        review = SemanticReview(
            product_id=product_id,
            requested_by_id=requested_by_id,
            product_snapshot=snapshot_json,
            provider=provider,
            model=model,
            prompt_version=PROMPT_VERSION,
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
        return review
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


async def get_semantic_review(
    session: AsyncSession,
    product_id: int,
    review_id: int,
) -> SemanticReview:
    """按商品路径读取审核，阻止跨商品 ID 读取。"""
    review = await session.scalar(
        select(SemanticReview).where(
            SemanticReview.id == review_id,
            SemanticReview.product_id == product_id,
        )
    )
    if review is None:
        raise AppError("SEMANTIC_REVIEW_NOT_FOUND", "语义审核不存在", 404)
    return review


async def get_semantic_review_by_id(
    session: AsyncSession,
    review_id: int,
) -> SemanticReview | None:
    """供 Worker 使用主键读取审核，不转换不存在结果。"""
    return await session.get(SemanticReview, review_id)


async def list_semantic_reviews(
    session: AsyncSession,
    product_id: int,
    page: int,
    page_size: int,
) -> tuple[list[SemanticReview], int]:
    """按 ID 倒序返回指定商品的审核历史。"""
    if await session.get(Product, product_id) is None:
        raise AppError("PRODUCT_NOT_FOUND", "商品不存在", 404)

    total = (
        await session.scalar(
            select(func.count())
            .select_from(SemanticReview)
            .where(SemanticReview.product_id == product_id)
        )
        or 0
    )
    items = list(
        await session.scalars(
            select(SemanticReview)
            .where(SemanticReview.product_id == product_id)
            .order_by(SemanticReview.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total
