"""Real MySQL checks for the immutable review transaction."""

import asyncio

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.product import Product
from app.models.research import ResearchRun, ResearchStatus
from app.models.research_review import ResearchReportReview, ResearchReviewDecision
from app.models.user import Role, User
from app.schemas.research import ResearchCreate
from app.schemas.research_review import ResearchReviewCreate
from app.services.research import create_research_run
from app.services.research_review import review_research_report
from tests.api.test_research import configured_settings
from tests.integration.db.test_research import setup_rows


def supported_report(product_id: int = 1) -> dict[str, object]:
    return {
        "outcome": "supported",
        "summary": "依据已登记来源",
        "findings": [{"claim": "可验证发现", "source_ids": [f"product:{product_id}:snapshot"]}],
        "recommendations": [],
        "evidence_gaps": [],
    }


async def prepared_run(session: AsyncSession, suffix: str) -> tuple[int, int, int]:
    actor_id, product_id, base_id = await setup_rows(session, suffix)
    run = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(goal="比较", knowledge_base_ids=[base_id]),
        configured_settings(),
    )
    run.status = ResearchStatus.SUCCESS
    run.report = supported_report(product_id)
    run.evidence = [
        {
            "source_id": f"product:{product_id}:snapshot",
            "source_type": "product",
            "product_id": product_id,
            "text": "商品快照",
        }
    ]
    await session.commit()
    return actor_id, product_id, run.id


@pytest.mark.asyncio
async def test_only_supported_report_is_reviewable(session: AsyncSession) -> None:
    actor_id, product_id, run_id = await prepared_run(session, "review-eligibility")
    run = await session.get_one(ResearchRun, run_id)
    payload = ResearchReviewCreate(decision=ResearchReviewDecision.APPROVED)
    cases: list[tuple[ResearchStatus, dict[str, object]]] = [
        (ResearchStatus.PENDING, supported_report()),
        (ResearchStatus.FAILURE, supported_report()),
        (
            ResearchStatus.SUCCESS,
            {
                "outcome": "insufficient_evidence",
                "summary": "不足",
                "findings": [],
                "recommendations": [],
                "evidence_gaps": ["缺资料"],
            },
        ),
        (ResearchStatus.SUCCESS, {"outcome": "supported", "findings": "broken"}),
    ]
    for status, report in cases:
        run.status = status
        run.report = report
        await session.commit()
        with pytest.raises(AppError) as failure:
            await review_research_report(session, product_id, run_id, actor_id, payload)
        assert failure.value.status_code == 409
    count = await session.scalar(
        select(func.count())
        .select_from(ResearchReportReview)
        .where(ResearchReportReview.run_id == run_id)
    )
    assert count == 0


@pytest.mark.asyncio
async def test_same_review_retry_is_idempotent(session: AsyncSession) -> None:
    actor_id, product_id, run_id = await prepared_run(session, "review-idempotence")
    first = await review_research_report(
        session,
        product_id,
        run_id,
        actor_id,
        ResearchReviewCreate(decision=ResearchReviewDecision.REJECTED, comment=" 需补证 "),
    )
    retry = await review_research_report(
        session,
        product_id,
        run_id,
        actor_id,
        ResearchReviewCreate(decision=ResearchReviewDecision.REJECTED, comment="需补证"),
    )
    assert retry.id == first.id
    assert retry.comment == "需补证"
    other_id, _, _ = await setup_rows(session, "review-other-admin")
    for reviewer_id, comment in ((actor_id, "其他意见"), (other_id, "需补证")):
        with pytest.raises(AppError) as failure:
            await review_research_report(
                session,
                product_id,
                run_id,
                reviewer_id,
                ResearchReviewCreate(decision=ResearchReviewDecision.REJECTED, comment=comment),
            )
        assert failure.value.status_code == 409
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ResearchReportReview)
            .where(ResearchReportReview.run_id == run_id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_competing_admin_reviews_have_one_winner(test_engine: AsyncEngine) -> None:
    """Unlike the rollback fixture, committed setup is visible to two connections."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as setup:
        actor_id, product_id, run_id = await prepared_run(setup, "review-race")
        base_id = await setup.scalar(
            select(KnowledgeBase.id).where(KnowledgeBase.name == "Research base review-race")
        )
        assert base_id is not None
        other = User(
            email="review-race-other@example.com",
            full_name="Other",
            password_hash="x",
            role=Role.ADMIN,
            is_active=True,
        )
        setup.add(other)
        await setup.commit()
        other_id = other.id

    async def submit(reviewer_id: int, decision: ResearchReviewDecision) -> int:
        async with sessions() as independent:
            try:
                await review_research_report(
                    independent,
                    product_id,
                    run_id,
                    reviewer_id,
                    ResearchReviewCreate(
                        decision=decision,
                        comment="需补证" if decision is ResearchReviewDecision.REJECTED else None,
                    ),
                )
                return 200
            except AppError as error:
                return error.status_code

    try:
        statuses = await asyncio.gather(
            submit(actor_id, ResearchReviewDecision.APPROVED),
            submit(other_id, ResearchReviewDecision.REJECTED),
        )
        assert sorted(statuses) == [200, 409]
        async with sessions() as verify:
            assert (
                await verify.scalar(
                    select(func.count())
                    .select_from(ResearchReportReview)
                    .where(ResearchReportReview.run_id == run_id)
                )
                == 1
            )
    finally:
        async with sessions() as cleanup:
            await cleanup.execute(
                delete(ResearchReportReview).where(ResearchReportReview.run_id == run_id)
            )
            await cleanup.execute(delete(ResearchRun).where(ResearchRun.id == run_id))
            await cleanup.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base_id)
            )
            await cleanup.execute(delete(KnowledgeBase).where(KnowledgeBase.id == base_id))
            await cleanup.execute(delete(Product).where(Product.id == product_id))
            await cleanup.execute(delete(User).where(User.id.in_([actor_id, other_id])))
            await cleanup.commit()
