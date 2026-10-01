"""研究报告的一次性人工审核与历史状态。"""

from typing import cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.research import ResearchRun, ResearchStatus
from app.models.research_review import ResearchReportReview, ResearchReviewDecision
from app.schemas.research import ResearchReport
from app.schemas.research_review import ResearchReviewCreate, ResearchReviewStatus


def _is_reviewable(run: ResearchRun) -> bool:
    if run.status is not ResearchStatus.SUCCESS or run.report is None:
        return False
    try:
        report = ResearchReport.model_validate(run.report, strict=True)
    except ValidationError:
        return False
    return report.outcome == "supported"


def _same_decision(
    existing: ResearchReportReview, reviewer_id: int, payload: ResearchReviewCreate
) -> bool:
    return (
        existing.reviewed_by_id == reviewer_id
        and existing.decision is payload.decision
        and existing.comment == payload.comment
    )


async def review_research_report(
    session: AsyncSession,
    product_id: int,
    run_id: int,
    reviewer_id: int,
    payload: ResearchReviewCreate,
) -> ResearchReportReview:
    """锁定研究行，数据库唯一键保证并发中只有一个终局决定。"""
    try:
        run = await session.scalar(
            select(ResearchRun)
            .where(ResearchRun.id == run_id, ResearchRun.product_id == product_id)
            .with_for_update()
        )
        if run is None:
            raise AppError("RESEARCH_NOT_FOUND", "研究记录不存在", 404)
        existing = await get_research_review(session, run_id)
        if existing is not None:
            if _same_decision(existing, reviewer_id, payload):
                await session.commit()
                return existing
            raise AppError("RESEARCH_ALREADY_REVIEWED", "研究报告已有最终审核", 409)
        if not _is_reviewable(run):
            raise AppError("RESEARCH_NOT_REVIEWABLE", "研究报告不符合审核条件", 409)
        review = ResearchReportReview(
            run_id=run_id,
            reviewed_by_id=reviewer_id,
            decision=payload.decision,
            comment=payload.comment,
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
        return review
    except IntegrityError:
        await session.rollback()
        existing = await get_research_review(session, run_id)
        if existing is not None and _same_decision(existing, reviewer_id, payload):
            return existing
        raise AppError("RESEARCH_ALREADY_REVIEWED", "研究报告已有最终审核", 409) from None
    except Exception:
        await session.rollback()
        raise


async def get_research_review(session: AsyncSession, run_id: int) -> ResearchReportReview | None:
    return cast(
        ResearchReportReview | None,
        await session.scalar(
            select(ResearchReportReview).where(ResearchReportReview.run_id == run_id)
        ),
    )


async def list_research_reviews(
    session: AsyncSession, run_ids: list[int]
) -> dict[int, ResearchReportReview]:
    if not run_ids:
        return {}
    reviews = await session.scalars(
        select(ResearchReportReview).where(ResearchReportReview.run_id.in_(run_ids))
    )
    return {review.run_id: review for review in reviews}


def research_review_status(
    run: ResearchRun, review: ResearchReportReview | None
) -> ResearchReviewStatus:
    if review is not None:
        return (
            ResearchReviewStatus.APPROVED
            if review.decision is ResearchReviewDecision.APPROVED
            else ResearchReviewStatus.REJECTED
        )
    if run.status in (ResearchStatus.PENDING, ResearchStatus.RUNNING):
        return ResearchReviewStatus.NOT_READY
    if not _is_reviewable(run):
        return ResearchReviewStatus.NOT_REVIEWABLE
    return ResearchReviewStatus.PENDING_REVIEW
