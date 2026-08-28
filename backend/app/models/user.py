"""用户 ORM Model。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(StrEnum):
    """阶段 1 的固定用户角色。"""

    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"


def _role_values(role_type: type[Role]) -> list[str]:
    return [role.value for role in role_type]


class User(Base):
    """内部平台用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="user_role",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=_role_values,
        )
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
