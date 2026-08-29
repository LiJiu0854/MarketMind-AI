"""FastAPI 数据库会话与当前用户依赖。"""

from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import create_engine, create_session_factory
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@cache
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """为应用进程创建并复用一个数据库 Session 工厂。"""
    database_url = Settings().database_url
    if database_url is None:
        raise RuntimeError("DATABASE_URL 未配置")
    return create_session_factory(create_engine(database_url))


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """为一次请求提供并自动关闭独立的数据库 Session。"""
    async with _get_session_factory()() as session:
        yield session


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """验证 Bearer Token，并返回数据库中的当前有效用户。"""
    settings = Settings()
    secret = settings.jwt_secret

    if secret is None:
        raise RuntimeError("JWT_SECRET 未配置")

    try:
        user_id = decode_access_token(token, secret)
    except InvalidTokenError:
        raise AppError(
            code="AUTH_INVALID_TOKEN",
            message="登录凭证无效",
            status_code=401,
        ) from None

    user = await session.get(User, user_id)

    if user is None:
        raise AppError(
            code="AUTH_INVALID_TOKEN",
            message="登录凭证无效",
            status_code=401,
        )

    if not user.is_active:
        raise AppError(
            code="ACCOUNT_INACTIVE",
            message="账号已停用",
            status_code=403,
        )

    return user
