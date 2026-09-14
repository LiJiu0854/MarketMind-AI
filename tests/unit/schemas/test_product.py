"""Product Pydantic Schema 测试。"""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.product import (
    ProductCreate,
    ProductFilters,
    ProductPage,
    ProductRead,
    ProductUpdate,
)


def product_payload() -> dict[str, object]:
    return {
        "sku": " sku-001 ",
        "title": "Test Product",
        "description": "",
        "bullet_points": [],
        "brand": "Brand",
        "category": "Category",
        "price": "19.90",
        "currency": "cny",
        "is_active": True,
    }


def test_product_create_normalizes_business_fields() -> None:
    data = ProductCreate.model_validate(product_payload())

    assert data.sku == "SKU-001"
    assert data.price == Decimal("19.90")
    assert data.currency == "CNY"


@pytest.mark.parametrize("price", ["0", "-1", "1.001", "12345678901.00"])
def test_product_create_rejects_invalid_price(price: str) -> None:
    payload = product_payload()
    payload["price"] = price

    with pytest.raises(ValidationError):
        ProductCreate.model_validate(payload)


def test_product_create_rejects_audit_fields() -> None:
    payload = product_payload()
    payload["created_by_id"] = 99

    with pytest.raises(ValidationError):
        ProductCreate.model_validate(payload)


def test_product_update_only_contains_sent_fields_and_normalizes() -> None:
    data = ProductUpdate(sku=" next-1 ", currency="usd")

    assert data.model_dump(exclude_unset=True) == {
        "sku": "NEXT-1",
        "currency": "USD",
    }


def test_product_filters_normalize_sku() -> None:
    filters = ProductFilters(sku=" sku-001 ", is_active=False)

    assert filters.sku == "SKU-001"
    assert filters.is_active is False


def test_product_read_accepts_attributes() -> None:
    now = datetime.now(UTC)
    source = SimpleNamespace(
        id=1,
        created_by_id=2,
        created_at=now,
        updated_at=now,
        **ProductCreate.model_validate(product_payload()).model_dump(),
    )

    result = ProductRead.model_validate(source)

    assert result.id == 1
    assert result.created_by_id == 2


def test_product_page_rejects_zero_page_size() -> None:
    with pytest.raises(ValidationError):
        ProductPage(items=[], total=0, page=1, page_size=0)
