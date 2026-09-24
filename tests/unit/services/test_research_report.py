"""Structured reports may cite only program-registered knowledge evidence."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.models.research import ResearchRun
from app.schemas.research import (
    ResearchEvidence,
    ResearchFinding,
    ResearchRecommendation,
    ResearchReport,
)
from app.services.research_agent import (
    ResearchCallError,
    build_insufficient_report,
    request_research_report,
    validate_report_sources,
)


def registered() -> list[ResearchEvidence]:
    return [
        ResearchEvidence(
            source_id="product:7:snapshot",
            source_type="product",
            product_id=7,
            text="商品快照",
        ),
        ResearchEvidence(
            source_id="kb:12:document:1:chunk:0",
            source_type="knowledge",
            knowledge_base_id=12,
            document_id=1,
            chunk_id="document:1:chunk:0",
            chunk_index=0,
            original_name="竞品.pdf",
            page_number=1,
            text="已核对的资料",
            distance=0.12,
        ),
    ]


def supported(source_ids: list[str]) -> ResearchReport:
    return ResearchReport(
        outcome="supported",
        summary="有来源的摘要",
        findings=[ResearchFinding(claim="竞品价格更低", source_ids=source_ids)],
        recommendations=[
            ResearchRecommendation(action="核对差异", reason="证据指出差异", source_ids=source_ids)
        ],
        evidence_gaps=[],
    )


def test_report_rejects_unregistered_source() -> None:
    with pytest.raises(ResearchCallError):
        validate_report_sources(supported(["kb:99:document:1:chunk:0"]), registered())


@pytest.mark.parametrize(
    "ids",
    [
        ["product:7:snapshot"],
        ["kb:12:document:1:chunk:0", "kb:12:document:1:chunk:0"],
        [],
    ],
)
def test_report_rejects_product_only_duplicate_or_empty_citations(ids: list[str]) -> None:
    if not ids:
        with pytest.raises(ValidationError):
            supported(ids)
        return
    with pytest.raises(ResearchCallError):
        validate_report_sources(supported(ids), registered())


def test_report_fills_citation_details_from_registry() -> None:
    report = validate_report_sources(
        supported(["product:7:snapshot", "kb:12:document:1:chunk:0"]),
        registered(),
    )
    citation = cast(dict[str, Any], report)["findings"][0]["citations"][1]
    assert citation["original_name"] == "竞品.pdf"
    assert citation["page_number"] == 1
    assert citation["excerpt"] == "已核对的资料"


def test_insufficient_report_is_deterministic() -> None:
    result = build_insufficient_report(registered()[:1])
    assert result["outcome"] == "insufficient_evidence"
    assert result["findings"] == []
    assert result["recommendations"] == []
    assert result["evidence_gaps"]


def test_report_schema_limits_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchReport.model_validate(
            {
                "outcome": "supported",
                "summary": "s",
                "findings": [],
                "recommendations": [],
                "evidence_gaps": [],
                "raw_model_text": "not allowed",
            }
        )
    with pytest.raises(ValidationError):
        ResearchReport.model_validate(
            {
                "outcome": "supported",
                "summary": "s",
                "findings": [
                    {"claim": "Finding", "source_ids": ["kb:12:document:1:chunk:0"]}
                ],
                "recommendations": [],
                "evidence_gaps": ["x" * 501],
            }
        )


@pytest.mark.asyncio
async def test_report_model_uses_json_mode_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    content = json.dumps(supported(["kb:12:document:1:chunk:0"]).model_dump())
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4),
        )
    )
    close = AsyncMock()
    factory = Mock(
        return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            close=close,
        )
    )
    monkeypatch.setattr("app.services.research_agent.AsyncOpenAI", factory)
    run = cast(
        ResearchRun,
        SimpleNamespace(
            goal="Compare",
            product_snapshot={"title": "Untrusted"},
            evidence=[item.model_dump(mode="json") for item in registered()],
            steps=[],
        ),
    )
    completion = await request_research_report(
        run, Settings(llm_model="model", llm_api_key=SecretStr("private"))
    )
    assert completion.prompt_tokens == 8
    assert completion.completion_tokens == 4
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}
    assert factory.call_args.kwargs["max_retries"] == 0
    assert "不可信" in create.call_args.kwargs["messages"][0]["content"]
    close.assert_awaited_once()
