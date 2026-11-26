---
name: masblue-llm-providers
description: How LLM integration works in the Masblue AI Chat Service and how to extend it - the LLMProvider contract, OpenAI-compatible and Anthropic providers, LLMFactory, the DB-backed model registry (models table), per-provider client caching, streaming, timeouts, and error wrapping. Use this skill whenever a task adds or changes an LLM or embedding provider, switches models or base URLs, touches llm/, LLMFactory, get_chat_llm, the models registry or its seeder, intent-classification models, token streaming from a provider, or provider-related settings such as LLM_PROVIDER and LLM_MODEL.
---

# LLM providers

Read `masblue-project-standards` first. Files: `src/app/llm/` (`base.py`, `factory.py`,
`openai_provider.py`, `anthropic_provider.py`, `stub_provider.py`), `api/deps.py`
(selection + caching), `models/embedding_model.py` and `repositories/model_repo.py` (registry),
`seeders/models.py`.

## The contract (`llm/base.py`)

```python
class LLMProvider(ABC):
    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str
    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]
    async def close(self) -> None
```

- `ChatMessage(role, content)` and `ModelConfig(model, temperature, max_tokens, timeout_seconds)` are
  frozen, slotted dataclasses and are provider-agnostic. Services never import an SDK.
- `stream` is a plain `def` returning an async iterator (implemented by an `_stream_tokens` async
  generator), so a caller can `async for` it directly.
- `close()` is abstract: every provider, **including test fakes**, must implement it. (An existing
  test fake forgot, which is one reason two current tests fail.)

## Providers that exist

| `LLM_PROVIDER` | Class | Notes |
|---|---|---|
| `stub` | `StubProvider` | Offline, deterministic; the default |
| `openai`, `grok`, `gemini`, `openai_compatible` | `OpenAICompatibleProvider` and subclasses | One `AsyncOpenAI` client; `grok` and `gemini` only set a default `base_url`; `openai_compatible` needs a `base_url` and tolerates a missing key (Ollama/vLLM) |
| `anthropic` | `AnthropicProvider` | `AsyncAnthropic`; splits `system` messages into the top-level `system` field; defaults `max_tokens` to 4096 because the API requires it |

## Adding a provider

**OpenAI-compatible service** (most vendors): subclass `OpenAICompatibleProvider`, set
`provider_name`, default `base_url` in `__init__` if there is one, and add one entry to
`_OPENAI_COMPATIBLE_PROVIDERS` in `factory.py`. Export it in `llm/__init__.py` (`__all__`). Nothing
else changes.

**Native SDK**: copy `AnthropicProvider` as the model. Required behaviours, all present there:

1. Constructor is keyword-only and accepts an optional prebuilt `client=` so tests can inject a fake.
2. Build request kwargs in one static `_build_kwargs`; omit optional values that are unset.
3. Catch the SDK's base error **and** `TimeoutError`, log
   `logger.error("llm_generate_failed", provider=..., model=..., error_type=type(exc).__name__)`, and
   `raise LLMProviderError() from exc`. Never log prompts, completions, or keys, and never put
   provider text in the client-facing message (it becomes a 502).
4. Empty or malformed upstream output is an error (`LLMProviderError("Upstream LLM returned an empty
   response")`) or a safe `""`, as the existing providers decide per case.
5. `close()` closes the SDK client.
6. Add a branch to `LLMFactory._build_provider` that validates required settings and raises
   `ServiceConfigurationError` (no detail) when the key or model is missing.

Then add tests with a fake SDK client (see `masblue-testing`, "Provider tests") and register any new
setting in all four places.

## How a provider gets selected (`api/deps.py`)

1. `get_chat_service` first asks the registry: `ModelRepository.get_active_by_type(CONVERSATION)`.
   One active row per type is enforced by a partial unique index.
2. If a row exists, its `provider`, `model_name`, `api_key`, `base_url` are used (temperature,
   max tokens, timeout still come from env). If not, env settings are used.
3. Built clients are cached in module-level dicts keyed by their config tuple and closed in the
   lifespan via `dispose_llm_clients`. A new long-lived client must follow this pattern.
4. The intent-classification model (`INTENT_LLM_*`) falls back field by field to the chat settings
   (`get_intent_llm`). The wiring exists but no service uses it yet.

Switching the live model with no deploy = update the registry rows (the seeder
`uv run python -m app.seeders.models` does this for a Gemini conversation model and prompts for the key
with `getpass`; never put a key on the command line or in code).

## Streaming rules

- Yield only non-empty text deltas. Wrap provider failures in `LLMProviderError`.
- The service collects the tokens, then persists the full assistant message after the stream ends
  (see `ChatService.stream_reply`). If the stream fails midway, nothing partial is saved today; mention
  that if the user asks about reliability.
- Never block the event loop: use the async SDK clients only.

## Embeddings (planned, not built)

The architecture doc specifies an `EmbeddingProvider` interface (`embed_query`, `embed_documents`,
`dimensions`) with an `EmbeddingFactory` mirroring `LLMFactory`. If asked to build it, mirror this
package's structure (an `embeddings/` package, abstract base, factory, fake-client tests, `EMBEDDING_*`
settings) and respect the fixed `Vector(1536)` column (see `masblue-ai-architecture`).

## Checks before finishing

- [ ] New provider passes through the factory and has success, stream, and error-wrapping tests.
- [ ] Fakes implement all three abstract methods.
- [ ] No secret is logged, returned, or committed; messages to clients are generic.
- [ ] `ruff`, `mypy`, `pytest` show no new failures.
