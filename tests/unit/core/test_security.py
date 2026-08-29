"""密码与 JWT 安全函数测试。"""

import pytest
from jwt import ExpiredSignatureError, InvalidSignatureError, decode
from pydantic import SecretStr

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


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


def test_access_token_contains_string_subject_and_round_trips() -> None:
    """Token 的 sub 应为字符串，并能还原为整数用户 ID。"""
    secret = SecretStr("unit-test-jwt-secret-with-32-bytes")

    token = create_access_token(user_id=42, secret=secret, expires_minutes=30)
    payload = decode(
        token,
        secret.get_secret_value(),
        algorithms=["HS256"],
    )

    assert payload["sub"] == "42"
    assert decode_access_token(token, secret) == 42


def test_decode_access_token_rejects_expired_token() -> None:
    """过期 Token 不能还原用户身份。"""
    secret = SecretStr("unit-test-jwt-secret-with-32-bytes")
    token = create_access_token(user_id=42, secret=secret, expires_minutes=-1)

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token, secret)


def test_decode_access_token_rejects_tampered_signature() -> None:
    """签名被修改后，即使载荷可读也必须拒绝。"""
    secret = SecretStr("unit-test-jwt-secret-with-32-bytes")
    token = create_access_token(user_id=42, secret=secret, expires_minutes=30)
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{header}.{payload}.{replacement}{signature[1:]}"

    with pytest.raises(InvalidSignatureError):
        decode_access_token(tampered, secret)
