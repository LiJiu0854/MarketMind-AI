"""SQLAlchemy ORM 声明基类。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM Model 共用的元数据入口。"""
