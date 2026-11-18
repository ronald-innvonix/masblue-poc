from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.embeddings.providers.local import LocalEmbeddingProvider
from app.embeddings.providers.openai import OpenAIEmbeddingProvider
from app.llm.base import EmbeddingProvider


def get_embeddings(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if settings.embed_provider == "local":
        try:
            return LocalEmbeddingProvider(settings.embed_model)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProviderError("Unable to initialize local embedding model") from exc
    if settings.embed_provider == "openai":
        if not settings.embed_api_key:
            raise ValueError("EMBED_API_KEY is required for openai embeddings")
        return OpenAIEmbeddingProvider(
            settings.embed_model,
            settings.embed_api_key.get_secret_value(),
            settings.embed_base_url or "https://api.openai.com/v1",
            settings.llm_timeout_seconds,
            settings.llm_max_retries,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embed_provider}")
