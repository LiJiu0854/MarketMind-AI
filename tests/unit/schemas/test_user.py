"""用户输入 Schema 测试。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.user import Role, User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate


def test_user_create_accepts_valid_input_without_exposing_password() -> None:
    """合法创建数据应通过，调试输出不得包含明文密码。"""
    password = "correct-horse-battery-staple"

    data = UserCreate(
        email="admin@example.com",
        full_name="MarketMind Admin",
        password=password,
        role=Role.ADMIN,
    )

    assert str(data.email) == "admin@example.com"
    assert data.full_name == "MarketMind Admin"
    assert data.role is Role.ADMIN
    assert password not in repr(data)


def test_user_create_rejects_invalid_email() -> None:
    """非法邮箱不能进入后续 Service。"""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="not-an-email",
            full_name="MarketMind Admin",
            password="correct-horse-battery-staple",
            role=Role.ADMIN,
        )

    assert any(
        error["loc"] == ("email",) and error["type"] == "value_error"
        for error in exc_info.value.errors()
    )


def test_user_create_rejects_short_password() -> None:
    """少于 12 个字符的密码应在输入边界被拒绝。"""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="admin@example.com",
            full_name="MarketMind Admin",
            password="too-short",
            role=Role.ADMIN,
        )

    assert any(
        error["loc"] == ("password",) and error["type"] == "string_too_short"
        for error in exc_info.value.errors()
    )


def test_user_update_allows_partial_fields() -> None:
    """更新对象应只包含调用者实际提供的字段。"""
    empty_update = UserUpdate()
    role_update = UserUpdate(role=Role.OPERATOR)

    assert empty_update.model_dump(exclude_unset=True) == {}
    assert role_update.model_dump(exclude_unset=True) == {"role": Role.OPERATOR}


def test_user_read_accepts_orm_model_without_exposing_password_hash() -> None:
    """输出 Schema 应读取 ORM 属性并过滤密码哈希。"""
    now = datetime(2026, 8, 28, tzinfo=UTC)
    user = User(
        id=1,
        email="analyst@example.com",
        full_name="MarketMind Analyst",
        password_hash="must-not-appear",
        role=Role.ANALYST,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    data = UserRead.model_validate(user)

    assert data.model_dump() == {
        "id": 1,
        "email": "analyst@example.com",
        "full_name": "MarketMind Analyst",
        "role": Role.ANALYST,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    assert "password_hash" not in data.model_dump()


def test_user_page_contains_items_and_pagination_metadata() -> None:
    """分页输出应同时包含用户列表和分页元数据。"""
    now = datetime(2026, 8, 28, tzinfo=UTC)
    item = UserRead(
        id=1,
        email="analyst@example.com",
        full_name="MarketMind Analyst",
        role=Role.ANALYST,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    page = UserPage(items=[item], total=1, page=1, page_size=20)

    assert page.items == [item]
    assert page.total == 1
    assert page.page == 1
    assert page.page_size == 20


def test_user_page_rejects_zero_page_size()->None:
    pytest.raises(ValidationError, UserPage, items=[], total=0, page=1, page_size=0)
    
