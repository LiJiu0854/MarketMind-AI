"""语义审核 API、RBAC、投递和 MySQL 查询测试。"""

from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.models.semantic_review import SemanticReview, SemanticReviewStatus
from app.models.user import Role, User
from app.schemas.product import ProductCreate
from app.schemas.semantic_review import LLMReviewResult
from app.schemas.user import UserCreate
from app.services.products import create_product
from app.services.semantic_reviews import (
    ReviewCompletion,
    create_semantic_review,
    mark_review_running,
    mark_review_success,
)
from app.services.users import create_user

JWT_SECRET = "semantic-api-test-secret-with-32-bytes"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


def configured_settings() -> Settings:
    return Settings(
        llm_provider="test-provider",
        llm_base_url="https://provider.invalid/v1",
        llm_model="test-model",
        llm_api_key=SecretStr("test-api-key"),
    )


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app(configured_settings())

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def make_user(session: AsyncSession, suffix: str, role: Role) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"semantic-api-{suffix}@example.com",
            full_name=f"Semantic API {suffix}",
            password=PASSWORD,
            role=role,
        ),
    )


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


async def make_product(session: AsyncSession, actor: User, suffix: str) -> int:
    product = await create_product(
        session,
        ProductCreate(
            sku=f"semantic-api-{suffix}",
            title="Useful Product",
            description="A useful product description",
            bullet_points=["First point", "Second point", "Third point"],
            brand="Brand",
            category="Category",
            price=Decimal("19.90"),
            currency="CNY",
        ),
        actor.id,
    )
    return product.id


