"""数据库集成测试夹具。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.session import create_engine


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """创建只允许连接 marketmind_test 的异步引擎。"""
    database_url = Settings().test_database_url
    if database_url is None:
        pytest.fail("TEST_DATABASE_URL 未配置")
    if make_url(database_url.get_secret_value()).database != "marketmind_test":
        pytest.fail("集成测试只能连接 marketmind_test")

    engine = create_engine(database_url)
    yield engine
    await engine.dispose()
