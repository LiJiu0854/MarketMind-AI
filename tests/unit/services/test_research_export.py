"""The export keeps persisted evidence visible and untrusted text inert."""

from io import BytesIO

from openpyxl import load_workbook  # type: ignore[import-untyped]

from app.models.research import ResearchRun, ResearchStatus
from app.models.research_review import ResearchReportReview, ResearchReviewDecision
from app.services.research_export import export_research_report


def sample_run() -> tuple[ResearchRun, ResearchReportReview]:
    source_id = "kb:2:document:3:chunk:0"
    run = ResearchRun(
        id=7,
        product_id=1,
        requested_by_id=4,
        goal="竞品比较",
        knowledge_base_ids=[2],
        product_snapshot={"sku": "SKU-1", "title": "商品标题"},
        status=ResearchStatus.SUCCESS,
        provider="test",
        model="research-model",
        prompt_version="research-v1",
        steps=[],
        evidence=[
            {
                "source_id": source_id,
                "source_type": "knowledge",
                "text": "已验证摘录",
                "knowledge_base_id": 2,
                "document_id": 3,
                "chunk_id": "document:3:chunk:0",
                "chunk_index": 0,
                "page_number": 2,
                "original_name": "资料.txt",
                "distance": 0.2,
            }
        ],
        report={
            "outcome": "supported",
            "summary": "报告摘要",
            "findings": [{"claim": "价格有优势", "source_ids": [source_id]}],
            "recommendations": [
                {"action": "保留定价", "reason": "竞争力", "source_ids": [source_id]}
            ],
            "evidence_gaps": [],
        },
    )
    review = ResearchReportReview(
        id=9,
        run_id=7,
        reviewed_by_id=5,
        decision=ResearchReviewDecision.APPROVED,
        comment=None,
    )
    return run, review


def test_export_contains_report_and_registered_sources() -> None:
    run, review = sample_run()
    workbook = load_workbook(BytesIO(export_research_report(run, review)))
    assert workbook.sheetnames == ["概览", "发现与建议", "证据"]
    all_values = [cell.value for sheet in workbook for row in sheet for cell in row]
    for expected in (
        "SKU-1",
        "商品标题",
        "报告摘要",
        "价格有优势",
        "保留定价",
        "kb:2:document:3:chunk:0",
        "资料.txt",
        "已验证摘录",
        "结论基于已上传且经程序核验的资料，仍需业务复核",
    ):
        assert expected in all_values
    assert 7 in all_values
    assert 5 in all_values


def test_export_never_writes_untrusted_formula() -> None:
    run, review = sample_run()
    run.product_snapshot["title"] = "=1+1"
    assert run.report is not None
    run.report["summary"] = " +cmd"
    run.report["findings"] = [{"claim": "-2", "source_ids": ["kb:2:document:3:chunk:0"]}]
    run.evidence[0]["original_name"] = "@SUM(1)"
    run.evidence[0]["text"] = '  =HYPERLINK("https://example.invalid")'
    workbook = load_workbook(BytesIO(export_research_report(run, review)))
    untrusted_cells = [
        cell
        for sheet in workbook
        for row in sheet
        for cell in row
        if isinstance(cell.value, str)
        and any(marker in cell.value for marker in ("=1+1", "+cmd", "-2", "@SUM(1)", "=HYPERLINK"))
    ]
    assert len(untrusted_cells) == 5
    assert all(cell.data_type != "f" and cell.hyperlink is None for cell in untrusted_cells)
