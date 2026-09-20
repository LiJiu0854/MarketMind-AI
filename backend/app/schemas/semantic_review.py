"""语义审核输入与输出结构。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.semantic_review import SemanticReviewStatus

ReviewDimension = Literal[
    "completeness",
    "consistency",
    "clarity",
    "risk",
    "persuasion",
]
ReviewSeverity = Literal["low", "medium", "high"]
ReviewField = Literal["title", "description", "bullet_points", "general"]


class ProductSnapshot(BaseModel):
    """发起审核时冻结的商品业务字段。"""

    model_config = ConfigDict(extra="forbid")

    sku: str
    title: str
    description: str
    bullet_points: list[str]
    brand: str
    category: str
    price: Decimal
    currency: str
    is_active: bool


class ReviewDimensionScores(BaseModel):
    """五个同方向的语义审核维度分数。"""

    model_config = ConfigDict(extra="forbid")

    completeness: int = Field(ge=0, le=100)
    consistency: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    risk: int = Field(ge=0, le=100)
    persuasion: int = Field(ge=0, le=100)


class SemanticReviewIssue(BaseModel):
    """模型发现的一条结构化问题。"""

    model_config = ConfigDict(extra="forbid")

    dimension: ReviewDimension
    severity: ReviewSeverity
    field: ReviewField
    message: str = Field(min_length=1, max_length=500)
    suggestion: str = Field(min_length=1, max_length=1_000)


class SemanticReviewRewrite(BaseModel):
    """模型建议的完整 Listing 改写。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=5_000)
    bullet_points: list[str] = Field(min_length=3, max_length=5)

    @field_validator("bullet_points")
    @classmethod
    def validate_bullet_lengths(cls, bullet_points: list[str]) -> list[str]:
        if any(not 10 <= len(bullet) <= 200 for bullet in bullet_points):
            raise ValueError("每条改写卖点必须为 10 到 200 个字符")
        return bullet_points


class LLMReviewResult(BaseModel):
    """通过本地校验后才允许持久化的模型审核结果。"""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    dimension_scores: ReviewDimensionScores
    summary: str = Field(min_length=1, max_length=1_000)
    issues: list[SemanticReviewIssue] = Field(max_length=20)
    rewrite: SemanticReviewRewrite


class SemanticReviewCreated(BaseModel):
    """审核成功投递后的 202 响应。"""

    review_id: int
    task_id: str
    status: SemanticReviewStatus


class SemanticReviewRead(BaseModel):
    """MySQL 中一条完整审核历史。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    requested_by_id: int
    celery_task_id: str | None
    status: SemanticReviewStatus
    product_snapshot: ProductSnapshot
    provider: str
    model: str
    prompt_version: str
    score: int | None
    dimension_scores: ReviewDimensionScores | None
    summary: str | None
    issues: list[SemanticReviewIssue] | None
    rewrite: SemanticReviewRewrite | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    attempt_count: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SemanticReviewPage(BaseModel):
    """语义审核历史分页响应。"""

    items: list[SemanticReviewRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
