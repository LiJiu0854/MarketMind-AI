"""Review API permissions, product scope and history display."""

from collections.abc import AsyncIterator
from copy import deepcopy
from io import BytesIO

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.dependencies import get_db_session
from app.main import create_app
from app.models.research import ResearchRun
from app.models.user import Role
from app.schemas.research import ResearchCreate
from app.services.research import create_research_run
from tests.api.test_research import actor, configured_settings, headers
from tests.integration.db.test_research_review import prepared_run, supported_report


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "research-test-secret-at-least-32-bytes")


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app(configured_settings())

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as value:
        yield value


@pytest.mark.asyncio
async def test_admin_reviews_operator_and_analyst_cannot(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, product_id, run_id = await prepared_run(session, "review-api-role")
    admin = await actor(session, "review-admin", Role.ADMIN)
    operator = await actor(session, "review-operator", Role.OPERATOR)
    analyst = await actor(session, "review-analyst", Role.ANALYST)
    path = f"/api/v1/products/{product_id}/research-runs/{run_id}/review"
    body = {"decision": "approved"}
    assert (await client.post(path, json=body)).status_code == 401
    for denied in (operator, analyst):
        assert (await client.post(path, json=body, headers=headers(denied))).status_code == 403
    admin_headers = headers(admin)
    first = await client.post(path, json=body, headers=admin_headers)
    assert first.status_code == 200, first.text
    again = await client.post(path, json=body, headers=admin_headers)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
async def test_review_requires_product_scope(client: AsyncClient, session: AsyncSession) -> None:
    _, product_id, run_id = await prepared_run(session, "review-api-scope")
    admin = await actor(session, "review-scope-admin", Role.ADMIN)
    response = await client.post(
        f"/api/v1/products/{product_id + 999}/research-runs/{run_id}/review",
        json={"decision": "approved"},
        headers=headers(admin),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_history_reports_review_state(
    client: AsyncClient, session: AsyncSession, test_engine: AsyncEngine
) -> None:
    actor_id, product_id, run_id = await prepared_run(session, "review-api-history")
    pending = await create_research_run(
        session,
        product_id,
        actor_id,
        ResearchCreate(
            goal="待处理",
            knowledge_base_ids=[(await session.get_one(ResearchRun, run_id)).knowledge_base_ids[0]],
        ),
        configured_settings(),
    )
    # The service normally prevents a second active run; here first run is SUCCESS.
    admin = await actor(session, "review-history-admin", Role.ADMIN)
    admin_headers = headers(admin)
    path = f"/api/v1/products/{product_id}/research-runs"
    before = await client.get(f"{path}/{run_id}", headers=admin_headers)
    assert before.status_code == 200
    assert before.json()["review_status"] == "pending_review"
    assert before.json()["review"] is None

    review_queries = 0

    def count_reviews(
        _conn: object,
        _cursor: object,
        statement: str,
        _params: object,
        _context: object,
        _many: object,
    ) -> None:
        nonlocal review_queries
        if "research_report_reviews" in statement.lower() and statement.lstrip().lower().startswith(
            "select"
        ):
            review_queries += 1

    event.listen(test_engine.sync_engine, "before_cursor_execute", count_reviews)
    try:
        listed = await client.get(path, headers=admin_headers)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", count_reviews)
    assert listed.status_code == 200
    assert review_queries == 1
    states = {item["id"]: item["review_status"] for item in listed.json()["items"]}
    assert states[run_id] == "pending_review"
    assert states[pending.id] == "not_ready"

    approved = await client.post(
        f"{path}/{run_id}/review", json={"decision": "approved"}, headers=admin_headers
    )
    assert approved.status_code == 200
    detail = await client.get(f"{path}/{run_id}", headers=admin_headers)
    assert detail.json()["review_status"] == "approved"
    assert detail.json()["review"]["id"] == approved.json()["id"]
    assert detail.json()["report"] == supported_report(product_id)


@pytest.mark.asyncio
async def test_only_approved_report_is_downloadable(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, product_id, run_id = await prepared_run(session, "export-approved")
    original = await session.get_one(ResearchRun, run_id)
    before = deepcopy((original.report, original.steps, original.evidence))
    _, rejected_product, rejected_run = await prepared_run(session, "export-rejected")
    _, insufficient_product, insufficient_run = await prepared_run(session, "export-insufficient")
    insufficient = await session.get_one(ResearchRun, insufficient_run)
    insufficient.report = {
        "outcome": "insufficient_evidence",
        "summary": "资料不足",
        "findings": [],
        "recommendations": [],
        "evidence_gaps": ["缺资料"],
    }
    await session.commit()
    admin = await actor(session, "export-admin", Role.ADMIN)
    admin_headers = headers(admin)
    approved_path = f"/api/v1/products/{product_id}/research-runs/{run_id}"
    rejected_path = f"/api/v1/products/{rejected_product}/research-runs/{rejected_run}"
    insufficient_path = f"/api/v1/products/{insufficient_product}/research-runs/{insufficient_run}"
    assert (await client.get(f"{approved_path}/export", headers=admin_headers)).status_code == 409
    assert (
        await client.get(f"{insufficient_path}/export", headers=admin_headers)
    ).status_code == 409
    rejected = await client.post(
        f"{rejected_path}/review",
        json={"decision": "rejected", "comment": "需补证"},
        headers=admin_headers,
    )
    assert rejected.status_code == 200
    assert (await client.get(f"{rejected_path}/export", headers=admin_headers)).status_code == 409
    approved = await client.post(
        f"{approved_path}/review",
        json={"decision": "approved"},
        headers=admin_headers,
    )
    assert approved.status_code == 200
    for role in (Role.ADMIN, Role.OPERATOR, Role.ANALYST):
        reader = await actor(session, f"export-reader-{role.value}", role)
        response = await client.get(f"{approved_path}/export", headers=headers(reader))
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert f"research-{run_id}.xlsx" in response.headers["content-disposition"]
        assert response.content[:2] == b"PK"
        workbook = load_workbook(BytesIO(response.content))
        values = [cell.value for sheet in workbook for row in sheet for cell in row]
        assert "可验证发现" in values
        assert f"product:{product_id}:snapshot" in values
        detail = await client.get(approved_path, headers=headers(reader))
        assert detail.status_code == 200
        assert (
            detail.json()["report"],
            detail.json()["steps"],
            detail.json()["evidence"],
        ) == before
    await session.refresh(original)
    assert (original.report, original.steps, original.evidence) == before


@pytest.mark.asyncio
async def test_export_requires_product_scope(client: AsyncClient, session: AsyncSession) -> None:
    _, product_id, run_id = await prepared_run(session, "export-scope")
    admin = await actor(session, "export-scope-admin", Role.ADMIN)
    correct = f"/api/v1/products/{product_id}/research-runs/{run_id}"
    approved = await client.post(
        f"{correct}/review",
        json={"decision": "approved"},
        headers=headers(admin),
    )
    assert approved.status_code == 200
    assert (await client.get(f"{correct}/export")).status_code == 401
    wrong = f"/api/v1/products/{product_id + 999}/research-runs/{run_id}/export"
    assert (await client.get(wrong, headers=headers(admin))).status_code == 404
