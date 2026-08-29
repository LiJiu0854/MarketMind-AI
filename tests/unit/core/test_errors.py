"""应用业务异常测试。"""

from app.core.errors import AppError


def test_app_error_keeps_safe_public_data() -> None:
    """业务异常应保留供 API 使用的安全公开数据。"""
    error = AppError(
        code="USER_EMAIL_CONFLICT",
        message="用户邮箱已存在",
        status_code=409,
    )

    assert error.code == "USER_EMAIL_CONFLICT"
    assert error.message == "用户邮箱已存在"
    assert error.status_code == 409
    assert str(error) == "用户邮箱已存在"
