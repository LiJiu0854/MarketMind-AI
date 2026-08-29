"""用户 Service 的真实 MySQL 集成测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import verify_password
from app.models.user import Role
from app.schemas.user import UserCreate, UserUpdate
from app.services.users import (
    authenticate_user,
    create_user,
    deactivate_user,
    get_user,
    list_users,
    update_user,
)


def user_data(index: int, *, role: Role = Role.ANALYST) -> UserCreate:
    """构造互不冲突的测试用户输入。"""
    return UserCreate(
        email=f"USER-{index}@EXAMPLE.COM",
        full_name=f"Test User {index}",
        password="correct-horse-battery-staple",
        role=role,
    )


@pytest.mark.asyncio
async def test_create_user_normalizes_email_and_hashes_password(
    session: AsyncSession,
) -> None:
    """创建用户应标准化邮箱，并且数据库中只能保存密码哈希。"""
    data = user_data(1, role=Role.ADMIN)

    user = await create_user(session, data)

    assert user.id is not None
    assert user.email == "user-1@example.com"
    assert user.password_hash != data.password
    assert verify_password(data.password, user.password_hash)


@pytest.mark.asyncio
async def test_authenticate_user_accepts_normalized_email_and_correct_password(
    session: AsyncSession,
) -> None:
    """登录邮箱应复用规范化规则，正确密码返回数据库用户。"""
    created = await create_user(session, user_data(1))

    authenticated = await authenticate_user(
        session,
        email="  USER-1@EXAMPLE.COM  ",
        password="correct-horse-battery-staple",
    )

    assert authenticated is created


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("missing@example.com", "wrong-password"),
        ("user-1@example.com", "wrong-password"),
    ],
)
async def test_authenticate_user_hides_which_credential_is_wrong(
    session: AsyncSession,
    email: str,
    password: str,
) -> None:
    """邮箱不存在和密码错误必须产生完全相同的认证失败。"""
    await create_user(session, user_data(1))

    with pytest.raises(AppError) as exc_info:
        await authenticate_user(session, email=email, password=password)

    assert exc_info.value.code == "AUTH_INVALID_CREDENTIALS"
    assert exc_info.value.message == "邮箱或密码错误"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_user_rejects_inactive_account(
    session: AsyncSession,
) -> None:
    """密码正确但已停用的账号不能登录。"""
    user = await create_user(session, user_data(1))
    user.is_active = False
    await session.commit()

    with pytest.raises(AppError) as exc_info:
        await authenticate_user(
            session,
            email=user.email,
            password="correct-horse-battery-staple",
        )

    assert exc_info.value.code == "ACCOUNT_INACTIVE"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_normalized_email(
    session: AsyncSession,
) -> None:
    """大小写不同但实际相同的邮箱应产生 409 业务异常。"""
    await create_user(session, user_data(1))

    with pytest.raises(AppError) as exc_info:
        await create_user(
            session,
            UserCreate(
                email="user-1@example.com",
                full_name="Duplicate User",
                password="correct-horse-battery-staple",
                role=Role.OPERATOR,
            ),
        )

    assert exc_info.value.code == "USER_EMAIL_CONFLICT"
    assert exc_info.value.status_code == 409
    assert await create_user(session, user_data(2))


@pytest.mark.asyncio
async def test_get_user_returns_user_and_rejects_missing_id(
    session: AsyncSession,
) -> None:
    """按 ID 查询应返回已有用户，并把不存在转换为 404。"""
    created = await create_user(session, user_data(1))

    assert await get_user(session, created.id) is created
    with pytest.raises(AppError) as exc_info:
        await get_user(session, created.id + 999)

    assert exc_info.value.code == "USER_NOT_FOUND"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_users_returns_stable_page_and_total(
    session: AsyncSession,
) -> None:
    """分页应返回准确总数，并按 ID 稳定排序。"""
    users = [await create_user(session, user_data(index)) for index in range(1, 4)]

    result = await list_users(session, page=2, page_size=2)

    assert result.total == 3
    assert [item.id for item in result.items] == [users[2].id]
    assert result.page == 2
    assert result.page_size == 2


@pytest.mark.asyncio
async def test_update_user_only_changes_provided_fields(
    session: AsyncSession,
) -> None:
    """部分更新不能覆盖调用者未提交的字段。"""
    user = await create_user(session, user_data(1))
    old_email = user.email
    old_hash = user.password_hash

    updated = await update_user(session, user, UserUpdate(full_name="Updated Name"))

    assert updated.full_name == "Updated Name"
    assert updated.email == old_email
    assert updated.password_hash == old_hash


@pytest.mark.asyncio
async def test_update_user_normalizes_email_and_rehashes_password(
    session: AsyncSession,
) -> None:
    """邮箱和密码更新应继续遵守创建时的安全规则。"""
    user = await create_user(session, user_data(1))
    new_password = "another-correct-horse-password"

    updated = await update_user(
        session,
        user,
        UserUpdate(email="NEW@EXAMPLE.COM", password=new_password),
    )

    assert updated.email == "new@example.com"
    assert updated.password_hash != new_password
    assert verify_password(new_password, updated.password_hash)


@pytest.mark.asyncio
async def test_deactivate_user_keeps_database_record(
    session: AsyncSession,
) -> None:
    """停用用户只改变状态，不能删除数据库记录。"""
    actor = await create_user(session, user_data(1, role=Role.ADMIN))
    target = await create_user(session, user_data(2))

    deactivated = await deactivate_user(session, target, actor)

    assert deactivated.is_active is False
    assert await get_user(session, target.id) is target


@pytest.mark.asyncio
async def test_deactivate_user_rejects_self_deactivation(
    session: AsyncSession,
) -> None:
    """操作者不能停用自己的账号。"""
    actor = await create_user(session, user_data(1, role=Role.ADMIN))

    with pytest.raises(AppError) as exc_info:
        await deactivate_user(session, actor, actor)

    assert exc_info.value.code == "USER_SELF_DEACTIVATE_FORBIDDEN"
    assert exc_info.value.status_code == 409
