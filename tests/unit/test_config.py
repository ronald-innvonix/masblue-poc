from app.core.config import Settings


def test_settings_parse_csv_origins_and_ignore_empty_optional_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://local/test")
    monkeypatch.setenv("INTERNAL_API_KEY", "local-test-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "local-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8001/v1")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "")
    monkeypatch.setenv("EMBED_MODEL", "local-embed-model")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example, https://admin.example")

    settings = Settings(_env_file=None)

    assert settings.allowed_cors_origins == [
        "https://app.example",
        "https://admin.example",
    ]
    assert settings.llm_fallback_provider is None
