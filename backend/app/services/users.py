"""用户业务服务。"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate


def _normalize_email(email: str) -> str:
    """把邮箱转换为数据库中的统一形式。"""
    return email.strip().lower()


def _email_conflict() -> AppError:
    """创建统一的邮箱冲突业务异常。"""
    return AppError(
        code="USER_EMAIL_CONFLICT",
        message="用户邮箱已存在",
        status_code=409,
    )


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """创建用户；邮箱冲突时抛出统一业务异常。"""
    email = _normalize_email(str(data.email))

    try:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise _email_conflict()

        user = User(
            email=email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _email_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def get_user(session: AsyncSession, user_id: int) -> User:
    """按 ID 查询用户，不存在时抛出业务异常。"""
    user = await session.get(User, user_id)
    if user is None:
        raise AppError(
            code="USER_NOT_FOUND",
            message="用户不存在",
            status_code=404,
        )
    return user


async def list_users(
    session: AsyncSession, page: int, page_size: int
) -> UserPage:
    """按 ID 稳定排序并分页返回用户。"""
    total = await session.scalar(select(func.count()).select_from(User)) or 0
    users = (
        await session.scalars(
            select(User)
            .order_by(User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return UserPage(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_user(
    session: AsyncSession, user: User, data: UserUpdate
) -> User:
    """只更新调用者实际提供的字段。"""
    updates = data.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return user

    try:
        email = updates.pop("email", None)
        if email is not None:
            normalized_email = _normalize_email(str(email))
            existing = await session.scalar(
                select(User).where(
                    User.email == normalized_email,
                    User.id != user.id,
                )
            )
            if existing is not None:
                raise _email_conflict()
            user.email = normalized_email

        password = updates.pop("password", None)
        if password is not None:
            user.password_hash = hash_password(str(password))

        for field, value in updates.items():
            setattr(user, field, value)

        await session.commit()
        await session.refresh(user)
        return user
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _email_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def deactivate_user(
    session: AsyncSession, user: User, actor: User
) -> User:
    """软停用目标用户，但不允许操作者停用自己。"""
    if actor.id == user.id:
        await session.rollback()
        raise AppError(
            code="USER_SELF_DEACTIVATE_FORBIDDEN",
            message="不能停用当前登录用户",
            status_code=409,
        )

    try:
        user.is_active = False
        await session.commit()
        await session.refresh(user)
        return user
    except Exception:
        await session.rollback()
        raise
