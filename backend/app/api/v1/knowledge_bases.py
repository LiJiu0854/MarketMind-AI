"""Knowledge-base management and document read endpoints."""

from typing import Annotated

from celery.exceptions import CeleryError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, require_roles
from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.user import Role, User
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBasePage,
    KnowledgeBaseRead,
    KnowledgeDocumentCreated,
    KnowledgeDocumentPage,
    KnowledgeDocumentRead,
)
from app.services.knowledge import (
    attach_document_task_id,
    create_knowledge_base,
    get_knowledge_base,
    get_knowledge_document,
    list_knowledge_bases,
    list_knowledge_documents,
    mark_document_dispatch_failure,
    stage_knowledge_document,
    validate_upload,
)
from app.tasks.knowledge import index_knowledge_document

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["RAG 知识库"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def create_base(
    payload: KnowledgeBaseCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Admin,
) -> KnowledgeBase:
    settings: Settings = request.app.state.settings
    return await create_knowledge_base(session, payload, actor.id, settings)


@router.get("", response_model=KnowledgeBasePage)
async def read_bases(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> KnowledgeBasePage:
    items, total = await list_knowledge_bases(session, page, page_size)
    return KnowledgeBasePage(
        items=[KnowledgeBaseRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def read_base(
    knowledge_base_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeBase:
    return await get_knowledge_base(session, knowledge_base_id)


@router.get("/{knowledge_base_id}/documents", response_model=KnowledgeDocumentPage)
async def read_documents(
    knowledge_base_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> KnowledgeDocumentPage:
    items, total = await list_knowledge_documents(session, knowledge_base_id, page, page_size)
    return KnowledgeDocumentPage(
        items=[KnowledgeDocumentRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=KnowledgeDocumentCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    knowledge_base_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Admin,
    file: Annotated[UploadFile, File()],
) -> KnowledgeDocumentCreated:
    settings: Settings = request.app.state.settings
    validated = await validate_upload(file, settings.knowledge_max_file_bytes)
    document = await stage_knowledge_document(
        session, knowledge_base_id, actor.id, validated, settings.knowledge_file_root
    )
    try:
        queued = index_knowledge_document.delay(document.id)
    except (BrokerOperationalError, CeleryError, RedisError) as error:
        await mark_document_dispatch_failure(session, document.id)
        raise AppError(
            "KNOWLEDGE_DOCUMENT_DISPATCH_FAILED", "文档任务投递服务暂时不可用", 503
        ) from error
    document = await attach_document_task_id(session, document.id, queued.id)
    return KnowledgeDocumentCreated(
        document_id=document.id, task_id=queued.id, status=document.status
    )


@router.get("/{knowledge_base_id}/documents/{document_id}", response_model=KnowledgeDocumentRead)
async def read_document(
    knowledge_base_id: int,
    document_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeDocument:
    return await get_knowledge_document(session, knowledge_base_id, document_id)
