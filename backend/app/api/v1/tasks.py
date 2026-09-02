"""后台任务投递与状态查询 API。"""

import logging

from celery.exceptions import CeleryError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, status
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from redis.exceptions import RedisError

from app.api.dependencies import require_roles
from app.celery_app import celery_app
from app.core.errors import AppError
from app.models.user import Role
from app.schemas.task import TaskCreated, TaskStatus
from app.tasks.user_stats import generate_user_stats

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tasks",
    tags=["后台任务"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post(
    "/user-stats",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_user_stats_task() -> TaskCreated:
    try:
        queued = generate_user_stats.delay()
        return TaskCreated(task_id=queued.id)
    except (BrokerOperationalError, CeleryError, RedisError) as exc:
        logger.error("投递任务失败")
        raise AppError(
            code="TASK_DISPATCH_FAILED",
            message="任务投递服务暂时不可用",
            status_code=503,
        ) from exc


@router.get("/{task_id}", response_model=TaskStatus)
async def read_task_status(task_id: str) -> TaskStatus:
    try:
        result = celery_app.AsyncResult(task_id)
        state = result.state

        if state == "PENDING":
            return TaskStatus(task_id=task_id, state="PENDING")
        if state == "STARTED":
            return TaskStatus(task_id=task_id, state="STARTED")
        if state == "SUCCESS":
            return TaskStatus(
                task_id=task_id,
                state="SUCCESS",
                result=result.result,
            )
        if state == "FAILURE":
            return TaskStatus(
                task_id=task_id,
                state="FAILURE",
                error="任务执行失败",
            )
        return TaskStatus(task_id=task_id, state="STARTED")
    except (BrokerOperationalError, CeleryError, RedisError) as exc:
        logger.error("查询任务状态失败")
        raise AppError(
            code="TASK_STATUS_UNAVAILABLE",
            message="任务状态查询服务暂时不可用",
            status_code=503,
        ) from exc
