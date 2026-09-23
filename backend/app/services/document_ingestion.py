"""Parse source documents and split them into deterministic character chunks."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import cast

from chromadb.api import AsyncClientAPI
from chromadb.api.types import Metadata
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from pypdf import PdfReader

from app.core.config import Settings
from app.db.chroma import knowledge_collection_name
from app.models.knowledge import KnowledgeBase, KnowledgeDocument

MAX_CHUNKS_PER_DOCUMENT = 2_000


@dataclass(frozen=True)
class ParsedSection:
    text: str
    page_number: int | None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: int
    chunk_index: int
    text: str
    page_number: int | None


class DocumentIngestionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class EmbeddingCompletion:
    vectors: list[list[float]]
    total_tokens: int | None
    dimensions: int


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[^\S\n]+", " ", text).strip()


def parse_document(path: Path, suffix: str) -> list[ParsedSection]:
    """Extract UTF-8 text or per-page PDF text without exposing parser details."""
    try:
        if suffix in {".txt", ".md"}:
            sections = [ParsedSection(_normalize_text(path.read_text(encoding="utf-8")), None)]
        elif suffix == ".pdf":
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            sections = [
                ParsedSection(_normalize_text(page.extract_text() or ""), page_number)
                for page_number, page in enumerate(reader.pages, start=1)
            ]
        else:
            raise ValueError("unsupported suffix")
    except Exception:
        raise DocumentIngestionError(
            "DOCUMENT_PARSE_ERROR", "文档无法解析或没有可提取文字", retryable=False
        ) from None
    nonempty = [section for section in sections if section.text]
    if not nonempty:
        raise DocumentIngestionError(
            "DOCUMENT_PARSE_ERROR", "文档无法解析或没有可提取文字", retryable=False
        )
    return nonempty


def _preferred_end(text: str, start: int, limit: int, overlap: int) -> int:
    minimum = start + overlap + 1
    window = text[start:limit]
    for boundary in ("\n\n", "\n", "。", "！", "？", ". "):
        position = window.rfind(boundary)
        if position >= 0:
            end = start + position + len(boundary)
            if end >= minimum:
                return end
    return limit


def split_sections(
    document_id: int,
    sections: Sequence[ParsedSection],
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("invalid chunk size or overlap")
    chunks: list[DocumentChunk] = []
    for section in sections:
        text = _normalize_text(section.text)
        start = 0
        while start < len(text):
            limit = min(start + chunk_size, len(text))
            end = limit if limit == len(text) else _preferred_end(text, start, limit, overlap)
            content = text[start:end].strip()
            if content:
                index = len(chunks)
                if index >= MAX_CHUNKS_PER_DOCUMENT:
                    raise DocumentIngestionError(
                        "DOCUMENT_TOO_MANY_CHUNKS", "文档分块数量超过上限", retryable=False
                    )
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"document:{document_id}:chunk:{index}",
                        document_id=document_id,
                        chunk_index=index,
                        text=content,
                        page_number=section.page_number,
                    )
                )
            if end == len(text):
                break
            start = end - overlap
    return chunks


async def request_embeddings(texts: Sequence[str], settings: Settings) -> EmbeddingCompletion:
    """Ask an OpenAI-compatible provider and validate every returned vector."""
    if not settings.embedding_model or settings.embedding_api_key is None:
        raise DocumentIngestionError("DOCUMENT_CONFIG_ERROR", "Embedding 配置缺失", retryable=False)
    if not texts or any(not text for text in texts):
        raise DocumentIngestionError(
            "EMBEDDING_INVALID_RESPONSE", "Embedding 输入无效", retryable=False
        )
    client = AsyncOpenAI(
        api_key=settings.embedding_api_key.get_secret_value(),
        base_url=settings.embedding_base_url,
        timeout=settings.embedding_timeout_seconds,
        max_retries=0,
    )
    vectors: list[list[float]] = []
    dimensions: int | None = None
    total_tokens = 0
    usage_known = True
    try:
        for start in range(0, len(texts), settings.embedding_batch_size):
            batch = list(texts[start : start + settings.embedding_batch_size])
            response = await client.embeddings.create(model=settings.embedding_model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise ValueError("Embedding count/index mismatch")
            for item in ordered:
                vector = item.embedding
                if not vector or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    for value in vector
                ):
                    raise ValueError("Invalid Embedding vector")
                if dimensions is None:
                    dimensions = len(vector)
                elif len(vector) != dimensions:
                    raise ValueError("Mixed Embedding dimensions")
                vectors.append([float(value) for value in vector])
            if response.usage is None or response.usage.total_tokens is None:
                usage_known = False
            else:
                total_tokens += response.usage.total_tokens
    except (AuthenticationError, PermissionDeniedError):
        raise DocumentIngestionError(
            "EMBEDDING_AUTH_ERROR", "Embedding 服务认证失败", retryable=False
        ) from None
    except (BadRequestError, NotFoundError):
        raise DocumentIngestionError(
            "EMBEDDING_REQUEST_ERROR", "Embedding 请求配置无效", retryable=False
        ) from None
    except (APIConnectionError, APITimeoutError, RateLimitError):
        raise DocumentIngestionError(
            "EMBEDDING_UNAVAILABLE", "Embedding 服务暂时不可用", retryable=True
        ) from None
    except APIStatusError as error:
        retryable = error.status_code >= 500
        raise DocumentIngestionError(
            "EMBEDDING_UNAVAILABLE" if retryable else "EMBEDDING_REQUEST_ERROR",
            "Embedding 服务暂时不可用" if retryable else "Embedding 请求配置无效",
            retryable=retryable,
        ) from None
    except (AttributeError, TypeError, ValueError, IndexError):
        raise DocumentIngestionError(
            "EMBEDDING_INVALID_RESPONSE", "Embedding 返回格式无效", retryable=False
        ) from None
    finally:
        await client.close()
    if dimensions is None:
        raise DocumentIngestionError(
            "EMBEDDING_INVALID_RESPONSE", "Embedding 返回格式无效", retryable=False
        )
    return EmbeddingCompletion(vectors, total_tokens if usage_known else None, dimensions)


async def index_document_vectors(
    client: AsyncClientAPI,
    knowledge_base: KnowledgeBase,
    document: KnowledgeDocument,
    chunks: Sequence[DocumentChunk],
    embeddings: EmbeddingCompletion,
) -> None:
    """Replace a document's vectors with stable IDs and explicit embeddings."""
    if not chunks or len(chunks) != len(embeddings.vectors):
        raise DocumentIngestionError(
            "EMBEDDING_INVALID_RESPONSE", "Embedding 返回格式无效", retryable=False
        )
    metadata: list[Metadata] = []
    for chunk in chunks:
        entry: dict[str, str | int] = {
            "knowledge_base_id": knowledge_base.id,
            "document_id": document.id,
            "chunk_index": chunk.chunk_index,
            "original_name": document.original_name,
        }
        if chunk.page_number is not None:
            entry["page_number"] = chunk.page_number
        metadata.append(entry)
    try:
        collection = await client.get_or_create_collection(
            name=knowledge_collection_name(knowledge_base.id),
            metadata={"hnsw:space": "cosine"},
        )
        await collection.delete(where={"document_id": document.id})
        await collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=cast(list[Sequence[float]], embeddings.vectors),
            documents=[chunk.text for chunk in chunks],
            metadatas=metadata,
        )
    except Exception:
        raise DocumentIngestionError(
            "CHROMA_UNAVAILABLE", "向量服务暂时不可用", retryable=True
        ) from None
