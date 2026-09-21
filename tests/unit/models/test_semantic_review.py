from typing import cast

from sqlalchemy import JSON, CheckConstraint, Table

from app.models.semantic_review import SemanticReview, SemanticReviewStatus


def test_semantic_review_model_contract() -> None:
    table = cast(Table, SemanticReview.__table__)
    assert SemanticReview.__tablename__ == "listing_semantic_reviews"
    assert [status.value for status in SemanticReviewStatus] == [
        "pending",
        "running",
        "success",
        "failure",
    ]
    assert SemanticReview.product_id.property.columns[0].foreign_keys
    assert SemanticReview.requested_by_id.property.columns[0].foreign_keys
    assert SemanticReview.celery_task_id.property.columns[0].unique is True
    assert isinstance(SemanticReview.product_snapshot.property.columns[0].type, JSON)
    assert SemanticReview.status.property.columns[0].default.arg is SemanticReviewStatus.PENDING
    assert any(
        isinstance(item, CheckConstraint)
        and item.name == "ck_listing_semantic_reviews_score_range"
        for item in table.constraints
    )
