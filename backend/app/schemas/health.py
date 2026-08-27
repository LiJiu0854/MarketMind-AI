"""健康检查响应模型。"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """服务存活状态响应。"""

    status: Literal["ok"]
    service: str
