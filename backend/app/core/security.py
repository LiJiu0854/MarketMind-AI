"""密码哈希与验证入口。"""

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """把明文密码转换为带随机盐的安全哈希。"""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证明文密码是否匹配已有哈希。"""
    return password_hasher.verify(password, password_hash)
