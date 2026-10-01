"""研究报告的一次性人工审核记录。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ResearchReportReview(Base):
    __tablename__ = "research_report_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id"), unique=True)
    reviewed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[ResearchReviewDecision] = mapped_column(
        Enum(
            ResearchReviewDecision,
            name="research_review_decision",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        )
    )
    comment: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
