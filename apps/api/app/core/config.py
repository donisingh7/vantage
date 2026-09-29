from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Vantage"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./data/vantage.db"
    # Serverless PostgreSQL (e.g. Supabase's transaction pooler): use NullPool and disable
    # asyncpg's prepared-statement cache instead of a normal persistent connection pool.
    # No effect on SQLite. See app/db/session.py.
    database_serverless: bool = False
    llm_provider: Literal["mock", "azure_openai", "gemini"] = "mock"
    embedding_provider: Literal["mock", "azure_openai", "gemini"] = "mock"
    azure_openai_endpoint: AnyHttpUrl | None = None
    azure_openai_api_key: str | None = Field(default=None, repr=False)
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_embedding_dimensions: int | None = Field(default=None, ge=8, le=3072)
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, ge=8, le=3072)
    embedding_dimensions: int = Field(default=32, ge=8, le=3072)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    frontend_url: AnyHttpUrl = "http://localhost:3000"
    dev_user_email: str = "analyst@example.local"
    dev_user_name: str = "Vantage Analyst"
    dev_workspace_name: str = "Vantage Development"
    dev_workspace_slug: str = "development"
    request_body_limit_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    ingestion_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    ingestion_read_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    ingestion_max_retries: int = Field(default=2, ge=0, le=5)
    ingestion_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    ingestion_max_discovered_pages: int = Field(default=10, ge=0, le=50)
    ingestion_min_content_length_for_browser: int = Field(default=200, ge=0)
    enable_browser_fallback: bool = False
    enable_scheduler: bool = False
    scheduler_interval_seconds: int = Field(default=60, ge=10, le=3600)

    @field_validator("api_v1_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        normalized = "/" + value.strip("/")
        if normalized == "/":
            raise ValueError("API prefix cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "Settings":
        if "azure_openai" in (self.llm_provider, self.embedding_provider):
            required = {
                "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
                "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
            }
            if self.llm_provider == "azure_openai":
                required["AZURE_OPENAI_CHAT_DEPLOYMENT"] = self.azure_openai_chat_deployment
            if self.embedding_provider == "azure_openai":
                required["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = self.azure_openai_embedding_deployment
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Azure OpenAI provider requires: {', '.join(missing)}")
        if "gemini" in (self.llm_provider, self.embedding_provider) and not self.gemini_api_key:
            raise ValueError("Gemini provider requires: GEMINI_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
