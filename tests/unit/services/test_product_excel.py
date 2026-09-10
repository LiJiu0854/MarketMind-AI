"""商品 Excel 纯内存测试。"""

from decimal import Decimal
from io import BytesIO

import pandas as pd  # type: ignore[import-untyped]
import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

from app.core.errors import AppError
from app.schemas.product import ProductImportError
from app.services.product_excel import (
    EXCEL_COLUMNS,
    MAX_XLSX_BYTES,
    ProductImportCandidate,
    clean_boolean,
    clean_bullet_points,
    clean_currency,
    clean_decimal,
    clean_sku,
    clean_text,
    parse_product_row,
    parse_product_workbook,
    read_product_dataframe,
    validate_xlsx_upload,
)


@pytest.mark.parametrize("value", [None, pd.NA, float("nan")])
def test_clean_text_turns_missing_values_into_empty_string(value: object) -> None:
    assert clean_text(value) == ""


def test_clean_sku_and_currency_strip_and_uppercase() -> None:
    assert clean_sku(" sku-1 ") == "SKU-1"
    assert clean_currency(" cny ") == "CNY"


def test_clean_bullet_points_splits_lines_and_removes_blanks() -> None:
    assert clean_bullet_points(" First point \n\n Second point \r\n ") == [
        "First point",
        "Second point",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (" TRUE ", True),
        ("yes", True),
        (1, True),
        ("false", False),
        ("NO", False),
        (0, False),
    ],
)
def test_clean_boolean_accepts_fixed_values(value: object, expected: bool) -> None:
    assert clean_boolean(value) is expected


@pytest.mark.parametrize("value", ["maybe", 2, ""])
def test_clean_boolean_rejects_other_values(value: object) -> None:
    with pytest.raises(ValueError):
        clean_boolean(value)


def test_clean_decimal_builds_decimal_from_text() -> None:
    assert clean_decimal(" 19.90 ") == Decimal("19.90")


@pytest.mark.parametrize("value", [None, "", "abc"])
def test_clean_decimal_rejects_missing_or_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        clean_decimal(value)


@pytest.mark.parametrize("filename", ["products.xlsx", "PRODUCTS.XLSX"])
def test_validate_xlsx_upload_accepts_xlsx(filename: str) -> None:
    validate_xlsx_upload(filename, b"content")


@pytest.mark.parametrize(
    "filename",
    [None, "", "products.xls", "products.csv", "products.xlsx.exe"],
)
def test_validate_xlsx_upload_rejects_other_types(filename: str | None) -> None:
    with pytest.raises(AppError) as exc_info:
        validate_xlsx_upload(filename, b"content")

    assert exc_info.value.code == "EXCEL_INVALID_TYPE"
    assert exc_info.value.status_code == 422


def test_validate_xlsx_upload_rejects_empty_content() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_xlsx_upload("products.xlsx", b"")

    assert exc_info.value.code == "EXCEL_INVALID_WORKBOOK"


def test_validate_xlsx_upload_accepts_exact_size_limit() -> None:
    validate_xlsx_upload("products.xlsx", b"x" * MAX_XLSX_BYTES)


def test_validate_xlsx_upload_rejects_one_byte_over_limit() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_xlsx_upload("products.xlsx", b"x" * (MAX_XLSX_BYTES + 1))

    assert exc_info.value.code == "EXCEL_TOO_LARGE"


