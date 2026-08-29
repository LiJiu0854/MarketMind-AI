"""用户输入与输出数据结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    """创建用户时允许接收的字段。"""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="用户邮箱")
    full_name: str = Field(min_length=1, max_length=100, description="用户全名")
    password: str = Field(min_length=12, max_length=128, repr=False)
    role: Role = Field(..., description="用户角色")


class UserUpdate(BaseModel):
    """更新用户时允许接收的可选字段。"""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = Field(default=None, description="用户邮箱")
    full_name: str | None = Field(
        default=None, min_length=1, max_length=100, description="用户全名"
    )
    password: str | None = Field(default=None, min_length=12, max_length=128, repr=False)
    role: Role | None = Field(default=None, description="用户角色")
    is_active: bool | None = Field(default=None, description="用户是否激活")


class UserRead(BaseModel):
    """返回给客户端的安全用户数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="用户 ID")
    email: EmailStr = Field(description="用户邮箱")
    full_name: str = Field(description="用户全名")
    role: Role = Field(description="用户角色")
    is_active: bool = Field(description="用户是否激活")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class UserPage(BaseModel):
    """用户分页查询结果。"""

    model_config = ConfigDict(extra="forbid")

    items: list[UserRead] = Field(description="用户列表")
    total: int = Field(ge=0, description="总用户数")
    page: int = Field(ge=1, description="当前页码")
    page_size: int = Field(ge=1, le=100, description="每页用户数")



    
