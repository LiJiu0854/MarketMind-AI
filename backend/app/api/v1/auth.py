"""登录与当前用户 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.core.config import Settings
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRead
from app.services.users import authenticate_user

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/token", response_model=TokenResponse, summary="账号登录")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """验证邮箱和密码并签发 Access Token。"""
    settings = Settings()
    secret = settings.jwt_secret

    if secret is None:
        raise RuntimeError("JWT_SECRET 未配置")

    user = await authenticate_user(
        session,
        email=form_data.username,
        password=form_data.password,
    )

    token = create_access_token(
        user_id=user.id,
        secret=secret,
        expires_minutes=settings.access_token_expire_minutes,
    )

    return TokenResponse(access_token=token, token_type="bearer")

@router.get("/me", response_model=UserRead, summary="读取当前用户")
async def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """返回依赖已经验证的当前有效用户。"""
    return current_user
