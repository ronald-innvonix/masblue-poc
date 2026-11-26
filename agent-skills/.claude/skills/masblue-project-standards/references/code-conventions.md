# Code conventions (extracted from the codebase)

Every rule here was observed in the existing code or enforced by `pyproject.toml`. Where the
code is inconsistent, that is called out instead of papered over.

## Contents

1. [Tooling rules enforced automatically](#1-tooling-rules-enforced-automatically)
2. [Module layout and naming](#2-module-layout-and-naming)
3. [Docstrings and comments](#3-docstrings-and-comments)
4. [Typing](#4-typing)
5. [Dependency injection and wiring](#5-dependency-injection-and-wiring)
6. [Transactions and persistence](#6-transactions-and-persistence)
7. [Schemas (Pydantic)](#7-schemas-pydantic)
8. [Errors](#8-errors)
9. [Logging](#9-logging)
10. [Configuration](#10-configuration)
11. [Streaming (SSE)](#11-streaming-sse)
12. [Small idioms](#12-small-idioms)

---

## 1. Tooling rules enforced automatically

- **ruff** lint rule sets: `E, F, I, UP, B, ASYNC, SIM`. Line length **100**, target `py312`,
  double quotes, space indent. `ASYNC` means: no blocking calls (`time.sleep`, sync file or
  network I/O) inside `async def`.
- **mypy**: `strict = true` with the `pydantic.mypy` plugin, checking package `app` only
  (migrations excluded; tests are outside the configured package, but test functions and fixtures are still annotated).
- **pre-commit** runs `ruff --fix` and `ruff-format`.
- `# type: ignore[...]` is used sparingly and always with the specific error code. It appears for
  FastAPI exception-handler registration and for injecting test doubles. Never use a bare
  `# type: ignore`.

## 2. Module layout and naming

```
src/app/
  main.py            application factory (create_app), lifespan, middleware, router registration
  api/deps.py        composition root: auth, services, repositories, provider caches
  api/v1/<area>.py   routers; registered in api/v1/router.py with prefix and tags
  core/              config, logging, middleware, exceptions, security
  db/session.py      engine + request-scoped session
  llm/               provider abstraction, factory, concrete providers
  models/            SQLAlchemy ORM (one entity per file, exported in models/__init__.py)
  repositories/      <entity>_repo.py -> <Entity>Repository
  schemas/           Pydantic request/response models, grouped by domain (chat.py, common.py)
  services/          <name>_service.py -> <Name>Service
  seeders/           command-line seeders run with python -m app.seeders.<name>
migrations/versions/ NNNN_slug.py (hand-numbered)
tests/unit, tests/integration, tests/conftest.py
```

- Modules are `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE`; module-private
  constants and helpers get a leading underscore (`_OPENAI_COMPATIBLE_PROVIDERS`, `_request_id`).
- Instance attributes that are injected collaborators are private: `self._session`,
  `self._provider`, `self._conversations`.
- Every package has an `__init__.py` with a one-line docstring. Only `llm/__init__.py` and
  `models/__init__.py` re-export names (with `__all__`); keep other `__init__` files empty of logic.
- Imports are absolute and grouped stdlib / third-party / first-party (`app.*`) by ruff.
  Use `if TYPE_CHECKING:` plus string annotations to break ORM import cycles
  (see `models/conversation.py`).

## 3. Docstrings and comments

- Module docstring: one line describing purpose. Class and function docstrings: one imperative
  sentence ending with a period ("Return...", "Create...", "Fetch...", "Verify..."). There are no
  multi-section Args/Returns blocks in this codebase; do not introduce them.
- Test functions: docstring starting with "Verify ...". Tiny private test doubles may skip method
  docstrings but keep a class docstring.
- Comments explain *why*, never *what*. Good examples from the code:
  - `# Request-scoped sessions prevent concurrent requests sharing transaction state.`
  - `# This is deliberately the first yielded event, before the provider request starts.`
- Future work is marked `# TODO(phase-2): ...` so it can be grepped.
- Known gap: `ModelRepository.__init__` has no docstring (the only one in `src/`). Do not copy that.

## 4. Typing

```python
async def get_for_user(self, conversation_id: UUID, user_id: str) -> Conversation | None: ...
def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]: ...
```

- `X | None` and builtin generics; `AsyncIterator` / `Sequence` from `collections.abc`.
- Small immutable value objects are `@dataclass(frozen=True, slots=True)` (`ChatMessage`,
  `ModelConfig`, `ResolvedLLM`). Closed vocabularies use `Literal[...]` (`MessageRole`).
- Do not reuse one variable name for an optional and a non-optional value. That is the cause of both
  existing mypy errors (`conversation = await repo.add(...)` then
  `conversation = await repo.get_for_user(...)`). Use two names or restructure.

## 5. Dependency injection and wiring

- Routes declare dependencies with `Annotated[...]`:

```python
service: Annotated[ChatService, Depends(get_chat_service)],
user: Annotated[CurrentUser, Depends(get_current_user)],
```

- `api/deps.py` is the only place that builds repositories, services, and providers. Services receive
  their collaborators through `__init__` (constructor injection), never by importing a global.
- **Order matters.** FastAPI resolves dependencies in the order they appear in the signature. Put
  `user: ... Depends(get_current_user)` **before** any dependency that touches the database so that
  unauthenticated requests are rejected before any query runs.
- Expensive clients (LLM providers) are cached in module-level dicts keyed by their config tuple and
  closed in the app lifespan (`dispose_llm_clients`). Follow that pattern for any new long-lived
  client; do not create one per request.
- Placeholder dependencies are explicit about being placeholders (`rate_limit_placeholder`).

## 6. Transactions and persistence

- SQLAlchemy 2.0 style only: `select(...)`, `await session.execute(...)`, `.scalar_one_or_none()`,
  `.scalars().all()`. No legacy `Query` API.
- **Repositories `flush()`, services `commit()`.** A repository `add` does
  `session.add(obj); await session.flush(); return obj`. The service commits once the whole use
  case succeeded (see `ChatService._prepare_turn`).
- Repositories return ORM objects or plain tuples (`tuple[list[Message], int]` for a page plus
  total). Pagination uses `offset`/`limit` keyword-only args; the service converts `page` to offset.
- Ordering is always deterministic: add a tiebreaker (`.order_by(Message.created_at, Message.id)`).
- Ownership is enforced in the query (`get_for_user(conversation_id, user_id)`), not afterwards.
- ORM models: `Mapped[...]` + `mapped_column`; compose `UUIDPrimaryKey`, `TimestampMixin`, `Base`;
  foreign keys use `schema_qualified("table")` (see the migrations skill).

## 7. Schemas (Pydantic)

- Request models constrain input with `Field(...)` (`message: str = Field(min_length=1,
  max_length=20_000)`). Query params use `Annotated[int, Query(ge=1, le=100)]`.
- Response models that read from ORM objects set `model_config = ConfigDict(from_attributes=True)`
  and are built with `Model.model_validate(orm_obj)`.
- Identity from the JWT is the frozen `CurrentUser(user_id: str, claims: dict)`. `user_id` is a
  string because the Node `sub` claim is not guaranteed to be a UUID.
- Routes declare `response_model=` and a return annotation.

## 8. Errors

- Base class `AppError(code, message, status_code)` in `core/exceptions.py`. Subclasses fix their own
  code, message, and status (`UnauthorizedError`, `ServiceConfigurationError`, `LLMProviderError`).
  One-off errors may be raised directly: `AppError("CONVERSATION_NOT_FOUND", "Conversation not found", 404)`.
- Codes are `UPPER_SNAKE`. Messages never include internal detail, key material, or user input.
- Wrap third-party failures and re-raise with the cause chained:
  `raise LLMProviderError() from exc`.
- Handlers in `register_exception_handlers` produce the uniform envelope and echo `X-Request-ID`.
  Validation errors do **not** echo submitted values. Unexpected exceptions are logged and returned as
  a generic 500.
- Config problems (`missing key`, `unknown provider`) raise `ServiceConfigurationError` with no detail,
  by design.

## 9. Logging

```python
logger = structlog.get_logger(__name__)
logger.error("llm_generate_failed", provider=self.provider_name, model=config.model,
             error_type=type(exc).__name__)
```

- Event name is a short `snake_case` string; context goes in keyword fields.
- `RequestContextMiddleware` binds `request_id` via `structlog.contextvars`, so do not pass it
  manually inside request handling (the SSE generator and the global handler do, because they run
  outside that context).
- The access log is **metadata only** (method, path, status, duration). Do not log request bodies,
  prompts, completions, tokens, or credentials.

## 10. Configuration

- All config is `Settings(BaseSettings)` in `core/config.py`: snake_case fields map to UPPER_CASE env
  vars, loaded from `.env`, `extra="ignore"`, case-insensitive. Constraints use `Field(gt=0, le=...)`.
- Derived values use `@model_validator(mode="after")` (database URL) or `@field_validator`.
- Read settings via `get_settings()` (cached) or `Depends(get_settings)`. Never call `os.getenv`.
- Optional "intent" model settings fall back to the chat settings (`intent_llm_x or llm_x`).
- Adding a setting touches four places: `Settings`, `.env.example`, `docker-compose.yml`
  (if the container needs it), README configuration section.

## 11. Streaming (SSE)

- Frames are `f"data: {json.dumps(event)}\n\n"` (note `json.dumps` default spacing, so the frame is
  `data: {"token": "x"}` with a space; tests assert that exact text).
- Order today: first `{"conversation_id": ...}`, then `{"token": ...}` frames, errors as
  `{"error": {"code", "message"}}`, and a final `data: [DONE]` emitted from `finally`.
- Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Errors during streaming cannot change the HTTP status (already 200), so they are sent as a frame.
- The architecture doc wants `type`-tagged frames (`token` / `done` with citations). That is not
  implemented. Do not change the frame shape without asking, because the React client depends on it.

## 12. Small idioms

- f-strings for formatting; `str | int` isinstance checks via `isinstance(x, str | int)`.
- Safe defaults over exceptions at boundaries (`content or ""`), explicit exceptions at invariants.
- Provider kwargs omit unset optional values (`if config.max_tokens is not None: ...`).
- Keyword-only parameters (`*,`) for anything beyond one or two obvious positionals.
- Env-driven behaviour differences are `APP_ENV`-based (docs/OpenAPI disabled in production).
