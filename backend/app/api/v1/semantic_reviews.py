"""商品 Listing 语义审核 API。"""

from typing import Annotated

from celery.exceptions import CeleryError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Query, Request, status
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, require_roles
from app.core.config import Settings
from app.core.errors import AppError
from app.models.semantic_review import SemanticReview
from app.models.user import Role, User
from app.schemas.semantic_review import (
    SemanticReviewCreated,
    SemanticReviewPage,
    SemanticReviewRead,
)
from app.services.semantic_reviews import (
    create_semantic_review,
    get_semantic_review,
    list_semantic_reviews,
    mark_review_failure,
    set_review_task_id,
)
from app.tasks.semantic_review import generate_semantic_review

ReviewManager = Annotated[
    User,
    Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
]

router = APIRouter(
    prefix="/products",
    tags=["LLM 语义审核"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/{product_id}/semantic-reviews",
    response_model=SemanticReviewCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_product_semantic_review(
    product_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ReviewManager,
) -> SemanticReviewCreated:
    """创建固定快照并把审核投递给 Celery。"""
    settings: Settings = request.app.state.settings
    if not settings.llm_model or settings.llm_api_key is None:
        raise AppError(
            "SEMANTIC_REVIEW_CONFIG_MISSING",
            "LLM 审核配置缺失",
            503,
        )

    review = await create_semantic_review(
        session,
        product_id=product_id,
        requested_by_id=actor.id,
        provider=settings.llm_provider,
        model=settings.llm_model,
    )
    try:
        queued = generate_semantic_review.delay(review.id)
    except (BrokerOperationalError, CeleryError, RedisError) as exc:
        await mark_review_failure(
            session,
            review.id,
            "REVIEW_DISPATCH_FAILED",
            "审核任务投递失败",
        )
        raise AppError(
            "SEMANTIC_REVIEW_DISPATCH_FAILED",
            "审核任务投递服务暂时不可用",
            503,
        ) from exc

    review = await set_review_task_id(session, review.id, queued.id)
    return SemanticReviewCreated(
        review_id=review.id,
        task_id=queued.id,
        status=review.status,
    )


@router.get(
    "/{product_id}/semantic-reviews",
    response_model=SemanticReviewPage,
)
async def read_semantic_reviews(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SemanticReviewPage:
    """分页读取 MySQL 中的商品审核历史。"""
    items, total = await list_semantic_reviews(
        session,
        product_id,
        page,
        page_size,
    )
    return SemanticReviewPage(
        items=[SemanticReviewRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{product_id}/semantic-reviews/{review_id}",
    response_model=SemanticReviewRead,
)
async def read_semantic_review(
    product_id: int,
    review_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SemanticReview:
    """读取一条必须属于路径商品的审核。"""
    return await get_semantic_review(session, product_id, review_id)
