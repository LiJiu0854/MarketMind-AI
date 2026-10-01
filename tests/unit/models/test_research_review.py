"""研究报告审核记录的数据库契约。"""

from typing import cast

from sqlalchemy import CheckConstraint, Table, UniqueConstraint

from app.models.research_review import ResearchReportReview, ResearchReviewDecision


def test_review_is_unique_per_run() -> None:
    table = cast(Table, ResearchReportReview.__table__)

    assert table.name == "research_report_reviews"
    assert {item.value for item in ResearchReviewDecision} == {"approved", "rejected"}
    assert {column.name for column in table.columns} == {
        "id",
        "run_id",
        "reviewed_by_id",
        "decision",
        "comment",
        "reviewed_at",
    }
    assert not table.c.run_id.nullable
    assert not table.c.reviewed_by_id.nullable
    assert table.c.run_id.foreign_keys
    assert table.c.reviewed_by_id.foreign_keys
    assert table.c.run_id.unique or any(
        isinstance(item, UniqueConstraint)
        and [column.name for column in item.columns] == ["run_id"]
        for item in table.constraints
    )
    assert any(isinstance(item, CheckConstraint) for item in table.constraints)
