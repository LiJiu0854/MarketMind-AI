"""密码哈希与验证入口。"""

from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import SecretStr

password_hasher = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """把明文密码转换为带随机盐的安全哈希。"""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证明文密码是否匹配已有哈希。"""
    return password_hasher.verify(password, password_hash)


def create_access_token(
    user_id: int, secret: SecretStr, expires_minutes: int
) -> str:
    """创建包含用户 ID 和过期时间的 JWT。"""
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expires_at,
    }
    token = jwt.encode(payload, secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str, secret: SecretStr) -> int:
    """验证 JWT 并返回整数用户 ID。"""
    payload = jwt.decode(
        token,
        secret.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "exp"]},
    )
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidTokenError("Token subject is invalid")
    try:
        return int(subject)
    except ValueError:
        raise InvalidTokenError("Token subject is invalid") from None
