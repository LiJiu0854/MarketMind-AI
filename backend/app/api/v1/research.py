"""商品研究任务 API。"""

from typing import Annotated

from celery.exceptions import CeleryError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Query, Request, status
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, require_roles
from app.celery_app import celery_app
from app.core.config import Settings
from app.core.errors import AppError
from app.models.research import ResearchRun
from app.models.user import Role, User
from app.schemas.research import ResearchCreate, ResearchCreated, ResearchPage, ResearchRead
from app.services.research import (
    create_research_run,
    get_research_run,
    list_research_runs,
    mark_research_failure,
    set_research_task_id,
)

ResearchManager = Annotated[User, Depends(require_roles(Role.ADMIN, Role.OPERATOR))]

router = APIRouter(
    prefix="/products",
    tags=["受控商品研究"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/{product_id}/research-runs",
    response_model=ResearchCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_product_research(
    product_id: int,
    payload: ResearchCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ResearchManager,
) -> ResearchCreated:
    settings: Settings = request.app.state.settings
    run = await create_research_run(session, product_id, actor.id, payload, settings)
    try:
        task = celery_app.send_task("app.tasks.research.run_research", args=[run.id])
    except (BrokerOperationalError, CeleryError, RedisError) as exc:
        await mark_research_failure(session, run.id, "RESEARCH_DISPATCH_FAILED", "研究任务投递失败")
        raise AppError("RESEARCH_DISPATCH_FAILED", "研究任务投递服务暂时不可用", 503) from exc
    run = await set_research_task_id(session, run.id, task.id)
    return ResearchCreated(run_id=run.id, task_id=task.id, status=run.status)


@router.get("/{product_id}/research-runs", response_model=ResearchPage)
async def read_research_runs(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResearchPage:
    items, total = await list_research_runs(session, product_id, page, page_size)
    return ResearchPage(
        items=[ResearchRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{product_id}/research-runs/{run_id}", response_model=ResearchRead)
async def read_research_run(
    product_id: int,
    run_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResearchRun:
    return await get_research_run(session, product_id, run_id)
