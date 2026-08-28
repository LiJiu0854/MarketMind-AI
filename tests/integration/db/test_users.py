"""User Model 的真实 MySQL 集成测试。"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.user import Role, User


@pytest.mark.asyncio
async def test_user_write_is_rolled_back(test_engine: AsyncEngine) -> None:
    """外层事务回滚后，测试用户不会残留在数据库中。"""
    email = "task1-transaction@example.com"

    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            user = User(
                email=email,
                full_name="Task 1 Transaction",
                password_hash="not-a-real-password-hash",
                role=Role.ANALYST,
            )
            session.add(user)
            await session.flush()

            stored_user = await session.scalar(
                select(User).where(User.email == email)
            )
            assert stored_user is not None
            assert stored_user.id is not None
        finally:
            await session.close()
            await transaction.rollback()

    async with test_engine.connect() as connection:
        remaining = await connection.scalar(
            select(func.count()).select_from(User).where(User.email == email)
        )

    assert remaining == 0
