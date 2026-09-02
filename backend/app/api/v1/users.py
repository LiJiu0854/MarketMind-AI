"""Admin 用户管理 API。"""

from hashlib import sha256
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, require_roles
from app.core.config import Settings
from app.core.errors import AppError
from app.db.redis import get_redis
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate
from app.services.redis_guards import (
    begin_idempotent_request,
    complete_idempotent_request,
    request_fingerprint,
)
from app.services.user_cache import get_user_with_cache, invalidate_user_cache
from app.services.users import create_user as create_user_service
from app.services.users import (
    deactivate_user,
    get_user,
    list_users,
    update_user,
)

router = APIRouter(
    prefix="/users",
    tags=["用户管理"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserRead:
    """创建内部平台用户。"""
    fingerprint = request_fingerprint(
        actor_id=actor.id,
        path=request.url.path,
        payload=data.model_dump(mode="json"),
    )
    key_digest = sha256(idempotency_key.encode()).hexdigest()
    redis_key = f"marketmind:idempotency:create-user:{actor.id}:{key_digest}"

    settings = cast(Settings, request.app.state.settings)
    cached_response = await begin_idempotent_request(
        redis,
        redis_key,
        fingerprint,
        settings.idempotency_processing_ttl_seconds,
    )

    if cached_response is not None:
        return UserRead.model_validate_json(cached_response)

    new_user = await create_user_service(session, data)
    user_read = UserRead.model_validate(new_user)
    await complete_idempotent_request(
        redis,
        redis_key,
        fingerprint,
        user_read.model_dump_json(),
        settings.idempotency_result_ttl_seconds,
    )
    return user_read


@router.get("", response_model=UserPage)
async def read_users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPage:
    """分页读取用户。"""
    list_user = await list_users(session, page, page_size)
    return list_user


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserRead:
    """按 ID 读取用户。"""
    settings = cast(Settings, request.app.state.settings)
    return await get_user_with_cache(
        session,
        redis,
        user_id,
        settings.redis_cache_ttl_seconds,
    )


@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: int,
    data: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    """部分更新用户。"""
    target = await get_user(session, user_id)
    if actor.id == target.id and data.role is not None and data.role != actor.role:
        raise AppError(
            code="USER_SELF_ROLE_CHANGE_FORBIDDEN",
            message="不能修改当前用户自己的角色",
            status_code=409,
        )

    updated_user = await update_user(session, target, data)
    await invalidate_user_cache(redis, user_id)
    return updated_user


@router.delete("/{user_id}", response_model=UserRead)
async def delete_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    """软停用用户。"""
    target = await get_user(session, user_id)
    await deactivate_user(session, target, actor)
    await invalidate_user_cache(redis, user_id)
    return target
