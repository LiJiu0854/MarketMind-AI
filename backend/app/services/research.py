"""研究记录的短事务与商品范围边界。"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentStatus
from app.models.product import Product
from app.models.research import ResearchRun, ResearchStatus
from app.schemas.research import ResearchCreate, ResearchEvidence
from app.services.semantic_reviews import build_product_snapshot

PROMPT_VERSION = "research-v1"
ACTIVE_STATUSES = (ResearchStatus.PENDING, ResearchStatus.RUNNING)


@dataclass(frozen=True)
class ResearchUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    embedding_tokens: int | None


def _add_usage(previous: int | None, current: int | None) -> int | None:
    return None if previous is None or current is None else previous + current


async def create_research_run(
    session: AsyncSession,
    product_id: int,
    actor_id: int,
    payload: ResearchCreate,
    settings: Settings,
) -> ResearchRun:
    """商品行锁串行化同商品创建，并保存不可变快照。"""
    if (
        not settings.llm_model
        or settings.llm_api_key is None
        or not settings.embedding_model
        or settings.embedding_api_key is None
    ):
        raise AppError("RESEARCH_CONFIG_MISSING", "研究模型或 Embedding 配置缺失", 503)
    try:
        product = await session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            raise AppError("PRODUCT_NOT_FOUND", "商品不存在", 404)
        active = await session.scalar(
            select(ResearchRun.id).where(
                ResearchRun.product_id == product_id,
                ResearchRun.status.in_(ACTIVE_STATUSES),
            )
        )
        if active is not None:
            raise AppError("RESEARCH_ALREADY_ACTIVE", "商品已有进行中的研究", 409)
        bases = list(
            await session.scalars(
                select(KnowledgeBase).where(KnowledgeBase.id.in_(payload.knowledge_base_ids))
            )
        )
        if len(bases) != len(payload.knowledge_base_ids):
            raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", 404)
        for base in bases:
            if (
                base.embedding_provider != settings.embedding_provider
                or base.embedding_base_url != settings.embedding_base_url
                or base.embedding_model != settings.embedding_model
            ):
                raise AppError(
                    "RESEARCH_EMBEDDING_CONFIG_MISMATCH", "知识库 Embedding 配置不一致", 503
                )
            ready_id = await session.scalar(
                select(KnowledgeDocument.id)
                .where(
                    KnowledgeDocument.knowledge_base_id == base.id,
                    KnowledgeDocument.status == KnowledgeDocumentStatus.READY,
                )
                .limit(1)
            )
            if ready_id is None:
                raise AppError("RESEARCH_KNOWLEDGE_NOT_READY", "知识库没有已就绪文档", 409)
        run = ResearchRun(
            product_id=product_id,
            requested_by_id=actor_id,
            goal=payload.goal,
            knowledge_base_ids=list(payload.knowledge_base_ids),
            product_snapshot=build_product_snapshot(product).model_dump(mode="json"),
            status=ResearchStatus.PENDING,
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_version=PROMPT_VERSION,
            steps=[],
            evidence=[],
            prompt_tokens=0,
            completion_tokens=0,
            embedding_tokens=0,
            total_tokens=0,
            attempt_count=0,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run
    except Exception:
        await session.rollback()
        raise


async def get_research_run(session: AsyncSession, product_id: int, run_id: int) -> ResearchRun:
    run = await session.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id,
            ResearchRun.product_id == product_id,
        )
    )
    if run is None:
        raise AppError("RESEARCH_NOT_FOUND", "研究记录不存在", 404)
    return run


async def list_research_runs(
    session: AsyncSession, product_id: int, page: int, page_size: int
) -> tuple[list[ResearchRun], int]:
    if await session.get(Product, product_id) is None:
        raise AppError("PRODUCT_NOT_FOUND", "商品不存在", 404)
    total = (
        await session.scalar(
            select(func.count())
            .select_from(ResearchRun)
            .where(ResearchRun.product_id == product_id)
        )
        or 0
    )
    items = list(
        await session.scalars(
            select(ResearchRun)
            .where(ResearchRun.product_id == product_id)
            .order_by(ResearchRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


async def set_research_task_id(session: AsyncSession, run_id: int, task_id: str) -> ResearchRun:
    try:
        run = await session.get(ResearchRun, run_id)
        if run is None:
            raise AppError("RESEARCH_NOT_FOUND", "研究记录不存在", 404)
        if run.status is ResearchStatus.PENDING:
            run.celery_task_id = task_id
            await session.commit()
            await session.refresh(run)
        return run
    except Exception:
        await session.rollback()
        raise


async def mark_research_failure(
    session: AsyncSession, run_id: int, code: str, message: str
) -> ResearchRun | None:
    try:
        run = await session.scalar(
            select(ResearchRun).where(ResearchRun.id == run_id).with_for_update()
        )
        if run is None or run.status not in ACTIVE_STATUSES:
            return None
        run.status = ResearchStatus.FAILURE
        run.error_code = code
        run.error_message = message
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
        return run
    except Exception:
        await session.rollback()
        raise


async def mark_research_running(session: AsyncSession, run_id: int) -> ResearchRun | None:
    """终态任务不重启；每次真实尝试独立计数。"""
    try:
        run = await session.scalar(
            select(ResearchRun).where(ResearchRun.id == run_id).with_for_update()
        )
        if run is None or run.status not in ACTIVE_STATUSES:
            return None
        run.status = ResearchStatus.RUNNING
        run.started_at = run.started_at or datetime.now(UTC)
        run.attempt_count += 1
        await session.commit()
        await session.refresh(run)
        return run
    except Exception:
        await session.rollback()
        raise


async def append_research_step(
    session: AsyncSession,
    run_id: int,
    step: dict[str, object],
    evidence: list[ResearchEvidence],
    usage: ResearchUsage,
) -> ResearchRun | None:
    """每个已验证动作单独提交，供重投从下一步继续。"""
    try:
        run = await session.scalar(
            select(ResearchRun).where(ResearchRun.id == run_id).with_for_update()
        )
        if run is None or run.status is not ResearchStatus.RUNNING:
            return None
        run.steps = [*run.steps, step]
        run.evidence = [item.model_dump(mode="json") for item in evidence]
        run.prompt_tokens = _add_usage(run.prompt_tokens, usage.prompt_tokens)
        run.completion_tokens = _add_usage(run.completion_tokens, usage.completion_tokens)
        run.embedding_tokens = _add_usage(run.embedding_tokens, usage.embedding_tokens)
        if (
            run.prompt_tokens is not None
            and run.completion_tokens is not None
            and run.embedding_tokens is not None
        ):
            run.total_tokens = run.prompt_tokens + run.completion_tokens + run.embedding_tokens
        else:
            run.total_tokens = None
        await session.commit()
        await session.refresh(run)
        return run
    except Exception:
        await session.rollback()
        raise
