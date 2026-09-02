"""Redis 幂等、限流和分布式锁。"""

import json
import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import AppError

logger = logging.getLogger(__name__)

LOCK_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

COMPLETE_IDEMPOTENCY_SCRIPT = """
local raw = redis.call("GET", KEYS[1])
if not raw then
    return 0
end
local record = cjson.decode(raw)
if record["fingerprint"] ~= ARGV[1] then
    return -1
end
redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
return 1
"""

RATE_LIMIT_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


def request_fingerprint(
    actor_id: int,
    path: str,
    payload: dict[str, object],
) -> str:
    normalized = {"actor_id": actor_id, "path": path, "payload": payload}
    stable_json = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(stable_json.encode()).hexdigest()


async def begin_idempotent_request(
    redis: Redis,
    key: str,
    fingerprint: str,
    ttl_seconds: int,
) -> str | None:
    processing = json.dumps(
        {"fingerprint": fingerprint, "status": "processing"},
        separators=(",", ":"),
    )
    try:
        acquired = await redis.set(key, processing, nx=True, ex=ttl_seconds)
        if acquired:
            return None
        existing_raw = await redis.get(key)
    except RedisError as exc:
        raise AppError(
            code="IDEMPOTENCY_UNAVAILABLE",
            message="幂等检查服务暂时不可用",
            status_code=503,
        ) from exc

    if not isinstance(existing_raw, str):
        raise AppError(
            code="IDEMPOTENCY_REQUEST_CONFLICT",
            message="请求正在处理中，请稍后重试",
            status_code=409,
        )

    record = json.loads(existing_raw)
    if record.get("fingerprint") != fingerprint:
        raise AppError(
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="幂等键已用于其他请求",
            status_code=409,
        )
    if record.get("status") != "completed":
        raise AppError(
            code="IDEMPOTENCY_REQUEST_CONFLICT",
            message="请求正在处理中，请稍后重试",
            status_code=409,
        )

    response = record.get("response")
    if not isinstance(response, str):
        raise ValueError("已完成的幂等记录缺少响应 JSON")
    return response


async def complete_idempotent_request(
    redis: Redis,
    key: str,
    fingerprint: str,
    response_json: str,
    ttl_seconds: int,
) -> None:
    completed = json.dumps(
        {
            "fingerprint": fingerprint,
            "status": "completed",
            "response": response_json,
        },
        separators=(",", ":"),
    )
    try:
        result = await cast(
            Awaitable[object],
            redis.eval(
                COMPLETE_IDEMPOTENCY_SCRIPT,
                1,
                key,
                fingerprint,
                completed,
                str(ttl_seconds),
            ),
        )
    except RedisError as exc:
        raise AppError(
            code="IDEMPOTENCY_UNAVAILABLE",
            message="幂等检查服务暂时不可用",
            status_code=503,
        ) from exc

    if result != 1:
        raise AppError(
            code="IDEMPOTENCY_REQUEST_CONFLICT",
            message="幂等记录已失效，请重新提交",
            status_code=409,
        )


async def enforce_login_rate_limit(
    redis: Redis,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    digest = sha256(identity.encode()).hexdigest()
    key = f"marketmind:rate-limit:login:{digest}"
    try:
        result = await cast(
            Awaitable[object],
            redis.eval(RATE_LIMIT_SCRIPT, 1, key, str(window_seconds)),
        )
    except RedisError as exc:
        raise AppError(
            code="RATE_LIMIT_UNAVAILABLE",
            message="登录保护服务暂时不可用",
            status_code=503,
        ) from exc

    if not isinstance(result, (list, tuple)) or len(result) != 2:
        raise ValueError("限流脚本返回了无效结果")
    current, ttl = int(result[0]), int(result[1])
    if current > limit:
        retry_after = str(max(1, ttl))
        raise AppError(
            code="LOGIN_RATE_LIMITED",
            message="登录尝试次数过多，请稍后重试",
            status_code=429,
            headers={"Retry-After": retry_after},
        )


@asynccontextmanager
async def redis_lock(
    redis: Redis,
    key: str,
    ttl_ms: int,
) -> AsyncIterator[bool]:
    owner = str(uuid4())
    try:
        acquired = bool(await redis.set(key, owner, nx=True, px=ttl_ms))
    except RedisError as exc:
        raise AppError(
            code="LOCK_UNAVAILABLE",
            message="锁服务暂时不可用",
            status_code=503,
        ) from exc

    try:
        yield acquired
    finally:
        if acquired:
            try:
                await cast(
                    Awaitable[object],
                    redis.eval(LOCK_RELEASE_SCRIPT, 1, key, owner),
                )
            except RedisError:
                logger.error("释放 Redis 锁失败", exc_info=True)
