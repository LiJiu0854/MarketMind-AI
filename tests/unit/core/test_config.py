"""应用配置测试。"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings

SETTINGS_ENVIRONMENT_VARIABLES = (
    "APP_NAME",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "APP_VERSION",
    "LOG_LEVEL",
    "SILICONFLOW_BASE_URL",
    "SILICONFLOW_MODEL",
    "SILICONFLOW_API_KEY",
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
