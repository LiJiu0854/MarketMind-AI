"""LLM 语义审核输出结构测试。"""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.semantic_review import LLMReviewResult


def valid_result_data() -> dict[str, object]:
    return {
        "score": 88,
        "dimension_scores": {
            "completeness": 90,
            "consistency": 85,
            "clarity": 87,
            "risk": 92,
            "persuasion": 86,
        },
        "summary": "商品信息完整，表达清晰。",
        "issues": [
            {
                "dimension": "clarity",
                "severity": "medium",
                "field": "description",
                "message": "描述可以更具体。",
                "suggestion": "补充可验证的使用场景。",
            }
        ],
        "rewrite": {
            "title": "清晰具体的商品标题",
            "description": "面向真实使用场景的商品描述。",
            "bullet_points": [
                "清楚说明商品的核心使用价值",
                "使用可验证的信息减少理解成本",
                "避免夸张承诺并保持表达一致",
            ],
        },
    }


def test_llm_review_result_accepts_complete_valid_payload() -> None:
    result = LLMReviewResult.model_validate(valid_result_data())

    assert result.score == 88
    assert result.dimension_scores.risk == 92
    assert result.issues[0].field == "description"
    assert len(result.rewrite.bullet_points) == 3


@pytest.mark.parametrize("score", [-1, 101])
def test_total_score_must_stay_between_zero_and_one_hundred(score: int) -> None:
    data = valid_result_data()
    data["score"] = score

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


@pytest.mark.parametrize("score", [-1, 101])
def test_every_dimension_score_has_the_same_range(score: int) -> None:
    data = valid_result_data()
    dimension_scores = deepcopy(data["dimension_scores"])
    assert isinstance(dimension_scores, dict)
    dimension_scores["clarity"] = score
    data["dimension_scores"] = dimension_scores

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimension", "seo"),
        ("severity", "critical"),
        ("field", "price"),
    ],
)
def test_issue_classifications_are_fixed_enums(field: str, value: str) -> None:
    data = valid_result_data()
    issues = deepcopy(data["issues"])
    assert isinstance(issues, list)
    assert isinstance(issues[0], dict)
    issues[0][field] = value
    data["issues"] = issues

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


def test_issue_count_is_limited_to_twenty() -> None:
    data = valid_result_data()
    issues = deepcopy(data["issues"])
    assert isinstance(issues, list)
    data["issues"] = issues * 21

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


@pytest.mark.parametrize("count", [2, 6])
def test_rewrite_requires_three_to_five_bullet_points(count: int) -> None:
    data = valid_result_data()
    rewrite = deepcopy(data["rewrite"])
    assert isinstance(rewrite, dict)
    rewrite["bullet_points"] = ["至少十个字符的有效卖点文本"] * count
    data["rewrite"] = rewrite

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


@pytest.mark.parametrize("bullet", ["123456789", "x" * 201])
def test_each_rewrite_bullet_has_a_ten_to_two_hundred_character_limit(
    bullet: str,
) -> None:
    data = valid_result_data()
    rewrite = deepcopy(data["rewrite"])
    assert isinstance(rewrite, dict)
    rewrite["bullet_points"] = [bullet, "至少十个字符的有效卖点文本", "另一个超过十字的有效卖点"]
    data["rewrite"] = rewrite

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("summary", "x" * 1_001),
        ("message", "x" * 501),
        ("suggestion", "x" * 1_001),
        ("title", "x" * 201),
        ("description", "x" * 5_001),
    ],
)
def test_model_text_fields_have_explicit_size_limits(path: str, value: str) -> None:
    data = valid_result_data()
    if path == "summary":
        data[path] = value
    elif path in {"message", "suggestion"}:
        issues = deepcopy(data["issues"])
        assert isinstance(issues, list)
        assert isinstance(issues[0], dict)
        issues[0][path] = value
        data["issues"] = issues
    else:
        rewrite = deepcopy(data["rewrite"])
        assert isinstance(rewrite, dict)
        rewrite[path] = value
        data["rewrite"] = rewrite

    with pytest.raises(ValidationError):
        LLMReviewResult.model_validate(data)
