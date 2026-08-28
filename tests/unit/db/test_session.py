"""异步数据库资源工厂测试。"""

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import create_engine, create_session_factory


@pytest.mark.asyncio
async def test_create_database_resources() -> None:
    """工厂返回错误的 Engine 或 Session 类型时应失败。"""
    engine = create_engine(
        SecretStr("mysql+asyncmy://user:not-a-real-password@localhost/database")
    )
    session_factory = create_session_factory(engine)

    assert isinstance(engine, AsyncEngine)
    assert session_factory.class_ is AsyncSession
    assert session_factory.kw["expire_on_commit"] is False

    await engine.dispose()