def workbook_bytes(
    headers: list[str],
    rows: list[list[object]],
    *,
    second_sheet_row: list[object] | None = None,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    if second_sheet_row is not None:
        second = workbook.create_sheet("Ignored")
        second.append(headers)
        second.append(second_sheet_row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def valid_row(sku: str = "SKU-1") -> list[object]:
    return [sku, "Title", "", "", "Brand", "Category", "19.90", "CNY", True]


def test_read_product_dataframe_reads_only_first_sheet() -> None:
    content = workbook_bytes(
        list(EXCEL_COLUMNS),
        [valid_row("FIRST")],
        second_sheet_row=valid_row("SECOND"),
    )

    frame = read_product_dataframe(content)

    assert frame["sku"].tolist() == ["FIRST"]


@pytest.mark.parametrize(
    "headers",
    [
        list(EXCEL_COLUMNS[:-1]),
        [*EXCEL_COLUMNS, "unknown"],
        ["sku", "sku", *EXCEL_COLUMNS[2:]],
        [*reversed(EXCEL_COLUMNS)],
    ],
)
def test_read_product_dataframe_rejects_invalid_headers(
    headers: list[str],
) -> None:
    with pytest.raises(AppError) as exc_info:
        read_product_dataframe(workbook_bytes(headers, [valid_row()]))

    assert exc_info.value.code == "EXCEL_INVALID_HEADERS"


def test_read_product_dataframe_rejects_damaged_workbook() -> None:
    with pytest.raises(AppError) as exc_info:
        read_product_dataframe(b"not-an-xlsx")

    assert exc_info.value.code == "EXCEL_INVALID_WORKBOOK"


def test_read_product_dataframe_rejects_empty_workbook() -> None:
    content = workbook_bytes([], [])

    with pytest.raises(AppError) as exc_info:
        read_product_dataframe(content)

    assert exc_info.value.code == "EXCEL_INVALID_WORKBOOK"


def test_read_product_dataframe_rejects_5001_rows() -> None:
    content = workbook_bytes(list(EXCEL_COLUMNS), [valid_row()] * 5001)

    with pytest.raises(AppError) as exc_info:
        read_product_dataframe(content)

    assert exc_info.value.code == "EXCEL_TOO_MANY_ROWS"





def valid_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = dict(zip(EXCEL_COLUMNS, valid_row(), strict=True))
    values.update(changes)
    return values


def test_parse_product_row_returns_candidate_with_excel_row() -> None:
    result = parse_product_row(2, valid_values(sku=" sku-1 ", price="19.90"))

    assert isinstance(result, ProductImportCandidate)
    assert result.row == 2
    assert result.data.sku == "SKU-1"
    assert result.data.price == Decimal("19.90")


@pytest.mark.parametrize(
    ("changes", "field", "code"),
    [
        ({"sku": ""}, "sku", "REQUIRED_FIELD"),
        ({"title": ""}, "title", "REQUIRED_FIELD"),
        ({"brand": "x" * 101}, "brand", "FIELD_TOO_LONG"),
        ({"price": "bad"}, "price", "INVALID_PRICE"),
        ({"price": "0"}, "price", "INVALID_PRICE"),
        ({"currency": "人民币"}, "currency", "INVALID_CURRENCY"),
        ({"is_active": "maybe"}, "is_active", "INVALID_BOOLEAN"),
    ],
)
def test_parse_product_row_returns_one_stable_error(
    changes: dict[str, object],
    field: str,
    code: str,
) -> None:
    result = parse_product_row(7, valid_values(**changes))

    assert isinstance(result, ProductImportError)
    assert result == ProductImportError(
        row=7,
        field=field,
        code=code,
        message=result.message,
    )


def test_parse_product_workbook_keeps_valid_rows_and_reports_invalid_rows() -> None:
    content = workbook_bytes(
        list(EXCEL_COLUMNS),
        [
            valid_row("SKU-1"),
            ["SKU-2", "", "", "", "Brand", "Category", "19.90", "CNY", True],
            valid_row("SKU-3"),
        ],
    )

    candidates, errors = parse_product_workbook(content)

    assert [item.data.sku for item in candidates] == ["SKU-1", "SKU-3"]
    assert [(error.row, error.field) for error in errors] == [(3, "title")]
    assert len(candidates) + len(errors) == 3


def test_parse_product_workbook_rejects_second_normalized_duplicate() -> None:
    content = workbook_bytes(
        list(EXCEL_COLUMNS),
        [valid_row(" sku-1 "), valid_row("SKU-1")],
    )

    candidates, errors = parse_product_workbook(content)

    assert [item.row for item in candidates] == [2]
    assert errors == [
        ProductImportError(
            row=3,
            field="sku",
            code="DUPLICATE_SKU_IN_FILE",
            message="文件内 SKU 重复",
        )
    ]


def test_parse_product_workbook_skips_fully_blank_rows() -> None:
    blank: list[object] = [None] * len(EXCEL_COLUMNS)
    content = workbook_bytes(
        list(EXCEL_COLUMNS),
        [valid_row("SKU-1"), blank, valid_row("SKU-2"), blank],
    )

    candidates, errors = parse_product_workbook(content)

    assert [item.row for item in candidates] == [2, 4]
    assert errors == []


def test_parse_product_workbook_does_not_reserve_sku_from_invalid_row() -> None:
    invalid = valid_row("SKU-1")
    invalid[1] = ""
    content = workbook_bytes(
        list(EXCEL_COLUMNS),
        [invalid, valid_row(" sku-1 ")],
    )

    candidates, errors = parse_product_workbook(content)

    assert [item.row for item in candidates] == [3]
    assert [(error.row, error.code) for error in errors] == [(2, "REQUIRED_FIELD")]
