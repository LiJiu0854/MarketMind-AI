"""异步数据库 Engine 与 Session 工厂。"""

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: SecretStr) -> AsyncEngine:
    """创建带连接存活检查的异步数据库 Engine。"""
    return create_async_engine(database_url.get_secret_value(), pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """创建提交后仍可读取 ORM 属性的异步 Session 工厂。"""
    return async_sessionmaker(engine, expire_on_commit=False)
