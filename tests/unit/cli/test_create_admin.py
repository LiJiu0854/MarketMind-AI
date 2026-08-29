"""管理员创建 CLI 测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.cli import create_admin
from app.models.user import Role
from app.schemas.user import UserCreate


def test_read_admin_data_uses_hidden_password_and_admin_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 应隐藏读取密码，并固定创建 Admin。"""
    answers = iter(["ADMIN@EXAMPLE.COM", "MarketMind Admin"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(
        create_admin, "getpass", lambda _prompt: "correct-horse-battery-staple"
    )

    data = create_admin.read_admin_data()

    assert str(data.email) == "admin@example.com"
    assert data.full_name == "MarketMind Admin"
    assert data.role is Role.ADMIN


@pytest.mark.asyncio
async def test_main_reuses_create_user_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 应复用 Service，并始终释放数据库 Engine。"""
    data = UserCreate(
        email="admin@example.com",
        full_name="MarketMind Admin",
        password="correct-horse-battery-staple",
        role=Role.ADMIN,
    )
    session = object()

    class SessionContext:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    engine = SimpleNamespace(dispose=AsyncMock())
    create_user = AsyncMock(return_value=SimpleNamespace(email="admin@example.com"))
    monkeypatch.setattr(create_admin, "read_admin_data", lambda: data)
    monkeypatch.setattr(
        create_admin,
        "Settings",
        lambda: SimpleNamespace(database_url=SecretStr("mysql+asyncmy://test")),
    )
    monkeypatch.setattr(create_admin, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        create_admin, "create_session_factory", lambda _engine: SessionContext
    )
    monkeypatch.setattr(create_admin, "create_user", create_user)

    exit_code = await create_admin.main()

    assert exit_code == 0
    create_user.assert_awaited_once_with(session, data)
    engine.dispose.assert_awaited_once()
