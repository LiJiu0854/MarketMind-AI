"""密码安全函数测试。"""

from app.core.security import hash_password, verify_password


def test_hash_password_returns_salted_hash() -> None:
    """哈希不能等于明文，相同密码也应产生不同结果。"""
    password = "correct-horse-battery-staple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != password
    assert second_hash != password
    assert first_hash != second_hash


def test_verify_password_accepts_correct_password() -> None:
    """正确密码应通过已有哈希验证。"""
    password = "correct-horse-battery-staple"

    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_rejects_wrong_password() -> None:
    """错误密码不应通过已有哈希验证。"""
    password_hash = hash_password("correct-horse-battery-staple")

    assert verify_password("wrong-password", password_hash) is False
