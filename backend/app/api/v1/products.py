"""商品 CRUD API。"""

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, require_roles
from app.models.product import Product
from app.models.user import Role, User
from app.schemas.product import (
    ListingCheckResult,
    ProductCreate,
    ProductFilters,
    ProductImportResult,
    ProductPage,
    ProductRead,
    ProductUpdate,
)
from app.services.listing_rules import check_listing
from app.services.product_excel import (
    MAX_XLSX_BYTES,
    export_products_workbook,
    parse_product_workbook,
    validate_xlsx_upload,
)
from app.services.products import (
    create_product as create_product_service,
)
from app.services.products import (
    deactivate_product,
    get_product,
    get_products_for_export,
    import_products,
    list_products,
    update_product,
)

ProductManager = Annotated[
    User,
    Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
]

router = APIRouter(
    prefix="/products",
    tags=["商品管理"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ProductManager,
) -> Product:
    """创建商品。"""
    return await create_product_service(session, data, actor.id)


@router.get("", response_model=ProductPage)
async def read_products(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductPage:
    """分页筛选商品。"""
    filters = ProductFilters(
        sku=sku,
        brand=brand,
        category=category,
        is_active=is_active,
    )
    return await list_products(session, filters, page, page_size)


@router.post("/import", response_model=ProductImportResult)
async def import_product_workbook(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ProductManager,
) -> ProductImportResult:
    """同步校验并导入商品工作簿。"""
    content = await file.read(MAX_XLSX_BYTES + 1)
    validate_xlsx_upload(file.filename, content)
    candidates, errors = parse_product_workbook(content)
    return await import_products(session, candidates, errors, actor.id)


@router.get("/export")
async def export_products(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
) -> StreamingResponse:
    """按列表筛选语义导出商品工作簿。"""
    filters = ProductFilters(
        sku=sku,
        brand=brand,
        category=category,
        is_active=is_active,
    )
    content = export_products_workbook(
        await get_products_for_export(session, filters)
    )
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="products.xlsx"'},
    )


@router.get("/{product_id}", response_model=ProductRead)
async def read_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Product:
    """按 ID 读取商品。"""
    return await get_product(session, product_id)


@router.get("/{product_id}/listing-check", response_model=ListingCheckResult)
async def read_listing_check(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListingCheckResult:
    """执行无 I/O 的确定性 Listing 检查。"""
    product = await get_product(session, product_id)
    issues = check_listing(product)
    return ListingCheckResult(
        product_id=product.id,
        passed=not issues,
        issues=issues,
    )


@router.patch("/{product_id}", response_model=ProductRead)
async def patch_product(
    product_id: int,
    data: ProductUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ProductManager,
) -> Product:
    """部分更新商品。"""
    del actor
    product = await get_product(session, product_id)
    return await update_product(session, product, data)


@router.delete("/{product_id}", response_model=ProductRead)
async def delete_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ProductManager,
) -> Product:
    """软停用商品。"""
    del actor
    product = await get_product(session, product_id)
    return await deactivate_product(session, product)
