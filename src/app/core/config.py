"""Environment-backed application settings."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    db_host: str = "localhost"
    db_port: int = Field(default=5432, gt=0, le=65535)
    db_name: str = "ai_chat"
    db_username: str | None = None
    db_password: str | None = None
    database_url: str = ""
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

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        """Build DATABASE_URL from DB_* fields unless it is explicitly configured."""
        if self.database_url:
            return self

        username = quote(self.db_username or "", safe="")
        password = quote(self.db_password or "", safe="")
        credentials = f"{username}:{password}" if username or password else ""
        authority = f"{credentials}@" if credentials else ""
        self.database_url = (
            f"postgresql+asyncpg://{authority}{self.db_host}:{self.db_port}/{self.db_name}"
        )
        return self

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
