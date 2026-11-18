from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(min_length=1)
    internal_api_key: SecretStr
    cors_origins: str = ""
    rate_limit_requests: int = Field(default=120, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    retrieval_min_score: float = Field(default=0.25, ge=-1, le=1)
    llm_provider: Literal["anthropic", "openai", "openai_compatible"] = "openai_compatible"
    llm_model: str = Field(min_length=1)
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=30, gt=0)
    llm_max_retries: int = Field(default=3, ge=0, le=8)
    llm_fallback_provider: Literal["anthropic", "openai", "openai_compatible"] | None = None
    llm_fallback_model: str | None = None
    llm_fallback_api_key: SecretStr | None = None
    llm_fallback_base_url: str | None = None
    llm_max_tokens: int = Field(default=700, gt=0)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    embed_provider: Literal["local", "openai"] = "local"
    embed_model: str = Field(min_length=1)
    embed_api_key: SecretStr | None = None
    embed_base_url: str | None = None
    embed_dim: int = Field(default=384, gt=0)
    retrieval_top_k: int = Field(default=6, ge=1, le=30)
    max_upload_bytes: int = Field(default=20_000_000, gt=0)

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "Settings":
        if self.llm_provider != "openai_compatible" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required for the selected provider")
        if self.llm_provider == "openai_compatible" and not self.llm_base_url:
            raise ValueError("LLM_BASE_URL is required for openai_compatible")
        if self.llm_fallback_provider and not self.llm_fallback_model:
            raise ValueError("LLM_FALLBACK_MODEL is required when fallback is enabled")
        if self.llm_fallback_provider and self.llm_fallback_provider != "openai_compatible":
            if not self.llm_fallback_api_key:
                raise ValueError("LLM_FALLBACK_API_KEY is required for the fallback provider")
        if self.llm_fallback_provider == "openai_compatible" and not self.llm_fallback_base_url:
            raise ValueError("LLM_FALLBACK_BASE_URL is required for openai_compatible fallback")
        if self.embed_provider == "openai" and not self.embed_api_key:
            raise ValueError("EMBED_API_KEY is required for the openai embedding provider")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
