"""跨测试目录共享的真实测试数据库夹具。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.session import create_engine
from app.models.user import User


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


@pytest_asyncio.fixture
async def session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """在外层事务中提供可提交的隔离 Session。"""
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(delete(User))
        db_session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            if transaction.is_active:
                await transaction.rollback()
