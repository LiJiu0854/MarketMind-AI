"""Knowledge-base rows and safe local upload staging."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentStatus
from app.schemas.knowledge import KnowledgeBaseCreate
from app.services.document_ingestion import DocumentIngestionError

_MEDIA_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
}


@dataclass(frozen=True)
class ValidatedUpload:
    original_name: str
    suffix: Literal[".pdf", ".md", ".txt"]
    media_type: str
    data: bytes
    sha256: str


async def validate_upload(upload: UploadFile, max_bytes: int) -> ValidatedUpload:
    """Consume at most the configured limit plus one byte, then own closure."""
    try:
        name = Path(upload.filename or "").name
        suffix = Path(name).suffix.lower()
        media_type = upload.content_type or ""
        if not name or len(name) > 255 or suffix not in _MEDIA_TYPES:
            raise AppError("KNOWLEDGE_FILE_INVALID", "文件名或格式无效", 422)
        if media_type not in _MEDIA_TYPES[suffix]:
            raise AppError("KNOWLEDGE_FILE_INVALID", "文件类型与格式不符", 422)
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise AppError("KNOWLEDGE_FILE_TOO_LARGE", "文件超过大小限制", 413)
        if not data:
            raise AppError("KNOWLEDGE_FILE_INVALID", "文件内容不能为空", 422)
        if suffix == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise AppError("KNOWLEDGE_FILE_INVALID", "PDF 文件头无效", 422)
        else:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                raise AppError("KNOWLEDGE_FILE_INVALID", "文本文件必须为 UTF-8", 422) from None
        return ValidatedUpload(
            original_name=name,
            suffix=suffix,  # type: ignore[arg-type]
            media_type=media_type,
            data=data,
            sha256=sha256(data).hexdigest(),
        )
    finally:
        await upload.close()


async def create_knowledge_base(
    session: AsyncSession,
    payload: KnowledgeBaseCreate,
    creator_id: int,
    settings: Settings,
) -> KnowledgeBase:
    if not settings.embedding_model or settings.embedding_api_key is None:
        raise AppError("RAG_CONFIG_MISSING", "Embedding 配置缺失", 503)
    base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        created_by_id=creator_id,
        embedding_provider=settings.embedding_provider,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
    )
    session.add(base)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError("KNOWLEDGE_BASE_NAME_EXISTS", "知识库名称已存在", 409) from None
    await session.refresh(base)
    return base


async def get_knowledge_base(session: AsyncSession, knowledge_base_id: int) -> KnowledgeBase:
    base = await session.get(KnowledgeBase, knowledge_base_id)
    if base is None:
        raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", 404)
    return base


async def list_knowledge_bases(
    session: AsyncSession, page: int, page_size: int
) -> tuple[list[KnowledgeBase], int]:
    total = await session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
    items = (
        await session.scalars(
            select(KnowledgeBase)
            .order_by(KnowledgeBase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(items), total


def _store_upload(file_root: Path, relative_path: str, data: bytes) -> Path:
    root = file_root.resolve()
    destination = root / relative_path
    directory = destination.parent
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(root):
        raise AppError("KNOWLEDGE_FILE_INVALID", "文件存储路径无效", 422)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


async def stage_knowledge_document(
    session: AsyncSession,
    knowledge_base_id: int,
    uploader_id: int,
    upload: ValidatedUpload,
    file_root: Path,
) -> KnowledgeDocument:
    """Commit row and generated file; compensate file if the commit fails."""
    destination: Path | None = None
    try:
        base = await session.scalar(
            select(KnowledgeBase)
            .where(KnowledgeBase.id == knowledge_base_id)
            .with_for_update()
        )
        if base is None:
            raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", 404)
        duplicate = await session.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.sha256 == upload.sha256,
            )
        )
        if duplicate is not None:
            raise AppError("KNOWLEDGE_DOCUMENT_DUPLICATE", "文件内容已存在", 409)
        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base_id,
            uploaded_by_id=uploader_id,
            original_name=upload.original_name,
            media_type=upload.media_type,
            size_bytes=len(upload.data),
            sha256=upload.sha256,
            storage_path="",
        )
        session.add(document)
        await session.flush()
        document.storage_path = f"{knowledge_base_id}/{document.id}{upload.suffix}"
        destination = await asyncio.to_thread(
            _store_upload, file_root, document.storage_path, upload.data
        )
        await session.commit()
        await session.refresh(document)
        return document
    except IntegrityError:
        await session.rollback()
        if destination is not None:
            await asyncio.to_thread(destination.unlink, missing_ok=True)
        raise AppError("KNOWLEDGE_DOCUMENT_DUPLICATE", "文件内容已存在", 409) from None
    except Exception:
        await session.rollback()
        if destination is not None:
            await asyncio.to_thread(destination.unlink, missing_ok=True)
        raise


async def mark_document_dispatch_failure(session: AsyncSession, document_id: int) -> None:
    document = await session.get_one(KnowledgeDocument, document_id)
    document.status = KnowledgeDocumentStatus.FAILURE
    document.error_code = "DOCUMENT_INTERNAL_ERROR"
    document.error_message = "文档索引任务投递失败"
    document.completed_at = datetime.now(UTC)
    await session.commit()


async def mark_document_processing(
    session: AsyncSession, document_id: int
) -> tuple[KnowledgeDocument, KnowledgeBase] | None:
    document = await session.scalar(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == document_id)
        .with_for_update()
    )
    if document is None or document.status in (
        KnowledgeDocumentStatus.READY,
        KnowledgeDocumentStatus.FAILURE,
    ):
        return None
    base = await session.get_one(KnowledgeBase, document.knowledge_base_id)
    document.status = KnowledgeDocumentStatus.PROCESSING
    if document.started_at is None:
        document.started_at = datetime.now(UTC)
    await session.commit()
    return document, base


async def mark_document_ready(
    session: AsyncSession,
    document_id: int,
    chunk_count: int,
    embedding_tokens: int | None,
    embedding_dimensions: int,
) -> KnowledgeDocument | None:
    document = await session.scalar(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == document_id)
        .with_for_update()
    )
    if document is None or document.status is not KnowledgeDocumentStatus.PROCESSING:
        return None
    base = await session.scalar(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == document.knowledge_base_id)
        .with_for_update()
    )
    if base is None:
        raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", 404)
    if base.embedding_dimensions is not None and base.embedding_dimensions != embedding_dimensions:
        raise DocumentIngestionError(
            "DOCUMENT_CONFIG_ERROR", "Embedding 向量维度与知识库不一致", retryable=False
        )
    base.embedding_dimensions = embedding_dimensions
    document.status = KnowledgeDocumentStatus.READY
    document.chunk_count = chunk_count
    document.embedding_tokens = embedding_tokens
    document.error_code = None
    document.error_message = None
    document.completed_at = datetime.now(UTC)
    await session.commit()
    return document


async def mark_document_failure(
    session: AsyncSession, document_id: int, code: str, message: str
) -> KnowledgeDocument | None:
    document = await session.scalar(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == document_id)
        .with_for_update()
    )
    if document is None or document.status in (
        KnowledgeDocumentStatus.READY,
        KnowledgeDocumentStatus.FAILURE,
    ):
        return None
    document.status = KnowledgeDocumentStatus.FAILURE
    document.error_code = code
    document.error_message = message
    document.completed_at = datetime.now(UTC)
    await session.commit()
    return document


async def attach_document_task_id(
    session: AsyncSession, document_id: int, task_id: str
) -> KnowledgeDocument:
    document = await session.get_one(KnowledgeDocument, document_id)
    document.celery_task_id = task_id
    await session.commit()
    await session.refresh(document)
    return document


async def get_knowledge_document(
    session: AsyncSession, knowledge_base_id: int, document_id: int
) -> KnowledgeDocument:
    document = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "文档不存在", 404)
    return document


async def list_knowledge_documents(
    session: AsyncSession, knowledge_base_id: int, page: int, page_size: int
) -> tuple[list[KnowledgeDocument], int]:
    await get_knowledge_base(session, knowledge_base_id)
    total = await session.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == knowledge_base_id
        )
    ) or 0
    items = (
        await session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
            .order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(items), total
