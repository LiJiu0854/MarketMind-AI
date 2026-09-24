"""研究请求的边界校验。"""

import pytest
from pydantic import ValidationError

from app.schemas.research import ResearchCreate


def test_research_goal_is_trimmed() -> None:
    payload = ResearchCreate(goal="  比较定位  ", knowledge_base_ids=[2])

    assert payload.goal == "比较定位"


@pytest.mark.parametrize("goal", ["", "  ", "x" * 501])
def test_research_goal_rejects_blank_or_oversized_text(goal: str) -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(goal=goal, knowledge_base_ids=[2])


@pytest.mark.parametrize("base_ids", [[], [0], [-1], [2, 2], [1, 2, 3, 4], [True]])
def test_research_rejects_invalid_knowledge_base_ids(base_ids: list[int]) -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(goal="比较定位", knowledge_base_ids=base_ids)


def test_research_rejects_unknown_request_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(goal="比较定位", knowledge_base_ids=[2], unsafe=True)  # type: ignore[call-arg]
