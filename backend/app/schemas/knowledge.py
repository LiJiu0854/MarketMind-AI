"""Validated API and provider data for the RAG knowledge base."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.knowledge import KnowledgeDocumentStatus, KnowledgeQueryStatus


class KnowledgeBaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name", "description")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_by_id: int
    embedding_provider: str
    embedding_base_url: str
    embedding_model: str
    embedding_dimensions: int | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    uploaded_by_id: int
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str
    status: KnowledgeDocumentStatus
    celery_task_id: str | None
    chunk_count: int
    embedding_tokens: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class KnowledgeDocumentCreated(BaseModel):
    document_id: int
    task_id: str
    status: KnowledgeDocumentStatus


class KnowledgeQuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int
    original_name: str
    chunk_id: str
    chunk_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1)
    distance: float = Field(ge=0, le=2)


class RAGModelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=5_000)
    cited_chunk_numbers: list[int] = Field(max_length=10)
    refused: bool

    @field_validator("answer")
    @classmethod
    def trim_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be blank")
        return value


class KnowledgeCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int
    original_name: str
    chunk_id: str
    chunk_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    excerpt: str = Field(min_length=1, max_length=300)
    distance: float = Field(ge=0, le=2)


class KnowledgeAnswerRead(BaseModel):
    query_id: int
    status: KnowledgeQueryStatus
    answer: str
    citations: list[KnowledgeCitation] = Field(max_length=10)
    embedding_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


class KnowledgeQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    asked_by_id: int
    question: str
    status: KnowledgeQueryStatus
    answer: str | None
    citations: list[KnowledgeCitation]
    provider: str
    model: str
    prompt_version: str
    embedding_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime


class KnowledgeQueryPage(BaseModel):
    items: list[KnowledgeQueryRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
