"""类型化应用配置。"""

from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
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
    celery_broker_url: SecretStr | None = None
    celery_result_backend: SecretStr | None = None
    celery_task_always_eager: bool = False
    celery_result_expires_seconds: int = Field(default=3_600, gt=0)
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: int = Field(default=60, gt=0)
    llm_max_output_tokens: int = Field(default=2_000, gt=0)
    knowledge_file_root: Path = Path("data/knowledge")
    knowledge_max_file_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    rag_chunk_size: int = Field(default=1_000, gt=0)
    rag_chunk_overlap: int = Field(default=150, ge=0)
    rag_top_k: int = Field(default=5, ge=1, le=10)
    rag_max_distance: float = Field(default=0.35, ge=0, le=2)
    chroma_host: str = "127.0.0.1"
    chroma_port: int = Field(default=8_000, ge=1, le=65_535)
    chroma_ssl: bool = False
    chroma_tenant: str = "default_tenant"
    chroma_database: str = "default_database"
    embedding_provider: str = "openai"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_timeout_seconds: int = Field(default=60, gt=0)
    embedding_batch_size: int = Field(default=64, gt=0, le=2_048)

    @field_validator(
        "llm_provider",
        "llm_base_url",
        "chroma_host",
        "chroma_tenant",
        "chroma_database",
        "embedding_provider",
        "embedding_base_url",
    )
    @classmethod
    def validate_required_llm_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("LLM 配置不能为空")
        return value

    @field_validator("llm_model", "embedding_model")
    @classmethod
    def normalize_optional_llm_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("llm_api_key", "embedding_api_key")
    @classmethod
    def normalize_optional_llm_secret(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value().strip()
        return SecretStr(secret) if secret else None

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> Self:
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG 分块重叠必须小于分块大小")
        return self
