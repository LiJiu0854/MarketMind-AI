"""Deterministic RAG quality metrics without live model calls."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from scripts.evaluate_rag import main
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.knowledge import KnowledgeBase, KnowledgeQueryStatus
from app.schemas.knowledge import KnowledgeCitation, RetrievedChunk
from app.services.document_ingestion import EmbeddingCompletion
from app.services.rag import RAGCallError, RAGCompletion
from app.services.rag_evaluation import (
    EvaluationCase,
    EvaluationReport,
    evaluate_case,
    load_evaluation_cases,
    reciprocal_rank,
    run_evaluation,
    summarize_evaluations,
)


def chunk(document_id: int, index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=document_id,
        original_name=f"source-{document_id}.txt",
        chunk_id=f"document:{document_id}:chunk:{index}",
        chunk_index=index,
        text="grounded evidence",
        distance=0.1,
    )


def completion(source: RetrievedChunk | None, *, refused: bool = False) -> RAGCompletion:
    citations = [] if source is None else [
        KnowledgeCitation(
            document_id=source.document_id,
            original_name=source.original_name,
            chunk_id=source.chunk_id,
            chunk_index=source.chunk_index,
            page_number=source.page_number,
            excerpt=source.text,
            distance=source.distance,
        )
    ]
    return RAGCompletion(
        "answer",
        KnowledgeQueryStatus.REFUSED if refused else KnowledgeQueryStatus.SUCCESS,
        citations,
        None,
        None,
        None,
        None,
    )


def test_reciprocal_rank_uses_first_relevant_document() -> None:
    assert reciprocal_rank([8, 3, 5], {3, 9}) == 0.5
    assert reciprocal_rank([8, 3, 5], {9}) == 0.0


def test_hit_at_k_and_citation_validity() -> None:
    source = chunk(3)
    case = EvaluationCase(question="why?", relevant_document_ids={3}, should_refuse=False)

    result = evaluate_case(case, [chunk(8), source], completion(source), 12.0)
    assert (result.hit_at_k, result.reciprocal_rank, result.citation_valid) == (1, 0.5, 1)

    fabricated = evaluate_case(case, [chunk(8), source], completion(chunk(9)), 12.0)
    assert fabricated.citation_valid == 0
    assert evaluate_case(case, [source], completion(None), 12.0).citation_valid == 0


def test_refusal_accuracy_and_failure_metrics() -> None:
    case = EvaluationCase(question="unknown?", should_refuse=True)
    correct = evaluate_case(case, [], completion(None, refused=True), 5.0)
    wrong = evaluate_case(case, [chunk(4)], completion(chunk(4)), 7.0)
    failed = evaluate_case(case, [], None, 9.0, error_code="RAG_PROVIDER_UNAVAILABLE")
    assert correct.refusal_correct == 1
    assert correct.citation_valid == 1
    assert wrong.refusal_correct == 0
    assert failed.refusal_correct == 0
    assert failed.citation_valid == 0

    report = summarize_evaluations([correct, wrong, failed])
    assert report.case_count == 3
    assert report.failure_count == 1
    assert report.refusal_accuracy == pytest.approx(1 / 3)
    assert report.average_latency_ms == 7


@pytest.mark.parametrize("bad_line", ["not-json", "{}", '{"question":""}'])
def test_invalid_jsonl_reports_line_number_without_content(
    tmp_path: Path, bad_line: str
) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"question": "ok", "should_refuse": True}) + "\n" + bad_line)

    with pytest.raises(ValueError, match="第 2 行") as failure:
        load_evaluation_cases(path)
    assert bad_line not in str(failure.value)


def test_jsonl_rejects_empty_file_and_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="不能为空"):
        load_evaluation_cases(path)
    path.write_text(
        '{"question":"如何退货？","should_refuse":false,"relevant_document_ids":[3]}\n',
        encoding="utf-8",
    )
    assert load_evaluation_cases(path)[0].relevant_document_ids == {3}


@pytest.mark.asyncio
async def test_runner_reuses_production_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import rag_evaluation

    settings = Settings(
        embedding_provider="test",
        embedding_base_url="https://provider.invalid/v1",
        embedding_model="embedding-test",
        embedding_api_key=SecretStr("test-only"),
    )
    base = KnowledgeBase(
        id=42,
        embedding_provider=settings.embedding_provider,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
        embedding_dimensions=2,
    )
    session = AsyncMock(spec=AsyncSession)
    embedding = AsyncMock(return_value=EmbeddingCompletion([[0.1, 0.2]], 4, 2))
    retrieve = AsyncMock(return_value=[chunk(3)])
    answer = AsyncMock(return_value=completion(chunk(3)))
    create_chroma = AsyncMock(return_value=SimpleNamespace())
    close_chroma = AsyncMock()
    monkeypatch.setattr(rag_evaluation, "request_embeddings", embedding)
    monkeypatch.setattr(rag_evaluation, "retrieve_chunks", retrieve)
    monkeypatch.setattr(rag_evaluation, "request_rag_answer", answer)
    monkeypatch.setattr(rag_evaluation, "create_chroma_client", create_chroma)
    monkeypatch.setattr(rag_evaluation, "close_chroma_client", close_chroma)

    report = await run_evaluation(
        cast(AsyncSession, session),
        base,
        [EvaluationCase(question="why?", relevant_document_ids={3}, should_refuse=False)],
        settings,
    )

    assert report.case_count == 1
    assert report.hit_at_k == 1
    assert report.mrr == 1
    assert report.citation_valid_rate == 1
    embedding.assert_awaited_once()
    retrieve.assert_awaited_once()
    answer.assert_awaited_once()
    close_chroma.assert_awaited_once()
    assert session.rollback.await_count >= 1


@pytest.mark.asyncio
async def test_runner_counts_failure_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import rag_evaluation

    settings = Settings(
        embedding_provider="test",
        embedding_base_url="https://provider.invalid/v1",
        embedding_model="embedding-test",
    )
    base = KnowledgeBase(
        id=42,
        embedding_provider=settings.embedding_provider,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
    )
    session = AsyncMock(spec=AsyncSession)
    embedding = AsyncMock(
        side_effect=[
            RAGCallError("RAG_PROVIDER_UNAVAILABLE", "unavailable", status_code=503),
            EmbeddingCompletion([[0.1]], None, 1),
        ]
    )
    monkeypatch.setattr(rag_evaluation, "request_embeddings", embedding)
    monkeypatch.setattr(
        rag_evaluation, "create_chroma_client", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(rag_evaluation, "close_chroma_client", AsyncMock())
    monkeypatch.setattr(rag_evaluation, "retrieve_chunks", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        rag_evaluation, "request_rag_answer", AsyncMock(return_value=completion(None, refused=True))
    )

    report = await run_evaluation(
        cast(AsyncSession, session),
        base,
        [
            EvaluationCase(question="first", should_refuse=True),
            EvaluationCase(question="second", should_refuse=True),
        ],
        settings,
    )
    assert report.case_count == 2
    assert report.failure_count == 1
    assert report.cases[0].error_code == "RAG_PROVIDER_UNAVAILABLE"
    assert report.cases[1].refusal_correct == 1


def test_cli_requires_live_before_loading_settings_or_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import evaluate_rag

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("live path was reached")

    monkeypatch.setattr(evaluate_rag, "Settings", forbidden)
    assert main([
        "--knowledge-base-id", "42", "--cases", str(tmp_path / "missing.jsonl"),
        "--output", str(tmp_path / "report.json"),
    ]) != 0


def test_cli_writes_utf8_report_to_requested_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import evaluate_rag

    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"question":"如何退货？","should_refuse":true}\n', encoding="utf-8")
    output = tmp_path / "report.json"
    async def fake_run(base_id: int, entries: list[EvaluationCase]) -> EvaluationReport:
        assert base_id == 42
        return summarize_evaluations([
            evaluate_case(entries[0], [], completion(None, refused=True), 1.0)
        ])

    monkeypatch.setattr(evaluate_rag, "run_live_evaluation", fake_run)
    assert main([
        "--knowledge-base-id", "42", "--cases", str(cases),
        "--output", str(output), "--live",
    ]) == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["cases"][0]["question"] == "如何退货？"


def test_cli_never_overwrites_its_case_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import evaluate_rag

    cases = tmp_path / "cases.jsonl"
    original = '{"question":"keep me","should_refuse":true}\n'
    cases.write_text(original, encoding="utf-8")
    async def fake_run(base_id: int, entries: list[EvaluationCase]) -> EvaluationReport:
        return summarize_evaluations([
            evaluate_case(entries[0], [], completion(None, refused=True), 1.0)
        ])

    monkeypatch.setattr(evaluate_rag, "run_live_evaluation", fake_run)
    assert main([
        "--knowledge-base-id", "42", "--cases", str(cases),
        "--output", str(cases), "--live",
    ]) != 0
    assert cases.read_text(encoding="utf-8") == original
