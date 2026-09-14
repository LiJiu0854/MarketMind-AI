"""商品 Listing 确定性规则测试。"""

from decimal import Decimal

import pytest

from app.models.product import Product
from app.services.listing_rules import check_listing


def valid_product(**changes: object) -> Product:
    values: dict[str, object] = {
        "sku": "SKU-1",
        "title": "A valid product title",
        "description": "A" * 50,
        "bullet_points": ["A" * 10, "B" * 10, "C" * 10],
        "brand": "Brand",
        "category": "Category",
        "price": Decimal("19.90"),
        "currency": "CNY",
        "is_active": True,
        "created_by_id": 1,
    }
    values.update(changes)
    return Product(**values)


def test_valid_listing_has_no_issues() -> None:
    assert check_listing(valid_product()) == []


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"title": "short"}, "TITLE_TOO_SHORT"),
        ({"description": ""}, "DESCRIPTION_MISSING"),
        ({"description": "short"}, "DESCRIPTION_TOO_SHORT"),
        ({"description": "x" * 5001}, "DESCRIPTION_TOO_LONG"),
        ({"bullet_points": []}, "BULLET_COUNT_INVALID"),
        (
            {"bullet_points": ["short", "B" * 10, "C" * 10]},
            "BULLET_TOO_SHORT",
        ),
        (
            {"bullet_points": ["A" * 201, "B" * 10, "C" * 10]},
            "BULLET_TOO_LONG",
        ),
        ({"price": Decimal("0")}, "PRICE_INVALID"),
        ({"currency": "cny"}, "CURRENCY_INVALID"),
    ],
)
def test_listing_rule_returns_stable_code(
    changes: dict[str, object],
    code: str,
) -> None:
    assert code in {issue.code for issue in check_listing(valid_product(**changes))}


def test_missing_description_does_not_also_report_too_short() -> None:
    codes = [issue.code for issue in check_listing(valid_product(description=""))]
    assert codes.count("DESCRIPTION_MISSING") == 1
    assert "DESCRIPTION_TOO_SHORT" not in codes


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"title": "A valid 最便宜 product"}, "title"),
        ({"description": "A" * 50 + "永久有效"}, "description"),
        (
            {"bullet_points": ["A" * 10, "绝对有效 product", "C" * 10]},
            "bullet_points",
        ),
        ({"title": "A valid 100%保证 product"}, "title"),
    ],
)
def test_forbidden_terms_cover_all_text_fields(
    changes: dict[str, object],
    field: str,
) -> None:
    forbidden = [
        issue
        for issue in check_listing(valid_product(**changes))
        if issue.code == "FORBIDDEN_TERM"
    ]
    assert forbidden
    assert forbidden[0].field == field


def test_listing_issue_has_explanation_and_suggestion() -> None:
    issue = check_listing(valid_product(title="short"))[0]
    assert issue.field == "title"
    assert issue.message
    assert issue.suggestion
