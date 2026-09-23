import pytest
from pydantic import ValidationError

from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeCitation,
    KnowledgeQuestionCreate,
    RAGModelResult,
    RetrievedChunk,
)


def test_create_name_and_description_are_trimmed() -> None:
    payload = KnowledgeBaseCreate(name="  Policies  ", description="  Team docs  ")

    assert payload.name == "Policies"
    assert payload.description == "Team docs"


@pytest.mark.parametrize("question", ["", "   ", "x" * 2_001])
def test_question_rejects_empty_or_oversized_text(question: str) -> None:
    with pytest.raises(ValidationError):
        KnowledgeQuestionCreate(question=question)


def test_citation_requires_source_coordinates() -> None:
    citation = KnowledgeCitation(
        document_id=7,
        original_name="policy.pdf",
        chunk_id="document:7:chunk:0",
        chunk_index=0,
        page_number=1,
        excerpt="Return window is 30 days.",
        distance=0.12,
    )

    assert citation.page_number == 1


def test_provider_and_retrieval_payloads_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RetrievedChunk(
            document_id=7,
            original_name="policy.pdf",
            chunk_id="document:7:chunk:0",
            chunk_index=0,
            page_number=1,
            text="Return window is 30 days.",
            distance=0.12,
            ignored=True,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        RAGModelResult(  # type: ignore[call-arg]
            answer="Thirty days.", cited_chunk_numbers=[1], refused=False, ignored=True
        )

    result = RAGModelResult(answer="Thirty days.", cited_chunk_numbers=[1], refused=False)
    assert result.cited_chunk_numbers == [1]


def test_citation_limits_are_enforced() -> None:
    with pytest.raises(ValidationError):
        KnowledgeCitation(
            document_id=7,
            original_name="policy.pdf",
            chunk_id="document:7:chunk:0",
            chunk_index=0,
            page_number=1,
            excerpt="x" * 301,
            distance=0.12,
        )