def review_result() -> LLMReviewResult:
    return LLMReviewResult.model_validate(
        {
            "score": 88,
            "dimension_scores": {
                "completeness": 90,
                "consistency": 85,
                "clarity": 87,
                "risk": 92,
                "persuasion": 86,
            },
            "summary": "商品信息完整，表达清晰。",
            "issues": [
                {
                    "dimension": "clarity",
                    "severity": "medium",
                    "field": "description",
                    "message": "描述可以更具体。",
                    "suggestion": "补充可验证的使用场景。",
                }
            ],
            "rewrite": {
                "title": "清晰具体的商品标题",
                "description": "面向真实使用场景的商品描述。",
                "bullet_points": [
                    "清楚说明商品的核心使用价值",
                    "使用可验证的信息减少理解成本",
                    "避免夸张承诺并保持表达一致",
                ],
            },
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
async def test_manager_can_create_and_dispatch_review(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    actor = await make_user(session, role.value, role)
    product_id = await make_product(session, actor, role.value)
    delay = Mock(return_value=SimpleNamespace(id="task-123"))
    monkeypatch.setattr(
        "app.api.v1.semantic_reviews.generate_semantic_review.delay",
        delay,
    )

    response = await client.post(
        f"/api/v1/products/{product_id}/semantic-reviews",
        headers=auth_headers(actor),
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "task-123"
    assert response.json()["status"] == "pending"
    review = await session.get_one(SemanticReview, response.json()["review_id"])
    assert review.requested_by_id == actor.id
    assert review.provider == "test-provider"
    assert review.model == "test-model"
    assert review.celery_task_id == "task-123"
    delay.assert_called_once_with(review.id)


@pytest.mark.asyncio
async def test_analyst_cannot_create_review(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    analyst = await make_user(session, "analyst", Role.ANALYST)
    product_id = await make_product(session, analyst, "analyst")

    response = await client.post(
        f"/api/v1/products/{product_id}/semantic-reviews",
        headers=auth_headers(analyst),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert (await session.scalars(select(SemanticReview))).all() == []


@pytest.mark.asyncio
async def test_create_review_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/products/1/semantic-reviews")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "api_key"),
    [
        (None, None),
        ("test-model", SecretStr("")),
    ],
)
async def test_create_review_rejects_missing_llm_config(
    session: AsyncSession,
    model: str | None,
    api_key: SecretStr | None,
) -> None:
    app = create_app(Settings(llm_model=model, llm_api_key=api_key))

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    actor = await make_user(session, "missing-config", Role.OPERATOR)
    product_id = await make_product(session, actor, "missing-config")
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        response = await value.post(
            f"/api/v1/products/{product_id}/semantic-reviews",
            headers=auth_headers(actor),
        )

    assert response.status_code == 503
    assert response.json()["code"] == "SEMANTIC_REVIEW_CONFIG_MISSING"
    assert (await session.scalars(select(SemanticReview))).all() == []


@pytest.mark.asyncio
async def test_create_review_rejects_missing_product(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = await make_user(session, "missing-product", Role.OPERATOR)
    delay = Mock()
    monkeypatch.setattr(
        "app.api.v1.semantic_reviews.generate_semantic_review.delay",
        delay,
    )

    response = await client.post(
        "/api/v1/products/999999/semantic-reviews",
        headers=auth_headers(actor),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    delay.assert_not_called()


@pytest.mark.asyncio
async def test_active_review_returns_conflict_without_second_dispatch(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = await make_user(session, "conflict", Role.OPERATOR)
    product_id = await make_product(session, actor, "conflict")
    delay = Mock(return_value=SimpleNamespace(id="task-conflict"))
    monkeypatch.setattr(
        "app.api.v1.semantic_reviews.generate_semantic_review.delay",
        delay,
    )
    headers = auth_headers(actor)

    first = await client.post(
        f"/api/v1/products/{product_id}/semantic-reviews",
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/products/{product_id}/semantic-reviews",
        headers=headers,
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["code"] == "SEMANTIC_REVIEW_ALREADY_ACTIVE"
    delay.assert_called_once()


@pytest.mark.asyncio
async def test_broker_failure_marks_review_failure_and_hides_task_id(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = await make_user(session, "broker", Role.OPERATOR)
    product_id = await make_product(session, actor, "broker")
    monkeypatch.setattr(
        "app.api.v1.semantic_reviews.generate_semantic_review.delay",
        Mock(side_effect=BrokerOperationalError("secret broker url")),
    )

    response = await client.post(
        f"/api/v1/products/{product_id}/semantic-reviews",
        headers=auth_headers(actor),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "SEMANTIC_REVIEW_DISPATCH_FAILED"
    assert "task_id" not in response.json()
    review = (await session.scalars(select(SemanticReview))).one()
    assert review.status is SemanticReviewStatus.FAILURE
    assert review.error_code == "REVIEW_DISPATCH_FAILED"
    assert "secret" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR, Role.ANALYST])
async def test_all_roles_can_read_history_and_detail_without_dispatch(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    actor = await make_user(session, f"read-{role.value}", role)
    product_id = await make_product(session, actor, f"read-{role.value}")
    first = await create_semantic_review(
        session,
        product_id=product_id,
        requested_by_id=actor.id,
        provider="openai",
        model="first-model",
    )
    await mark_review_running(session, first.id)
    await mark_review_success(
        session,
        first.id,
        ReviewCompletion(review_result(), 120, 80, 200),
    )
    second = await create_semantic_review(
        session,
        product_id=product_id,
        requested_by_id=actor.id,
        provider="deepseek",
        model="second-model",
    )
    delay = Mock()
    monkeypatch.setattr(
        "app.api.v1.semantic_reviews.generate_semantic_review.delay",
        delay,
    )
    headers = auth_headers(actor)

    history = await client.get(
        f"/api/v1/products/{product_id}/semantic-reviews?page=1&page_size=1",
        headers=headers,
    )
    detail = await client.get(
        f"/api/v1/products/{product_id}/semantic-reviews/{first.id}",
        headers=headers,
    )

    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["id"] == second.id
    assert history.json()["page"] == 1
    assert history.json()["page_size"] == 1
    assert detail.status_code == 200
    assert detail.json()["score"] == 88
    assert detail.json()["dimension_scores"]["risk"] == 92
    assert detail.json()["product_snapshot"]["price"] == "19.90"
    delay.assert_not_called()


@pytest.mark.asyncio
async def test_detail_rejects_review_from_another_product(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    actor = await make_user(session, "wrong-product", Role.ANALYST)
    first_product_id = await make_product(session, actor, "wrong-product-1")
    second_product_id = await make_product(session, actor, "wrong-product-2")
    review = await create_semantic_review(
        session,
        product_id=first_product_id,
        requested_by_id=actor.id,
        provider="openai",
        model="test-model",
    )

    response = await client.get(
        f"/api/v1/products/{second_product_id}/semantic-reviews/{review.id}",
        headers=auth_headers(actor),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "SEMANTIC_REVIEW_NOT_FOUND"


@pytest.mark.asyncio
async def test_history_requires_authentication_and_existing_product(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    actor = await make_user(session, "history-errors", Role.ANALYST)

    unauthenticated = await client.get("/api/v1/products/1/semantic-reviews")
    missing = await client.get(
        "/api/v1/products/999999/semantic-reviews",
        headers=auth_headers(actor),
    )

    assert unauthenticated.status_code == 401
    assert missing.status_code == 404
    assert missing.json()["code"] == "PRODUCT_NOT_FOUND"
