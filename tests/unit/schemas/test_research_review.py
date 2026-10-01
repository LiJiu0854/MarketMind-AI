"""研究审核请求不能携带未核准的决定或空驳回理由。"""

import pytest
from pydantic import ValidationError

from app.models.research_review import ResearchReviewDecision
from app.schemas.research_review import ResearchReviewCreate, ResearchReviewStatus


def test_rejection_requires_comment() -> None:
    payload = ResearchReviewCreate(
        decision=ResearchReviewDecision.REJECTED, comment=" 需补证 "
    )
    assert payload.comment == "需补证"

    for raw in ("", "   ", None):
        with pytest.raises(ValidationError):
            ResearchReviewCreate.model_validate({"decision": "rejected", "comment": raw})


def test_approval_may_omit_comment_and_rejects_untrusted_fields() -> None:
    approved = ResearchReviewCreate(decision=ResearchReviewDecision.APPROVED)
    assert approved.comment is None
    assert {item.value for item in ResearchReviewStatus} == {
        "not_ready",
        "not_reviewable",
        "pending_review",
        "approved",
        "rejected",
    }
    for data in (
        {"decision": "other"},
        {"decision": "approved", "comment": "x" * 501},
        {"decision": "approved", "reviewed_by_id": 7},
    ):
        with pytest.raises(ValidationError):
            ResearchReviewCreate.model_validate(data)
