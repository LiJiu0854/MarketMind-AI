"""认证接口的数据结构。"""

from pydantic import BaseModel, ConfigDict


class TokenResponse(BaseModel):
    """登录成功后返回给客户端的 Bearer Token。"""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
