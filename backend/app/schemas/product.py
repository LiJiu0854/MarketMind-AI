"""商品 CRUD 输入与输出结构。"""

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class ProductBase(BaseModel):
    """创建与读取共用的商品业务字段。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    brand: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    is_active: bool = True

    normalize_codes = field_validator("sku", "currency", mode="before")(
        _normalize_upper
    )


class ProductCreate(ProductBase):
    """创建商品输入。"""


class ProductUpdate(BaseModel):
    """部分更新商品输入。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str | None = Field(default=None, min_length=1, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    bullet_points: list[str] | None = None
    brand: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    is_active: bool | None = None

    normalize_codes = field_validator("sku", "currency", mode="before")(
        _normalize_upper
    )


class ProductRead(ProductBase):
    """返回给客户端的安全商品结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    """商品分页结果。"""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ProductFilters(BaseModel):
    """列表和导出共用的固定筛选条件。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str | None = Field(default=None, min_length=1, max_length=50)
    brand: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    normalize_sku = field_validator("sku", mode="before")(_normalize_upper)


class ProductImportError(BaseModel):
    """一个 Excel 数据行的稳定错误。"""

    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=2)
    field: str
    code: str
    message: str


class ProductImportResult(BaseModel):
    """同步商品导入结果。"""

    model_config = ConfigDict(extra="forbid")

    total_rows: int = Field(ge=0)
    imported_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    errors: list[ProductImportError]

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        if self.total_rows != self.imported_rows + self.failed_rows:
            raise ValueError("导入行数统计不一致")
        return self


class ListingIssue(BaseModel):
    """单条可解释的 Listing 问题。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    field: str
    message: str
    suggestion: str


class ListingCheckResult(BaseModel):
    """一个商品的确定性 Listing 检查结果。"""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    passed: bool
    issues: list[ListingIssue]
