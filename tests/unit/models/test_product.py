"""Product ORM 元数据测试。"""

from typing import cast

from sqlalchemy import JSON, CheckConstraint, Numeric, String, Table

from app.models.product import Product


def test_product_uses_expected_table_and_columns() -> None:
    assert Product.__tablename__ == "products"
    assert {column.name for column in Product.__table__.columns} == {
        "id",
        "sku",
        "title",
        "description",
        "bullet_points",
        "brand",
        "category",
        "price",
        "currency",
        "is_active",
        "created_by_id",
        "created_at",
        "updated_at",
    }


def test_product_sku_and_created_by_are_indexed() -> None:
    table = cast(Table, Product.__table__)
    sku = table.columns["sku"]
    created_by = table.columns["created_by_id"]

    assert isinstance(sku.type, String)
    assert sku.type.length == 50
    assert sku.unique is True
    assert sku.index is True
    assert created_by.index is True
    assert {key.target_fullname for key in created_by.foreign_keys} == {"users.id"}


def test_product_uses_safe_price_and_bullet_types() -> None:
    price = Product.__table__.columns["price"]

    assert isinstance(price.type, Numeric)
    assert (price.type.precision, price.type.scale) == (12, 2)
    assert isinstance(Product.__table__.columns["bullet_points"].type, JSON)


def test_product_requires_positive_price() -> None:
    table = cast(Table, Product.__table__)
    checks = {
        str(constraint.sqltext).strip()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "price > 0" in checks
