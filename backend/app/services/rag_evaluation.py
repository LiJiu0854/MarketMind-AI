"""Deterministic RAG metrics and a guarded live-evaluation runner."""

from collections.abc import Sequence
from pathlib import Path
from statistics import mean
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.chroma import close_chroma_client, create_chroma_client
from app.models.knowledge import KnowledgeBase, KnowledgeQueryStatus
from app.schemas.knowledge import RetrievedChunk
from app.services.document_ingestion import DocumentIngestionError, request_embeddings
from app.services.rag import RAGCallError, RAGCompletion, request_rag_answer, retrieve_chunks


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    relevant_document_ids: set[int] = Field(default_factory=set)
    should_refuse: bool


class CaseEvaluation(BaseModel):
    question: str
    hit_at_k: float = Field(ge=0, le=1)
    reciprocal_rank: float = Field(ge=0, le=1)
    citation_valid: float = Field(ge=0, le=1)
    refusal_correct: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    error_code: str | None = None


class EvaluationReport(BaseModel):
    case_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    hit_at_k: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    citation_valid_rate: float = Field(ge=0, le=1)
    refusal_accuracy: float = Field(ge=0, le=1)
    average_latency_ms: float = Field(ge=0)
    cases: list[CaseEvaluation]


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    """Read one strict JSON object per line, without echoing bad case content."""
    cases: list[EvaluationCase] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            cases.append(EvaluationCase.model_validate_json(line, strict=True))
        except ValidationError:
            raise ValueError(f"评估用例第 {number} 行无效") from None
    if not cases:
        raise ValueError("评估用例不能为空")
    return cases


def reciprocal_rank(retrieved_document_ids: Sequence[int], relevant: set[int]) -> float:
    return next(
        (1 / rank for rank, document_id in enumerate(retrieved_document_ids, start=1)
         if document_id in relevant),
        0.0,
    )


def evaluate_case(
    case: EvaluationCase,
    chunks: Sequence[RetrievedChunk],
    completion: RAGCompletion | None,
    latency_ms: float,
    error_code: str | None = None,
) -> CaseEvaluation:
    retrieved_ids = [chunk.document_id for chunk in chunks]
    if completion is None:
        citation_valid = refusal_correct = 0.0
    else:
        refused = completion.status == KnowledgeQueryStatus.REFUSED
        refusal_correct = float(refused == case.should_refuse)
        sources = {
            (
                chunk.document_id,
                chunk.original_name,
                chunk.chunk_id,
                chunk.chunk_index,
                chunk.page_number,
                chunk.text[:300],
                chunk.distance,
            )
            for chunk in chunks
        }
        citation_valid = float(
            (refused and not completion.citations)
            or (
                not refused
                and bool(completion.citations)
                and all(
                    (
                        citation.document_id,
                        citation.original_name,
                        citation.chunk_id,
                        citation.chunk_index,
                        citation.page_number,
                        citation.excerpt,
                        citation.distance,
                    ) in sources
                    for citation in completion.citations
                )
            )
        )
    return CaseEvaluation(
        question=case.question,
        hit_at_k=float(bool(set(retrieved_ids) & case.relevant_document_ids)),
        reciprocal_rank=reciprocal_rank(retrieved_ids, case.relevant_document_ids),
        citation_valid=citation_valid,
        refusal_correct=refusal_correct,
        latency_ms=latency_ms,
        error_code=error_code,
    )


def summarize_evaluations(cases: Sequence[CaseEvaluation]) -> EvaluationReport:
    if not cases:
        raise ValueError("评估结果不能为空")
    return EvaluationReport(
        case_count=len(cases),
        failure_count=sum(case.error_code is not None for case in cases),
        hit_at_k=mean(case.hit_at_k for case in cases),
        mrr=mean(case.reciprocal_rank for case in cases),
        citation_valid_rate=mean(case.citation_valid for case in cases),
        refusal_accuracy=mean(case.refusal_correct for case in cases),
        average_latency_ms=mean(case.latency_ms for case in cases),
        cases=list(cases),
    )


async def run_evaluation(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    cases: Sequence[EvaluationCase],
    settings: Settings,
) -> EvaluationReport:
    """Use production Embedding/retrieval/answer boundaries and isolate case failures."""
    results: list[CaseEvaluation] = []
    for case in cases:
        started = perf_counter()
        chunks: list[RetrievedChunk] = []
        completion: RAGCompletion | None = None
        error_code: str | None = None
        try:
            if (
                knowledge_base.embedding_provider != settings.embedding_provider
                or knowledge_base.embedding_base_url != settings.embedding_base_url
                or knowledge_base.embedding_model != settings.embedding_model
            ):
                raise RAGCallError("RAG_CONFIG_MISSING", "Embedding 配置不匹配", status_code=503)
            embedding = await request_embeddings([case.question], settings)
            if (
                knowledge_base.embedding_dimensions is not None
                and knowledge_base.embedding_dimensions != embedding.dimensions
            ):
                raise RAGCallError("RAG_CONFIG_MISSING", "Embedding 维度不匹配", status_code=503)
            client = await create_chroma_client(settings)
            try:
                chunks = await retrieve_chunks(
                    session,
                    client,
                    knowledge_base,
                    embedding.vectors[0],
                    settings.rag_top_k,
                    settings.rag_max_distance,
                )
            finally:
                await session.rollback()
                await close_chroma_client(client)
            completion = await request_rag_answer(case.question, chunks, settings)
        except RAGCallError as error:
            error_code = error.code
        except DocumentIngestionError as error:
            error_code = error.code
        except Exception:
            error_code = "EVALUATION_ERROR"
        finally:
            await session.rollback()
        results.append(
            evaluate_case(case, chunks, completion, (perf_counter() - started) * 1_000, error_code)
        )
    return summarize_evaluations(results)
