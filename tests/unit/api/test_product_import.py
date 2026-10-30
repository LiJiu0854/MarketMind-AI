"""损坏工作簿在进入数据库写入前返回稳定的业务错误。"""

from collections.abc import AsyncIterator
from io import BytesIO
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.products as products_api
from app.api.dependencies import get_current_user, get_db_session
from app.main import create_app
from app.models.user import Role, User


@pytest.mark.asyncio
@pytest.mark.parametrize("manifest", [None, b"<Types"])
async def test_import_rejects_broken_package_before_writing(
    manifest: bytes | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        if manifest is not None:
            archive.writestr("[Content_Types].xml", manifest)
    session = AsyncMock(spec=AsyncSession)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    async def override_user() -> User:
        return User(id=1, role=Role.OPERATOR, is_active=True)

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    import_products = AsyncMock()
    monkeypatch.setattr(products_api, "import_products", import_products)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("damaged.xlsx", output.getvalue())},
        )

    assert response.status_code == 422
    assert response.json() == {
        "code": "EXCEL_INVALID_WORKBOOK",
        "message": "无法解析 Excel 文件，请确认格式正确且未损坏",
        "request_id": response.headers["X-Request-ID"],
    }
    import_products.assert_not_called()
    session.commit.assert_not_called()
