"""商品 CRUD API 与 RBAC 测试。"""

from collections.abc import AsyncIterator
from io import BytesIO

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.products as products_service
from app.api.dependencies import get_db_session
from app.core.security import create_access_token
from app.main import create_app
from app.models.product import Product
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.product_excel import EXCEL_COLUMNS, MAX_XLSX_BYTES
from app.services.users import create_user

JWT_SECRET = "unit-test-jwt-secret-with-32-bytes"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def make_user(session: AsyncSession, index: int, role: Role) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"product-api-{index}@example.com",
            full_name=f"Product API User {index}",
            password=PASSWORD,
            role=role,
        ),
    )


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


def product_json() -> dict[str, object]:
    return {
        "sku": " sku-1 ",
        "title": "Product 1",
        "price": "19.90",
        "currency": "cny",
    }


def workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(EXCEL_COLUMNS))
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def workbook_with_headers(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def excel_row(sku: str, *, title: str = "Product", price: str = "19.90") -> list[object]:
    return [sku, title, "", "", "Brand", "Category", price, "CNY", True]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
async def test_writer_can_create_product(
    client: AsyncClient,
    session: AsyncSession,
    role: Role,
) -> None:
    actor = await make_user(session, 1, role)

    response = await client.post(
        "/api/v1/products",
        headers=auth_headers(actor),
        json=product_json(),
    )

    assert response.status_code == 201
    assert response.json()["sku"] == "SKU-1"
    assert response.json()["created_by_id"] == actor.id


@pytest.mark.asyncio
async def test_analyst_cannot_write_but_can_read(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    analyst = await make_user(session, 2, Role.ANALYST)
    created = await client.post(
        "/api/v1/products",
        headers=auth_headers(operator),
        json=product_json(),
    )
    product_id = created.json()["id"]

    blocked = await client.patch(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(analyst),
        json={"title": "Blocked"},
    )
    read = await client.get(
        f"/api/v1/products/{product_id}",
        headers=auth_headers(analyst),
    )

    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PERMISSION_DENIED"
    assert read.status_code == 200


@pytest.mark.asyncio
async def test_products_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/products")).status_code == 401


@pytest.mark.asyncio
async def test_writer_lists_updates_and_deactivates_product(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    headers = auth_headers(operator)
    created = await client.post(
        "/api/v1/products",
        headers=headers,
        json=product_json(),
    )
    product_id = created.json()["id"]

    listed = await client.get(
        "/api/v1/products?sku=sku-1",
        headers=headers,
    )
    updated = await client.patch(
        f"/api/v1/products/{product_id}",
        headers=headers,
        json={"title": "Updated Product"},
    )
    deactivated = await client.delete(
        f"/api/v1/products/{product_id}",
        headers=headers,
    )

    assert listed.json()["total"] == 1
    assert updated.json()["title"] == "Updated Product"
    assert deactivated.json()["is_active"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
async def test_writer_imports_valid_rows_and_reports_invalid_rows(
    client: AsyncClient,
    session: AsyncSession,
    role: Role,
) -> None:
    actor = await make_user(session, 1, role)
    content = workbook_bytes(
        [
            excel_row("SKU-1"),
            excel_row("SKU-2", price="bad"),
            excel_row(" sku-1 "),
        ]
    )

    response = await client.post(
        "/api/v1/products/import",
        headers=auth_headers(actor),
        files={"file": ("products.xlsx", content)},
    )

    assert response.status_code == 200
    assert response.json()["total_rows"] == 3
    assert response.json()["imported_rows"] == 1
    assert response.json()["failed_rows"] == 2
    assert [error["code"] for error in response.json()["errors"]] == [
        "INVALID_PRICE",
        "DUPLICATE_SKU_IN_FILE",
    ]


@pytest.mark.asyncio
async def test_analyst_cannot_import_products(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    analyst = await make_user(session, 1, Role.ANALYST)
    response = await client.post(
        "/api/v1/products/import",
        headers=auth_headers(analyst),
        files={"file": ("products.xlsx", workbook_bytes([excel_row("SKU-1")]))},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_product_import_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/products/import",
        files={"file": ("products.xlsx", workbook_bytes([excel_row("SKU-1")]))},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_product_import_rejects_wrong_extension_and_oversized_content(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    headers = auth_headers(operator)

    wrong_type = await client.post(
        "/api/v1/products/import",
        headers=headers,
        files={"file": ("products.csv", b"content")},
    )
    oversized = await client.post(
        "/api/v1/products/import",
        headers=headers,
        files={"file": ("products.xlsx", b"x" * (MAX_XLSX_BYTES + 1))},
    )

    assert wrong_type.status_code == 422
    assert wrong_type.json()["code"] == "EXCEL_INVALID_TYPE"
    assert oversized.status_code == 422
    assert oversized.json()["code"] == "EXCEL_TOO_LARGE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"not-an-xlsx", "EXCEL_INVALID_WORKBOOK"),
        (
            workbook_with_headers(list(EXCEL_COLUMNS[:-1]), [excel_row("SKU-1")]),
            "EXCEL_INVALID_HEADERS",
        ),
    ],
)
async def test_product_import_file_errors_write_nothing(
    client: AsyncClient,
    session: AsyncSession,
    content: bytes,
    code: str,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)

    response = await client.post(
        "/api/v1/products/import",
        headers=auth_headers(operator),
        files={"file": ("products.xlsx", content)},
    )

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert (await session.scalars(select(Product))).all() == []


@pytest.mark.asyncio
async def test_importing_same_workbook_twice_reports_database_duplicate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    headers = auth_headers(operator)
    files = {"file": ("products.xlsx", workbook_bytes([excel_row("SKU-1")]))}

    first = await client.post("/api/v1/products/import", headers=headers, files=files)
    second = await client.post("/api/v1/products/import", headers=headers, files=files)

    assert first.json()["imported_rows"] == 1
    assert second.json()["imported_rows"] == 0
    assert second.json()["errors"][0]["code"] == "DUPLICATE_SKU_IN_DATABASE"
    assert len((await session.scalars(select(Product))).all()) == 1


@pytest.mark.asyncio
async def test_import_conflict_returns_safe_409(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = await make_user(session, 1, Role.OPERATOR)
    headers = auth_headers(operator)
    await client.post("/api/v1/products", headers=headers, json=product_json())

    async def miss_existing_skus(
        session: AsyncSession,
        skus: set[str],
    ) -> set[str]:
        del session, skus
        return set()

    monkeypatch.setattr(products_service, "find_existing_skus", miss_existing_skus)
    response = await client.post(
        "/api/v1/products/import",
        headers=headers,
        files={"file": ("products.xlsx", workbook_bytes([excel_row("SKU-1")]))},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRODUCT_IMPORT_CONFLICT"
    assert response.json()["message"] == "导入期间 SKU 发生冲突，请重新导入"
    assert response.json()["request_id"]
    assert "sql" not in response.text.lower()
