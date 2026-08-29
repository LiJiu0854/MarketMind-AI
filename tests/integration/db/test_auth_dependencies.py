"""当前用户依赖的真实 MySQL 集成测试。"""

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.core.security import create_access_token
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"


def user_data(index: int) -> UserCreate:
    """构造当前用户测试数据。"""
    return UserCreate(
        email=f"auth-{index}@example.com",
        full_name=f"Auth User {index}",
        password="correct-horse-battery-staple",
        role=Role.ANALYST,
    )


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """为当前测试提供不进入 Git 配置文件的测试密钥。"""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest.mark.asyncio
async def test_get_current_user_returns_token_user(session: AsyncSession) -> None:
    """有效 Token 应还原为数据库中的用户。"""
    user = await create_user(session, user_data(1))
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)

    assert await get_current_user(token, session) is user


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["not-a-jwt", ""])
async def test_get_current_user_rejects_invalid_token(
    session: AsyncSession, token: str
) -> None:
    """格式错误或缺失的 Token 应统一返回 401。"""
    with pytest.raises(AppError) as exc_info:
        await get_current_user(token, session)

    assert exc_info.value.code == "AUTH_INVALID_TOKEN"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_user(session: AsyncSession) -> None:
    """签名正确但用户不存在的 Token 仍然无效。"""
    token = create_access_token(999_999, SecretStr(JWT_SECRET), 30)

    with pytest.raises(AppError) as exc_info:
        await get_current_user(token, session)

    assert exc_info.value.code == "AUTH_INVALID_TOKEN"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_user(session: AsyncSession) -> None:
    """签名正确但账号已停用时应返回 403。"""
    user = await create_user(session, user_data(1))
    user.is_active = False
    await session.commit()
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)

    with pytest.raises(AppError) as exc_info:
        await get_current_user(token, session)

    assert exc_info.value.code == "ACCOUNT_INACTIVE"
    assert exc_info.value.status_code == 403
