"""报告审核输入、输出及派生状态。"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.research_review import ResearchReviewDecision


class ResearchReviewStatus(StrEnum):
    NOT_READY = "not_ready"
    NOT_REVIEWABLE = "not_reviewable"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResearchReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ResearchReviewDecision
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def require_rejection_comment(self) -> Self:
        if self.decision is ResearchReviewDecision.REJECTED and self.comment is None:
            raise ValueError("驳回时必须填写意见")
        return self


class ResearchReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    reviewed_by_id: int
    decision: ResearchReviewDecision
    comment: str | None
    reviewed_at: datetime
