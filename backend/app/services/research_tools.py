"""两个受控只读研究工具及来源登记。"""

import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.chroma import close_chroma_client, create_chroma_client
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentStatus
from app.models.research import ResearchRun
from app.schemas.research import ResearchEvidence, ToolResult
from app.schemas.semantic_review import ProductSnapshot
from app.services.document_ingestion import DocumentIngestionError, request_embeddings
from app.services.rag import RAGCallError, retrieve_chunks


def read_product_snapshot(run: ResearchRun) -> ToolResult:
    """只读创建时的商品快照，不重新加载当前商品。"""
    allowed = ProductSnapshot.model_fields
    snapshot = ProductSnapshot.model_validate(
        {key: value for key, value in run.product_snapshot.items() if key in allowed}
    )
    text = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
    evidence = ResearchEvidence(
        source_id=f"product:{run.product_id}:snapshot",
        source_type="product",
        product_id=run.product_id,
        text=text,
    )
    return ToolResult(evidence=[evidence], embedding_tokens=0)


def register_evidence(
    existing: Sequence[ResearchEvidence],
    incoming: Sequence[ResearchEvidence],
    limit: int,
) -> list[ResearchEvidence]:
    """按程序来源 ID 去重；返回新列表供 JSON 字段重新赋值。"""
    result = list(existing)
    seen = {item.source_id for item in result}
    for item in incoming:
        if len(result) >= limit:
            break
        if item.source_id not in seen:
            result.append(item)
            seen.add(item.source_id)
    return result


async def search_knowledge(
    session: AsyncSession,
    run: ResearchRun,
    base_id: int,
    query: str,
    settings: Settings,
) -> ToolResult:
    """先校验选定范围与配置，再检索并用 MySQL 复核每个来源。"""
    if base_id not in run.knowledge_base_ids:
        raise AppError("RESEARCH_BASE_NOT_SELECTED", "知识库不在本次研究范围", 422)
    query = query.strip()
    if not query or len(query) > 300:
        raise AppError("RESEARCH_QUERY_INVALID", "检索词长度无效", 422)
    try:
        base = await session.get(KnowledgeBase, base_id)
        if base is None:
            raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", 404)
        if (
            base.embedding_provider != settings.embedding_provider
            or base.embedding_base_url != settings.embedding_base_url
            or base.embedding_model != settings.embedding_model
            or not settings.embedding_model
            or settings.embedding_api_key is None
        ):
            raise AppError("RESEARCH_EMBEDDING_CONFIG_MISMATCH", "Embedding 配置不一致", 503)
        ready_id = await session.scalar(
            select(KnowledgeDocument.id)
            .where(
                KnowledgeDocument.knowledge_base_id == base_id,
                KnowledgeDocument.status == KnowledgeDocumentStatus.READY,
            )
            .limit(1)
        )
        if ready_id is None:
            raise AppError("RESEARCH_KNOWLEDGE_NOT_READY", "知识库没有已就绪文档", 409)
        session.expunge(base)
    finally:
        await session.rollback()
    try:
        embedding = await request_embeddings([query], settings)
    except DocumentIngestionError as error:
        raise AppError(
            "RESEARCH_EMBEDDING_UNAVAILABLE"
            if error.retryable
            else "RESEARCH_EMBEDDING_CONFIG_ERROR",
            "Embedding 服务暂时不可用"
            if error.retryable
            else "Embedding 配置或响应无效",
            503,
        ) from None
    if base.embedding_dimensions is not None and base.embedding_dimensions != embedding.dimensions:
        raise AppError("RESEARCH_EMBEDDING_CONFIG_MISMATCH", "Embedding 维度不一致", 503)
    try:
        chroma = await create_chroma_client(settings)
    except Exception:
        raise AppError("RESEARCH_SEARCH_UNAVAILABLE", "向量检索服务不可用", 503) from None
    try:
        chunks = await retrieve_chunks(
            session, chroma, base, embedding.vectors[0], 3, settings.rag_max_distance
        )
        if not chunks:
            return ToolResult(evidence=[], embedding_tokens=embedding.total_tokens)
        documents = list(
            await session.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id.in_({chunk.document_id for chunk in chunks}),
                    KnowledgeDocument.knowledge_base_id == base_id,
                    KnowledgeDocument.status == KnowledgeDocumentStatus.READY,
                )
            )
        )
        verified = {document.id: document for document in documents}
        evidence = [
            ResearchEvidence(
                source_id=(f"kb:{base_id}:document:{chunk.document_id}:chunk:{chunk.chunk_index}"),
                source_type="knowledge",
                knowledge_base_id=base_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                original_name=verified[chunk.document_id].original_name,
                text=chunk.text,
                distance=chunk.distance,
            )
            for chunk in chunks
            if chunk.document_id in verified
        ]
        return ToolResult(evidence=evidence, embedding_tokens=embedding.total_tokens)
    except RAGCallError as error:
        raise AppError(
            "RESEARCH_SEARCH_INVALID_RESPONSE"
            if error.code == "RAG_INVALID_RESPONSE"
            else "RESEARCH_SEARCH_UNAVAILABLE",
            "向量检索结果无效"
            if error.code == "RAG_INVALID_RESPONSE"
            else "向量检索服务不可用",
            error.status_code,
        ) from None
    finally:
        await session.rollback()
        await close_chroma_client(chroma)
