"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://localhost/ai_chat"
    db_schema: str = Field(default="ai_chat", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    jwt_secret: str | None = None
    jwt_public_key: str | None = None
    jwt_algorithm: str = "HS256"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    llm_provider: str = "stub"
    llm_api_key: str | None = None
    llm_model: str = "stub"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    rate_limit_per_minute: int = Field(default=60, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        """Reject empty origin entries while allowing comma-separated env values."""
        if any(not origin.strip() for origin in value.split(",")):
            raise ValueError("CORS_ORIGINS cannot contain empty origins")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
