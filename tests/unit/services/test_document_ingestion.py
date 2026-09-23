"""Parsing, character chunking, and vector ingestion boundaries."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from chromadb.api import AsyncClientAPI
from pydantic import SecretStr

from app.core.config import Settings
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.services.document_ingestion import (
    DocumentChunk,
    DocumentIngestionError,
    EmbeddingCompletion,
    ParsedSection,
    index_document_vectors,
    parse_document,
    request_embeddings,
    split_sections,
)


def test_parse_txt_normalizes_newlines_and_preserves_text_source(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"first\r\nsecond\rthird")

    sections = parse_document(path, ".txt")

    assert sections == [ParsedSection("first\nsecond\nthird", None)]


def test_parse_markdown_requires_utf8(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_bytes(b"\xff")

    with pytest.raises(DocumentIngestionError) as failure:
        parse_document(path, ".md")
    assert failure.value.code == "DOCUMENT_PARSE_ERROR"
    assert not failure.value.retryable


def test_parse_pdf_returns_one_section_per_nonempty_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.services.document_ingestion.PdfReader",
        lambda path: SimpleNamespace(
            is_encrypted=False,
            pages=[
                SimpleNamespace(extract_text=lambda: "Page one"),
                SimpleNamespace(extract_text=lambda: "   "),
                SimpleNamespace(extract_text=lambda: "Page three"),
            ],
        ),
    )

    assert parse_document(tmp_path / "fake.pdf", ".pdf") == [
        ParsedSection("Page one", 1),
        ParsedSection("Page three", 3),
    ]


@pytest.mark.parametrize("encrypted", [True, False])
def test_encrypted_or_malformed_pdf_maps_to_safe_parse_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, encrypted: bool
) -> None:
    def reader(path: Path) -> object:
        if encrypted:
            return SimpleNamespace(is_encrypted=True, pages=[])
        raise ValueError("private file path and parser detail")

    monkeypatch.setattr("app.services.document_ingestion.PdfReader", reader)
    with pytest.raises(DocumentIngestionError) as failure:
        parse_document(tmp_path / "bad.pdf", ".pdf")
    assert failure.value.code == "DOCUMENT_PARSE_ERROR"
    assert "private" not in failure.value.message


def test_scanned_pdf_without_text_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.services.document_ingestion.PdfReader",
        lambda path: SimpleNamespace(
            is_encrypted=False,
            pages=[SimpleNamespace(extract_text=lambda: "")],
        ),
    )
    with pytest.raises(DocumentIngestionError) as failure:
        parse_document(tmp_path / "scanned.pdf", ".pdf")
    assert failure.value.code == "DOCUMENT_PARSE_ERROR"


def test_split_prefers_paragraph_or_sentence_boundary() -> None:
    text = "First complete sentence.\n\nSecond complete sentence. More text follows."
    chunks = split_sections(7, [ParsedSection(text, None)], chunk_size=40, overlap=5)
    assert chunks[0].text == "First complete sentence."
    assert chunks[0].chunk_id == "document:7:chunk:0"


def test_split_uses_exact_overlap_without_infinite_loop() -> None:
    text = "abcdefghijklmnopqrstuvwxyz0123456789"
    chunks = split_sections(7, [ParsedSection(text, None)], chunk_size=20, overlap=5)
    assert len(chunks) == 3
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.text[-5:] == current.text[:5]


def test_pdf_chunks_never_cross_page_boundary() -> None:
    chunks = split_sections(
        7,
        [ParsedSection("A" * 25, 1), ParsedSection("B" * 25, 2)],
        chunk_size=20,
        overlap=5,
    )
    assert [chunk.page_number for chunk in chunks] == [1, 1, 2, 2]
    assert [chunk.chunk_index for chunk in chunks] == list(range(4))


def test_more_than_2000_chunks_is_rejected_before_embedding() -> None:
    with pytest.raises(DocumentIngestionError) as failure:
        split_sections(7, [ParsedSection("x" * 2_001, None)], chunk_size=1, overlap=0)
    assert failure.value.code == "DOCUMENT_TOO_MANY_CHUNKS"


def embedding_settings(batch_size: int = 2) -> Settings:
    return Settings(
        embedding_model="test-embedding",
        embedding_api_key=SecretStr("test-only-key"),
        embedding_batch_size=batch_size,
    )


def embedding_response(vectors: list[list[float]], tokens: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=vector) for index, vector in enumerate(vectors)
        ],
        usage=SimpleNamespace(total_tokens=tokens),
    )


@pytest.mark.asyncio
async def test_embedding_batches_preserve_provider_index_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = embedding_response([[1.0, 0.0], [0.0, 1.0]], 5)
    first.data.reverse()
    client = SimpleNamespace(
        close=AsyncMock(),
        embeddings=SimpleNamespace(
            create=AsyncMock(side_effect=[first, embedding_response([[0.5, 0.5]], 2)])
        ),
    )
    monkeypatch.setattr("app.services.document_ingestion.AsyncOpenAI", lambda **kwargs: client)

    result = await request_embeddings(["a", "b", "c"], embedding_settings())

    assert result.vectors == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    assert result.total_tokens == 7
    assert result.dimensions == 2
    assert client.embeddings.create.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0, 0.0]],
        [[1.0, 0.0], [1.0]],
        [[float("nan"), 0.0], [0.0, 1.0]],
        [[float("inf"), 0.0], [0.0, 1.0]],
    ],
)
async def test_invalid_embedding_shape_or_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, vectors: list[list[float]]
) -> None:
    client = SimpleNamespace(
        close=AsyncMock(),
        embeddings=SimpleNamespace(create=AsyncMock(return_value=embedding_response(vectors))),
    )
    monkeypatch.setattr("app.services.document_ingestion.AsyncOpenAI", lambda **kwargs: client)

    with pytest.raises(DocumentIngestionError) as failure:
        await request_embeddings(["a", "b"], embedding_settings())
    assert failure.value.code == "EMBEDDING_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_index_deletes_document_then_upserts_deterministic_ids() -> None:
    collection = SimpleNamespace(delete=AsyncMock(), upsert=AsyncMock())
    client = SimpleNamespace(get_or_create_collection=AsyncMock(return_value=collection))
    base = KnowledgeBase(id=42)
    document = KnowledgeDocument(id=7, original_name="policy.pdf")
    chunks = [DocumentChunk("document:7:chunk:0", 7, 0, "Returns in 30 days", 1)]
    embeddings = EmbeddingCompletion([[0.1, 0.2]], 3, 2)

    await index_document_vectors(cast(AsyncClientAPI, client), base, document, chunks, embeddings)
    await index_document_vectors(cast(AsyncClientAPI, client), base, document, chunks, embeddings)

    assert client.get_or_create_collection.await_count == 2
    assert client.get_or_create_collection.call_args.kwargs["metadata"] == {"hnsw:space": "cosine"}
    assert collection.delete.await_count == 2
    collection.delete.assert_awaited_with(where={"document_id": 7})
    assert collection.upsert.await_count == 2
    assert collection.upsert.call_args.kwargs["ids"] == ["document:7:chunk:0"]
    assert collection.upsert.call_args.kwargs["embeddings"] == [[0.1, 0.2]]
    assert collection.upsert.call_args.kwargs["metadatas"][0]["page_number"] == 1


@pytest.mark.asyncio
async def test_retry_after_partial_chroma_write_converges() -> None:
    collection = SimpleNamespace(
        delete=AsyncMock(),
        upsert=AsyncMock(side_effect=[RuntimeError("temporary outage"), None]),
    )
    client = cast(
        AsyncClientAPI,
        SimpleNamespace(get_or_create_collection=AsyncMock(return_value=collection)),
    )
    base = KnowledgeBase(id=42)
    document = KnowledgeDocument(id=7, original_name="notes.txt")
    chunks = [DocumentChunk("document:7:chunk:0", 7, 0, "hello", None)]
    embeddings = EmbeddingCompletion([[0.1, 0.2]], 3, 2)

    with pytest.raises(DocumentIngestionError) as failure:
        await index_document_vectors(client, base, document, chunks, embeddings)
    assert failure.value.code == "CHROMA_UNAVAILABLE"
    assert failure.value.retryable

    await index_document_vectors(client, base, document, chunks, embeddings)
    assert collection.delete.await_count == 2
    assert collection.upsert.call_args.kwargs["ids"] == ["document:7:chunk:0"]
