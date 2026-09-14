"""商品 Listing 确定性规则。"""

import re

from app.models.product import Product
from app.schemas.product import ListingIssue

FORBIDDEN_TERMS = ("最便宜", "绝对有效", "永久有效", "100%保证")


def check_listing(product: Product) -> list[ListingIssue]:
    """返回商品的全部确定性问题，不执行 I/O。"""
    issues: list[ListingIssue] = []

    if len(product.title) < 10:
        issues.append(
            ListingIssue(
                code="TITLE_TOO_SHORT",
                field="title",
                message="标题少于 10 个字符",
                suggestion="补充能准确描述商品的标题",
            )
        )

    if not product.description:
        issues.append(
            ListingIssue(
                code="DESCRIPTION_MISSING",
                field="description",
                message="商品描述为空",
                suggestion="填写商品描述",
            )
        )
    elif len(product.description) < 50:
        issues.append(
            ListingIssue(
                code="DESCRIPTION_TOO_SHORT",
                field="description",
                message="商品描述少于 50 个字符",
                suggestion="补充商品用途、特点和适用场景",
            )
        )
    elif len(product.description) > 5000:
        issues.append(
            ListingIssue(
                code="DESCRIPTION_TOO_LONG",
                field="description",
                message="商品描述超过 5000 个字符",
                suggestion="删除重复或无关内容",
            )
        )

    if not 3 <= len(product.bullet_points) <= 5:
        issues.append(
            ListingIssue(
                code="BULLET_COUNT_INVALID",
                field="bullet_points",
                message="卖点数量必须为 3 到 5 条",
                suggestion="调整卖点数量",
            )
        )
    if any(len(point) < 10 for point in product.bullet_points):
        issues.append(
            ListingIssue(
                code="BULLET_TOO_SHORT",
                field="bullet_points",
                message="存在少于 10 个字符的卖点",
                suggestion="补充卖点的具体信息",
            )
        )
    if any(len(point) > 200 for point in product.bullet_points):
        issues.append(
            ListingIssue(
                code="BULLET_TOO_LONG",
                field="bullet_points",
                message="存在超过 200 个字符的卖点",
                suggestion="精简过长卖点",
            )
        )

    if product.price <= 0:
        issues.append(
            ListingIssue(
                code="PRICE_INVALID",
                field="price",
                message="价格必须大于 0",
                suggestion="填写有效价格",
            )
        )
    if re.fullmatch(r"[A-Z]{3}", product.currency) is None:
        issues.append(
            ListingIssue(
                code="CURRENCY_INVALID",
                field="currency",
                message="货币代码必须为三位大写字母",
                suggestion="使用 CNY、USD 等 ISO 货币代码",
            )
        )

    text_fields = {
        "title": product.title,
        "description": product.description,
        "bullet_points": "\n".join(product.bullet_points),
    }
    for field, text in text_fields.items():
        if any(term.casefold() in text.casefold() for term in FORBIDDEN_TERMS):
            issues.append(
                ListingIssue(
                    code="FORBIDDEN_TERM",
                    field=field,
                    message="内容包含禁用词",
                    suggestion="删除或改写绝对化宣传用语",
                )
            )

    return issues
