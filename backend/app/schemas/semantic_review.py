"""语义审核输入与输出结构。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductSnapshot(BaseModel):
    """发起审核时冻结的商品业务字段。"""

    model_config = ConfigDict(extra="forbid")

    sku: str
    title: str
    description: str
    bullet_points: list[str]
    brand: str
    category: str
    price: Decimal
    currency: str
    is_active: bool
