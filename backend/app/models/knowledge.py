"""RAG knowledge-base persistence models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILURE = "failure"


class KnowledgeQueryStatus(StrEnum):
    SUCCESS = "success"
    REFUSED = "refused"
    FAILURE = "failure"


def _enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="ck_knowledge_bases_embedding_dimensions_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    embedding_provider: Mapped[str] = mapped_column(String(50))
    embedding_base_url: Mapped[str] = mapped_column(String(500))
    embedding_model: Mapped[str] = mapped_column(String(255))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "sha256",
            name="uq_knowledge_documents_base_sha256",
        ),
        CheckConstraint("size_bytes > 0", name="ck_knowledge_documents_size_positive"),
        CheckConstraint(
            "chunk_count >= 0",
            name="ck_knowledge_documents_chunk_count_non_negative",
        ),
        CheckConstraint(
            "embedding_tokens IS NULL OR embedding_tokens >= 0",
            name="ck_knowledge_documents_embedding_tokens_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        Enum(
            KnowledgeDocumentStatus,
            name="knowledge_document_status",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=_enum_values,
        ),
        default=KnowledgeDocumentStatus.PENDING,
        index=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeQuery(Base):
    __tablename__ = "knowledge_queries"
    __table_args__ = (
        CheckConstraint(
            "(embedding_tokens IS NULL OR embedding_tokens >= 0) AND "
            "(prompt_tokens IS NULL OR prompt_tokens >= 0) AND "
            "(completion_tokens IS NULL OR completion_tokens >= 0) AND "
            "(total_tokens IS NULL OR total_tokens >= 0)",
            name="ck_knowledge_queries_token_counts_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    asked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(String(2000))
    status: Mapped[KnowledgeQueryStatus] = mapped_column(
        Enum(
            KnowledgeQueryStatus,
            name="knowledge_query_status",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=_enum_values,
        ),
        index=True,
    )
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    embedding_tokens: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
