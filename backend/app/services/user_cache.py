"""单个用户的 Cache Aside 服务。"""

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserRead
from app.services.users import get_user

logger = logging.getLogger(__name__)


def user_cache_key(user_id: int) -> str:
    return f"marketmind:user:v1:{user_id}"


async def get_user_with_cache(
    session: AsyncSession,
    redis: Redis,
    user_id: int,
    ttl_seconds: int,
) -> UserRead:
    cache_key = user_cache_key(user_id)

    try:
        cached_user = await redis.get(cache_key)
    except RedisError:
        logger.warning("读取用户缓存失败", exc_info=True)
    else:
        if cached_user is not None:
            return UserRead.model_validate_json(cached_user)

    user = await get_user(session, user_id)
    user_read = UserRead.model_validate(user)

    try:
        await redis.set(cache_key, user_read.model_dump_json(), ex=ttl_seconds)
    except RedisError:
        logger.warning("写入用户缓存失败", exc_info=True)

    return user_read


async def invalidate_user_cache(redis: Redis, user_id: int) -> None:
    try:
        await redis.delete(user_cache_key(user_id))
    except RedisError:
        logger.error("删除用户缓存失败", exc_info=True)
