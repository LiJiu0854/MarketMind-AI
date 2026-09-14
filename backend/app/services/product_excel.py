"""商品 Excel 文件读取、清洗和校验。"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd  # type: ignore[import-untyped]
from openpyxl.utils.exceptions import InvalidFileException  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.core.errors import AppError
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductImportError

MAX_XLSX_BYTES = 5 * 1024 * 1024   # 5 MiB，二进制
MAX_PRODUCT_ROWS = 5000            # 后续行数限制，本单元不用
EXCEL_COLUMNS = (
    "sku",
    "title",
    "description",
    "bullet_points",
    "brand",
    "category",
    "price",
    "currency",
    "is_active",
)


def validate_xlsx_upload(filename: str | None, content: bytes) -> None:
    """校验上传文件名、空内容和字节大小。"""
    # 1. 检查文件名是否有效且以 .xlsx 结尾（不区分大小写）
    if filename is None:
        raise AppError(
            code="EXCEL_INVALID_TYPE",
            message="仅支持 .xlsx 格式的文件",
            status_code=422,
        )
    if Path(filename).suffix.lower() != ".xlsx":
        raise AppError(
            code="EXCEL_INVALID_TYPE",
            message="仅支持 .xlsx 格式的文件",
            status_code=422,
        )

    # 2. 检查内容是否为空
    if not content:  # len(content) == 0
        raise AppError(
            code="EXCEL_INVALID_WORKBOOK",
            message="上传的 Excel 文件为空",
            status_code=422,
        )

    # 3. 检查大小是否超过上限
    if len(content) > MAX_XLSX_BYTES:
        raise AppError(
            code="EXCEL_TOO_LARGE",
            message=f"文件大小超过 {MAX_XLSX_BYTES // 1024 // 1024} MiB 上限",
            status_code=422,
        )


def read_product_dataframe(content: bytes) -> pd.DataFrame:
    """读取第一个工作表并校验结构。"""
    try:
        frame = pd.read_excel(
            BytesIO(content),
            sheet_name=0,
            engine="openpyxl",
            dtype=object,
        )
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        raise AppError(
            code="EXCEL_INVALID_WORKBOOK",
            message="无法解析 Excel 文件，请确认格式正确且未损坏",
            status_code=422,
        ) from exc

    if frame.empty or frame.columns.empty:
        raise AppError(
            code="EXCEL_INVALID_WORKBOOK",
            message="Excel 文件为空或无有效数据",
            status_code=422,
        )

    if list(frame.columns) != list(EXCEL_COLUMNS):
        raise AppError(
            code="EXCEL_INVALID_HEADERS",
            message=(
                "Excel 表头必须为：sku, title, description, bullet_points, brand, "
                "category, price, currency, is_active，且顺序不变"
            ),
            status_code=422,
        )

    if len(frame) > MAX_PRODUCT_ROWS:
        raise AppError(
            code="EXCEL_TOO_MANY_ROWS",
            message=f"数据行数超过 {MAX_PRODUCT_ROWS} 行上限",
            status_code=422,
        )

    return frame


def clean_text(value: object) -> str:
    """将任意值转为去除首尾空格的字符串，空值转为空字符串。"""
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def clean_sku(value: object) -> str:
    """SKU：清洗后转为大写。"""
    return clean_text(value).upper()


def clean_currency(value: object) -> str:
    """货币代码：清洗后转为大写。"""
    return clean_text(value).upper()


def clean_bullet_points(value: object) -> list[str]:
    """将多行文本按换行分割，去除空行和首尾空格。"""
    text = clean_text(value)
    if not text:
        return []
    lines = text.splitlines()
    result = []
    for line in lines:
        cleaned = line.strip()
        if cleaned:
            result.append(cleaned)
    return result


def clean_boolean(value: object) -> bool:
    """将常见真/假表示转为布尔值，否则抛 ValueError。"""
    if isinstance(value, bool):
        return value

    text = clean_text(value)
    if not text:
        raise ValueError("布尔值不能为空")

    lower = text.lower()
    if lower in ("true", "yes", "1"):
        return True
    if lower in ("false", "no", "0"):
        return False

    raise ValueError(f"无法识别的布尔值: {value}")


def clean_decimal(value: object) -> Decimal:
    """从清洗后的字符串构造 Decimal，空值或非法格式抛 ValueError。"""
    text = clean_text(value)
    if not text:
        raise ValueError("金额不能为空")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"无效的金额格式: {value}") from exc


@dataclass(frozen=True, slots=True)
class ProductImportCandidate:
    row: int
    data: ProductCreate


def parse_product_row(
    row_number: int,
    values: Mapping[str, object],
) -> ProductImportCandidate | ProductImportError:
    """清洗并校验一行，只返回候选或一个错误。"""
    # 字段清洗映射
    cleaners = {
        "sku": clean_sku,
        "title": clean_text,
        "description": clean_text,
        "bullet_points": clean_bullet_points,
        "brand": clean_text,
        "category": clean_text,
        "price": clean_decimal,
        "currency": clean_currency,
        "is_active": clean_boolean,
    }

    cleaned: dict[str, object] = {}

    # 第一步：逐个清洗，捕获 ValueError
    for field, cleaner in cleaners.items():
        raw = values.get(field)
        try:
            cleaned[field] = cleaner(raw)
        except ValueError as exc:
            # 根据字段映射错误码
            code = "INVALID_VALUE"
            message = str(exc)
            if field == "price":
                code = "INVALID_PRICE"
                message = "价格格式无效"
            elif field == "currency":
                code = "INVALID_CURRENCY"
                message = "货币代码必须为三位大写字母"
            elif field == "is_active":
                code = "INVALID_BOOLEAN"
                message = "是否启用必须为 true/false/yes/no/1/0"
            elif field == "sku":
                code = "INVALID_SKU"
                message = "SKU 格式无效"
            return ProductImportError(
                row=row_number,
                field=field,
                code=code,
                message=message,
            )

    # 第二步：用 ProductCreate 做完整校验
    try:
        data = ProductCreate.model_validate(cleaned)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = str(first["loc"][0])
        error_type = first["type"]

        # 先按字段名做针对性映射（更精确）
        if loc == "currency":
            code = "INVALID_CURRENCY"
            message = "货币代码必须为三位大写字母"
        elif loc == "price":
            code = "INVALID_PRICE"
            message = "价格必须为大于 0、最多两位小数的金额"
        elif loc == "sku":
            if error_type in ("missing", "string_too_short"):
                code = "REQUIRED_FIELD"
                message = "SKU 为必填"
            else:
                code = "INVALID_SKU"
                message = "SKU 格式无效"
        elif loc == "title":
            if error_type in ("missing", "string_too_short"):
                code = "REQUIRED_FIELD"
                message = "标题为必填"
            elif error_type == "string_too_long":
                code = "FIELD_TOO_LONG"
                message = "标题长度超限"
            else:
                code = "INVALID_FIELD"
                message = first.get("msg", "标题校验失败")
        elif error_type in ("missing", "string_too_short"):
            code = "REQUIRED_FIELD"
            message = f"字段 {loc} 为必填"
        elif error_type == "string_too_long":
            code = "FIELD_TOO_LONG"
            message = f"字段 {loc} 长度超限"
        else:
            code = "INVALID_FIELD"
            message = first.get("msg", "字段校验失败")

        return ProductImportError(
            row=row_number,
            field=loc,
            code=code,
            message=message,
        )

    return ProductImportCandidate(row=row_number, data=data)


def parse_product_workbook(
    content: bytes,
) -> tuple[list[ProductImportCandidate], list[ProductImportError]]:
    """解析工作簿，返回合法候选和行级错误。"""
    # 1. 先通过文件级校验
    frame = read_product_dataframe(content)

    candidates: list[ProductImportCandidate] = []
    errors: list[ProductImportError] = []
    seen_skus: set[str] = set()

    # 2. 逐行处理（idx 从 0 开始，对应 Excel 第 2 行）
    for idx, row in frame.iterrows():
        row_number = idx + 2

        # 3. 判断全空行：所有值都为 None/NaN/空字符串
        all_empty = True
        for val in row:
            if val is not None:
                # 处理 pandas NA 和 float nan
                if isinstance(val, float) and pd.isna(val):
                    continue
                if isinstance(val, str) and val.strip() == "":
                    continue
                all_empty = False
                break
        if all_empty:
            continue

        # 4. 转换为字典并解析
        values = row.to_dict()
        result = parse_product_row(row_number, values)

        if isinstance(result, ProductImportError):
            errors.append(result)
        else:
            # 5. 文件内去重（基于规范化后的 SKU）
            sku = result.data.sku
            if sku in seen_skus:
                errors.append(
                    ProductImportError(
                        row=row_number,
                        field="sku",
                        code="DUPLICATE_SKU_IN_FILE",
                        message="文件内 SKU 重复",
                    )
                )
            else:
                seen_skus.add(sku)
                candidates.append(result)

    return candidates, errors


def export_products_workbook(products: list[Product]) -> bytes:
    """在内存中生成可重新打开的商品工作簿。"""
    rows = [
        {
            "sku": product.sku,
            "title": product.title,
            "description": product.description,
            "bullet_points": "\n".join(product.bullet_points),
            "brand": product.brand,
            "category": product.category,
            "price": product.price,
            "currency": product.currency,
            "is_active": product.is_active,
        }
        for product in products
    ]
    frame = pd.DataFrame(rows, columns=EXCEL_COLUMNS)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Products")
    return output.getvalue()
