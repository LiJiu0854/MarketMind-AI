"""角色授权依赖测试。"""

import pytest

from app.api.dependencies import require_roles
from app.core.errors import AppError
from app.models.user import Role, User


def make_user(role: Role) -> User:
    """创建无需数据库连接的角色测试用户。"""
    return User(
        email=f"{role.value}@example.com",
        full_name=role.value,
        password_hash="not-used-in-this-test",
        role=role,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_require_roles_returns_allowed_user() -> None:
    """允许列表中的角色应取得原来的当前用户。"""
    admin = make_user(Role.ADMIN)
    require_admin = require_roles(Role.ADMIN)

    assert await require_admin(admin) is admin


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
async def test_require_roles_rejects_disallowed_role(role: Role) -> None:
    """不在允许列表中的角色必须得到稳定的 403 业务异常。"""
    require_admin = require_roles(Role.ADMIN)

    with pytest.raises(AppError) as exc_info:
        await require_admin(make_user(role))

    assert exc_info.value.code == "PERMISSION_DENIED"
    assert exc_info.value.message == "权限不足"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_roles_accepts_any_listed_role() -> None:
    """依赖工厂应支持为一个接口声明多个允许角色。"""
    require_staff = require_roles(Role.ADMIN, Role.OPERATOR)

    assert await require_staff(make_user(Role.OPERATOR))
