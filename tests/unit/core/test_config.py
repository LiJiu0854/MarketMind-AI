"""应用配置测试。"""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings

SETTINGS_ENVIRONMENT_VARIABLES = (
    "APP_NAME",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "APP_DEBUG",
    "APP_VERSION",
    "DATABASE_URL",
    "LOG_LEVEL",
    "JWT_SECRET",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "SILICONFLOW_BASE_URL",
    "SILICONFLOW_MODEL",
    "SILICONFLOW_API_KEY",
    "TEST_DATABASE_URL",
    "REDIS_URL",
    "TEST_REDIS_URL",
    "REDIS_CACHE_TTL_SECONDS",
)


@pytest.fixture(autouse=True)
def isolate_settings_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """避免开发机器上的环境变量和 .env 影响测试结果。"""
    monkeypatch.chdir(tmp_path)
    for variable_name in SETTINGS_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)


def test_settings_have_safe_defaults() -> None:
    """错误的默认值或意外加载本地 .env 时应失败。"""
    settings = Settings()

    assert settings.app_name == "MarketMind AI"
    assert settings.app_env == "development"
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8010
    assert settings.log_level == "INFO"
    assert settings.app_debug is False
    assert settings.siliconflow_base_url == "https://api.siliconflow.cn/v1"
    assert settings.siliconflow_model == "deepseek-ai/DeepSeek-V4-Flash"
    assert settings.siliconflow_api_key is None


def test_settings_read_and_convert_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量未覆盖默认值或端口未转换为整数时应失败。"""
    monkeypatch.setenv("APP_NAME", "MarketMind Test")
    monkeypatch.setenv("APP_PORT", "9010")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-secret-value")

    settings = Settings()

    assert settings.app_name == "MarketMind Test"
    assert settings.app_port == 9010
    assert isinstance(settings.app_port, int)
    assert isinstance(settings.siliconflow_api_key, SecretStr)
    assert settings.siliconflow_api_key.get_secret_value() == "test-secret-value"


def test_settings_repr_does_not_expose_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings 的调试输出泄露 API Key 时应失败。"""
    api_key = "secret-that-must-not-appear"
    monkeypatch.setenv("SILICONFLOW_API_KEY", api_key)

    settings = Settings()

    assert api_key not in repr(settings)


def test_app_version_default() -> None:
    """测试未设置 APP_VERSION 时，app_version 应为默认值 "0.1.0" """
    settings = Settings()
    assert settings.app_version == "0.1.0"


def test_app_version_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试设置 APP_VERSION 环境变量后，app_version 应使用其值"""
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    settings = Settings()
    assert settings.app_version == "1.2.3"


def test_app_debug_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_DEBUG 应从环境变量转换为布尔值。"""
    monkeypatch.setenv("APP_DEBUG", "True")

    settings = Settings()

    assert settings.app_debug is True


def test_database_urls_are_secret_and_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """数据库连接串未受保护或测试库被意外默认配置时应失败。"""
    database_url = "mysql+asyncmy://user:not-a-real-password@localhost/marketmind"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings()

    assert isinstance(settings.database_url, SecretStr)
    assert database_url not in repr(settings)
    assert settings.test_database_url is None


def test_jwt_settings_have_safe_defaults() -> None:
    """JWT 密钥不能有不安全默认值，Token 有效期应默认为 30 分钟。"""
    settings = Settings()

    assert settings.jwt_secret is None
    assert settings.access_token_expire_minutes == 30


def test_jwt_secret_is_loaded_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWT 密钥应使用 SecretStr，并且不能出现在调试输出中。"""
    secret = "unit-test-jwt-secret"
    monkeypatch.setenv("JWT_SECRET", secret)

    settings = Settings()

    assert isinstance(settings.jwt_secret, SecretStr)
    assert settings.jwt_secret.get_secret_value() == secret
    assert secret not in repr(settings)


def test_redis_settings_have_safe_defaults() -> None:
    """Redis 不能包含秘密默认连接串，缓存 TTL 必须为正数。"""
    settings = Settings()

    assert settings.redis_url is None
    assert settings.test_redis_url is None
    assert settings.redis_cache_ttl_seconds == 60


def test_redis_settings_read_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis URL 应受保护，缓存 TTL 应从环境变量转换为整数。"""
    redis_url = "redis://:test-password@127.0.0.1:6379/0"
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("REDIS_CACHE_TTL_SECONDS", "120")

    settings = Settings()

    assert isinstance(settings.redis_url, SecretStr)
    assert settings.redis_url.get_secret_value() == redis_url
    assert redis_url not in repr(settings)
    assert settings.redis_cache_ttl_seconds == 120


def test_redis_cache_ttl_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """零或负数 TTL 会让缓存策略失去明确边界。"""
    monkeypatch.setenv("REDIS_CACHE_TTL_SECONDS", "0")

    with pytest.raises(ValidationError):
        Settings()
