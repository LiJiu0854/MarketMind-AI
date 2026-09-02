"""类型化应用配置。"""

from pydantic import Field, SecretStr
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
    app_debug: bool = False
    log_level: str = "INFO"
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    access_token_expire_minutes: int = 30
    redis_url: SecretStr | None = None
    test_redis_url: SecretStr | None = None
    redis_cache_ttl_seconds: int = Field(default=60, gt=0)
    idempotency_processing_ttl_seconds: int = Field(default=30, gt=0)
    idempotency_result_ttl_seconds: int = Field(default=86_400, gt=0)
    login_rate_limit: int = Field(default=5, gt=0)
    login_rate_window_seconds: int = Field(default=60, gt=0)
    redis_lock_ttl_ms: int = Field(default=30_000, gt=0)
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "deepseek-ai/DeepSeek-V4-Flash"
    siliconflow_api_key: SecretStr | None = None
