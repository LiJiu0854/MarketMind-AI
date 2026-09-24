"""Only registered, selected, bounded sources can enter research evidence."""

from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.research import ResearchRun
from app.schemas.research import ResearchEvidence
from app.services.research_tools import (
    read_product_snapshot,
    register_evidence,
    search_knowledge,
)


def product_evidence() -> ResearchEvidence:
    return ResearchEvidence(
        source_id="product:7:snapshot",
        source_type="product",
        product_id=7,
        text="商品快照",
    )


def test_read_product_uses_only_saved_snapshot() -> None:
    run = cast(
        ResearchRun,
        SimpleNamespace(
            product_id=7,
            product_snapshot={
                "sku": "A",
                "title": "Saved",
                "description": "Description",
                "bullet_points": ["Point"],
                "brand": "Brand",
                "category": "Category",
                "price": "12.00",
                "currency": "CNY",
                "is_active": True,
                "unknown": "do not expose",
            },
        ),
    )
    result = read_product_snapshot(run)
    assert result.evidence[0].source_id == "product:7:snapshot"
    assert "Saved" in result.evidence[0].text
    assert "unknown" not in result.evidence[0].text
    assert result.embedding_tokens == 0


def test_register_evidence_deduplicates_and_caps_count() -> None:
    item = product_evidence()
    existing = [item]
    result = register_evidence(existing, [item, item], limit=2)
    assert [e.source_id for e in result] == ["product:7:snapshot"]
    assert result is not existing
    second = ResearchEvidence(
        source_id="kb:3:document:8:chunk:0",
        source_type="knowledge",
        knowledge_base_id=3,
        document_id=8,
        chunk_id="document:8:chunk:0",
        chunk_index=0,
        original_name="real.txt",
        text="a" * 2000,
        distance=0.1,
    )
    assert len(second.text) == 1000
    assert len(register_evidence(result, [second, second], limit=2)) == 2
    assert len(existing) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"source_id": "x", "source_type": "product", "text": "x"},
        {"source_id": "x", "source_type": "knowledge", "product_id": 7, "text": "x"},
        {
            "source_id": "x",
            "source_type": "product",
            "product_id": 7,
            "knowledge_base_id": 3,
            "text": "x",
        },
    ],
)
def test_evidence_rejects_cross_type_coordinates(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchEvidence.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   ", "x" * 301])
async def test_invalid_query_never_reaches_database(query: str) -> None:
    run = cast(ResearchRun, SimpleNamespace(knowledge_base_ids=[3]))
    with pytest.raises(AppError):
        await search_knowledge(cast(AsyncSession, None), run, 3, query, Settings())


@pytest.mark.asyncio
async def test_unselected_base_never_reaches_database() -> None:
    run = cast(ResearchRun, SimpleNamespace(knowledge_base_ids=[3]))
    with pytest.raises(AppError):
        await search_knowledge(cast(AsyncSession, None), run, 4, "price", Settings())
