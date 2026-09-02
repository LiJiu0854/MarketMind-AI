
import asyncio

from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.config import Settings
from app.db.redis import close_redis_client, create_redis_client
from app.db.session import create_engine, create_session_factory
from app.models.user import Role, User
from app.services.redis_guards import redis_lock

USER_STATS_LOCK_KEY = "marketmind:lock:user-stats"

async def query_user_stats(session: AsyncSession) -> dict[str, int]:
    """
    执行聚合查询，返回用户统计数字。
    这是唯一执行 SQL 的函数，不创建连接，不管理事务。
    """
    # 1. 构造聚合查询
    stmt = select(
        func.count(User.id).label("total"),  # 总用户数
        func.sum(
            case((User.is_active.is_(True), 1), else_=0)
        ).label("active"),  # 活跃用户数
        func.sum(
            case((User.is_active.is_(False), 1), else_=0)
        ).label("inactive"),  # 停用用户数
        func.sum(
            case((User.role == Role.ADMIN, 1), else_=0)
        ).label("admin"),  # 管理员数
        func.sum(
            case((User.role == Role.OPERATOR, 1), else_=0)
        ).label("operator"),  # 操作员数
        func.sum(
            case((User.role == Role.ANALYST, 1), else_=0)
        ).label("analyst"),  # 分析员数
    )

    # 2. 执行查询，拿到一行结果
    result = await session.execute(stmt)
    row = result.one()

    # 3. 转换成普通字典（只包含 int，没有 ORM 对象、datetime 等）
    return {
        "total": row.total or 0,
        "active": row.active or 0,
        "inactive": row.inactive or 0,
        "admin": row.admin or 0,
        "operator": row.operator or 0,
        "analyst": row.analyst or 0,
    }


async def collect_user_stats() -> dict[str, int]:
    """
    创建独立的数据库连接，执行统计，然后释放连接池。
    Worker 没有 FastAPI 请求，必须自己管理 Session 生命周期。
    """

    settings = Settings()
    database_url = settings.database_url
    if database_url is None:
        raise RuntimeError("DATABASE_URL 未配置")

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            stats = await query_user_stats(session)
        return stats
    finally:
        await engine.dispose()


async def run_user_stats_with_lock() -> dict[str, int | str]:
    """
    用 Redis 锁保护统计任务，确保同一时刻只有一个 Worker 在执行。
    """
    settings = Settings()
    redis_url = settings.redis_url
    if redis_url is None:
        raise RuntimeError("REDIS_URL 未配置")
    redis = create_redis_client(redis_url)

    try:
        async with redis_lock(redis, USER_STATS_LOCK_KEY, 30000) as acquired:
            if not acquired:
                return {"status": "already_running"}

            stats = await collect_user_stats()
            result: dict[str, int | str] = {
                key: value for key, value in stats.items()
            }
            result["status"] = "completed"
            return result
    finally:
        await close_redis_client(redis)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.user_stats.generate_user_stats",
    autoretry_for=(OperationalError,),  # 只有数据库连接错误才重试
    retry_backoff=True,                # 指数退避：1s, 2s, 4s...
    retry_kwargs={"max_retries": 3},
)
def generate_user_stats() -> dict[str, int | str]:
    """
    Celery 可执行的同步任务入口。
    """
    return asyncio.run(run_user_stats_with_lock())
