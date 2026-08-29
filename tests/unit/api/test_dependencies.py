"""数据库 Session 依赖测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import dependencies


@pytest.mark.asyncio
async def test_get_db_session_yields_an_async_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求依赖应创建 Session，并在生成器结束时自动关闭。"""
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+asyncmy://user:password@localhost/marketmind",
    )
    dependencies._get_session_factory.cache_clear()
    generator = dependencies.get_db_session()

    session = await anext(generator)

    assert isinstance(session, AsyncSession)
    with pytest.raises(StopAsyncIteration):
        await anext(generator)
    engine = dependencies._get_session_factory().kw["bind"]
    await engine.dispose()
    dependencies._get_session_factory.cache_clear()
