"""用户 ORM Model 测试。"""

from app.models.user import Role, User


def test_user_model_exposes_expected_table_contract() -> None:
    """用户表缺少必要字段或角色值漂移时应失败。"""
    assert User.__tablename__ == "users"
    assert set(User.__table__.columns.keys()) == {
        "id",
        "email",
        "full_name",
        "password_hash",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert {role.value for role in Role} == {"admin", "operator", "analyst"}


def test_user_model_exposes_expected_column_constraints() -> None:
    """邮箱应唯一且有索引，ID 应为主键。"""
    email_column = User.__table__.columns["email"]
    id_column = User.__table__.columns["id"]

    assert email_column.unique is True
    assert email_column.index is True
    assert id_column.primary_key is True
