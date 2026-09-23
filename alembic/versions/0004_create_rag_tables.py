"""create RAG knowledge-base tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("embedding_provider", sa.String(50), nullable=False),
        sa.Column("embedding_base_url", sa.String(500), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="ck_knowledge_bases_embedding_dimensions_positive",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_knowledge_bases_created_by_id", "knowledge_bases", ["created_by_id"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "ready",
                "failure",
                name="knowledge_document_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_knowledge_documents_size_positive"),
        sa.CheckConstraint(
            "chunk_count >= 0", name="ck_knowledge_documents_chunk_count_non_negative"
        ),
        sa.CheckConstraint(
            "embedding_tokens IS NULL OR embedding_tokens >= 0",
            name="ck_knowledge_documents_embedding_tokens_non_negative",
        ),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_base_id", "sha256", name="uq_knowledge_documents_base_sha256"
        ),
    )
    for column in ("knowledge_base_id", "uploaded_by_id", "status"):
        op.create_index(f"ix_knowledge_documents_{column}", "knowledge_documents", [column])
    op.create_index(
        "ix_knowledge_documents_celery_task_id",
        "knowledge_documents",
        ["celery_task_id"],
        unique=True,
    )

    op.create_table(
        "knowledge_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("asked_by_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "success",
                "refused",
                "failure",
                name="knowledge_query_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("answer", sa.Text()),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("embedding_tokens", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(embedding_tokens IS NULL OR embedding_tokens >= 0) AND "
            "(prompt_tokens IS NULL OR prompt_tokens >= 0) AND "
            "(completion_tokens IS NULL OR completion_tokens >= 0) AND "
            "(total_tokens IS NULL OR total_tokens >= 0)",
            name="ck_knowledge_queries_token_counts_non_negative",
        ),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(["asked_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("knowledge_base_id", "asked_by_id", "status"):
        op.create_index(f"ix_knowledge_queries_{column}", "knowledge_queries", [column])


def downgrade() -> None:
    op.drop_table("knowledge_queries")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
