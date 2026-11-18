from app.llm.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, model: str, api_key: str | None, timeout: float, max_retries: int) -> None:
        super().__init__(model, api_key, "https://api.openai.com/v1", timeout, max_retries)
