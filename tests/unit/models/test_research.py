"""研究任务的数据库约束契约。"""

from typing import cast

from sqlalchemy import CheckConstraint, Table

from app.models.research import ResearchRun, ResearchStatus


def test_research_run_has_auditable_fields_and_constraints() -> None:
    table = cast(Table, ResearchRun.__table__)

    assert table.name == "research_runs"
    assert {item.value for item in ResearchStatus} == {
        "pending",
        "running",
        "success",
        "failure",
    }
    assert {column.name for column in table.columns} >= {
        "product_id",
        "requested_by_id",
        "goal",
        "knowledge_base_ids",
        "product_snapshot",
        "status",
        "celery_task_id",
        "provider",
        "model",
        "prompt_version",
        "steps",
        "evidence",
        "report",
        "prompt_tokens",
        "completion_tokens",
        "embedding_tokens",
        "total_tokens",
        "attempt_count",
        "error_code",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    }
    assert ResearchRun.product_id.property.columns[0].foreign_keys
    assert ResearchRun.requested_by_id.property.columns[0].foreign_keys
    assert any(index.name == "ix_research_runs_product_status" for index in table.indexes)
    assert {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    } >= {
        "ck_research_runs_attempt_count_non_negative",
        "ck_research_runs_token_counts_non_negative",
    }
