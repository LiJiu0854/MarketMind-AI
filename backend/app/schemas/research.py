"""研究请求与历史响应的类型边界。"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.research import ResearchStatus

PositiveBaseID = Annotated[int, Field(gt=0, strict=True)]
EvidenceGap = Annotated[str, Field(min_length=1, max_length=500)]


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


class ResearchEvidence(BaseModel):
    """程序验证并登记的来源，不接受模型生成的坐标。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=150)
    source_type: Literal["product", "knowledge"]
    text: str = Field(min_length=1, max_length=1000)
    product_id: int | None = Field(default=None, gt=0)
    knowledge_base_id: int | None = Field(default=None, gt=0)
    document_id: int | None = Field(default=None, gt=0)
    chunk_id: str | None = None
    chunk_index: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    original_name: str | None = None
    distance: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)

    @field_validator("text", mode="before")
    @classmethod
    def truncate_text(cls, value: object) -> object:
        return value[:1000] if isinstance(value, str) else value

    @model_validator(mode="after")
    def verify_coordinates(self) -> Self:
        if self.source_type == "product":
            if (
                self.product_id is None
                or self.source_id != f"product:{self.product_id}:snapshot"
                or any(
                    value is not None
                    for value in (
                        self.knowledge_base_id,
                        self.document_id,
                        self.chunk_id,
                        self.chunk_index,
                        self.original_name,
                        self.distance,
                    )
                )
            ):
                raise ValueError("商品来源坐标无效")
        elif (
            self.product_id is not None
            or self.knowledge_base_id is None
            or self.document_id is None
            or self.chunk_index is None
            or self.chunk_id != f"document:{self.document_id}:chunk:{self.chunk_index}"
            or self.source_id
            != f"kb:{self.knowledge_base_id}:document:{self.document_id}:chunk:{self.chunk_index}"
            or not self.original_name
            or self.distance is None
        ):
            raise ValueError("知识库来源坐标无效")
        return self


class ToolResult(BaseModel):
    evidence: list[ResearchEvidence]
    embedding_tokens: int | None = Field(default=0, ge=0)


class ResearchAction(BaseModel):
    """模型唯一允许提出的三种动作。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["read_product", "search_knowledge", "finish"]
    knowledge_base_id: int | None = Field(default=None, gt=0, strict=True)
    query: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("检索词不能为空")
        return value

    @model_validator(mode="after")
    def verify_shape(self) -> Self:
        if self.action == "search_knowledge":
            if self.knowledge_base_id is None or self.query is None:
                raise ValueError("知识库检索需要 ID 与查询词")
        elif self.knowledge_base_id is not None or self.query is not None:
            raise ValueError("此动作不能携带知识库参数")
        return self


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=5)


class ResearchRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=5)


class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["supported", "insufficient_evidence"]
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[ResearchFinding] = Field(max_length=10)
    recommendations: list[ResearchRecommendation] = Field(max_length=5)
    evidence_gaps: list[EvidenceGap] = Field(max_length=5)

    @model_validator(mode="after")
    def verify_outcome(self) -> Self:
        if self.outcome == "supported" and not self.findings:
            raise ValueError("有证据报告至少需要一条发现")
        if self.outcome == "insufficient_evidence" and (self.findings or self.recommendations):
            raise ValueError("证据不足报告不能包含发现或建议")
        return self
