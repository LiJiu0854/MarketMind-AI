"""商品 Listing 语义审核 ORM Model。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SemanticReviewStatus(StrEnum):
    """语义审核生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


def _status_values(status_type: type[SemanticReviewStatus]) -> list[str]:
    return [status.value for status in status_type]


class SemanticReview(Base):
    """一次基于固定商品快照的语义审核。"""

    __tablename__ = "listing_semantic_reviews"
    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_listing_semantic_reviews_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[SemanticReviewStatus] = mapped_column(
        Enum(
            SemanticReviewStatus,
            name="semantic_review_status",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=_status_values,
        ),
        default=SemanticReviewStatus.PENDING,
        index=True,
    )
    product_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    score: Mapped[int | None] = mapped_column(Integer)
    dimension_scores: Mapped[dict[str, int] | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    rewrite: Mapped[dict[str, object] | None] = mapped_column(JSON)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
