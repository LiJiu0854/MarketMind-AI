"""Redis 客户端生命周期和请求依赖。"""

from typing import cast

from fastapi import Request
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.errors import AppError


def create_redis_client(url: SecretStr) -> Redis:
    """创建 Redis 客户端。"""
    redis_url = url.get_secret_value()
    return cast(Redis, Redis.from_url(redis_url, decode_responses=True))


async def close_redis_client(client: Redis) -> None:
    """关闭 Redis 客户端。"""
    await client.aclose()


def get_redis(request: Request) -> Redis:
    """获取 Redis 客户端。"""
    client = request.app.state.redis

    if client is None:
        raise AppError(
            code="REDIS_NOT_CONFIGURED",
            message="Redis 客户端未配置",
            status_code=503,
        )

    return cast(Redis, client)
