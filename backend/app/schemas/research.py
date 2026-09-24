"""研究请求与历史响应的类型边界。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.research import ResearchStatus

PositiveBaseID = Annotated[int, Field(gt=0, strict=True)]


class ResearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=500)
    knowledge_base_ids: list[PositiveBaseID] = Field(min_length=1, max_length=3)

    @field_validator("goal")
    @classmethod
    def trim_goal(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("研究目标不能为空")
        return value

    @model_validator(mode="after")
    def reject_duplicate_bases(self) -> "ResearchCreate":
        if len(set(self.knowledge_base_ids)) != len(self.knowledge_base_ids):
            raise ValueError("知识库不能重复")
        return self


class ResearchCreated(BaseModel):
    run_id: int
    task_id: str
    status: ResearchStatus


class ResearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    requested_by_id: int
    goal: str
    knowledge_base_ids: list[int]
    product_snapshot: dict[str, object]
    status: ResearchStatus
    celery_task_id: str | None
    provider: str
    model: str
    prompt_version: str
    steps: list[dict[str, object]]
    evidence: list[dict[str, object]]
    report: dict[str, object] | None
    prompt_tokens: int | None
    completion_tokens: int | None
    embedding_tokens: int | None
    total_tokens: int | None
    attempt_count: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchPage(BaseModel):
    items: list[ResearchRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
