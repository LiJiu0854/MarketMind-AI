"""create listing semantic reviews table"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建商品语义审核历史表。"""
    op.create_table(
        "listing_semantic_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failure",
                name="semantic_review_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("product_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("dimension_scores", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column("rewrite", sa.JSON(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_listing_semantic_reviews_score_range",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_listing_semantic_reviews_celery_task_id",
        "listing_semantic_reviews",
        ["celery_task_id"],
        unique=True,
    )
    op.create_index(
        "ix_listing_semantic_reviews_product_id",
        "listing_semantic_reviews",
        ["product_id"],
    )
    op.create_index(
        "ix_listing_semantic_reviews_requested_by_id",
        "listing_semantic_reviews",
        ["requested_by_id"],
    )
    op.create_index(
        "ix_listing_semantic_reviews_status",
        "listing_semantic_reviews",
        ["status"],
    )


def downgrade() -> None:
    """删除商品语义审核历史表。"""
    op.drop_table("listing_semantic_reviews")
