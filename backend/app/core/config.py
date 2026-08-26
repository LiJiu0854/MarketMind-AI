"""类型化应用配置。"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量和本地 .env 文件读取应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MarketMind AI"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "deepseek-ai/DeepSeek-V4-Flash"
    siliconflow_api_key: SecretStr | None = None
