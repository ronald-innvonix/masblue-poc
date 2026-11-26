# Known issues and "do not copy" list

These are things in the current repo that look like conventions but are defects or drift. They were
found by reading the code and by running ruff, mypy, and pytest against the repo (with no PostgreSQL
available). Do **not** reproduce them in new code. Do not silently fix them either, unless the user
asked: mention them, and offer a fix when it is relevant to the task.

## A. Layering and correctness

### A1. A route queries the database directly
`GET /api/v1/chat/{conversation_id}/messages` in `api/v1/chat.py` injects `AsyncSession` and calls
`ConversationRepository` and `MessageRepository` itself. This contradicts the README ("Routes do not
access the database"). New read endpoints should go through a service.
*Fix when asked:* move the body into a `ConversationService.get_messages(...)` and inject the service.

### A2. The database is hit before authentication
In `POST /chat` and `POST /chat/stream` the `service: ChatService` dependency is declared before
`user: CurrentUser`. FastAPI resolves them in that order, and `get_chat_service` queries the model
registry, so an unauthenticated request touches PostgreSQL before it gets a 401.
Verified by listing the route's dependency order: `rate_limit_placeholder`, `get_chat_service`,
`get_current_user`.
*Fix when asked:* declare `user` first, or add `Depends(get_current_user)` at router level.
New routes must declare the auth dependency first.

### A3. `get_chat_service` calls a dependency as a plain function
Inside `get_chat_service`, `resolved = get_chat_llm(settings)` is a direct call, not `Depends`.
Consequence: `app.dependency_overrides[get_chat_llm] = ...` has **no effect** on the chat endpoints.
Verified: after fixing an unrelated problem in the test fake, `/chat` still returned the real stub
reply instead of the overridden provider's reply. Override `get_chat_service` in tests instead, or
refactor so the provider arrives through `Depends`.

### A4. Business logic lives in `api/deps.py`
`get_chat_service` does a registry lookup, builds a cache key, and chooses a provider. That is
service/factory logic in the composition root. Keep new `get_*` functions to pure wiring.

## B. Test and lint baseline (as of the uploaded zip)

| Check | Result |
|---|---|
| `ruff check .` | passes |
| `ruff format --check .` | passes (54 files) |
| `mypy` (strict) | **2 errors**, both from reusing one variable name for `X \| None` and `X` (`services/chat_service.py` line ~56, `api/deps.py` line ~131) |
| `alembic upgrade head` / `downgrade base` / `upgrade head` | passes on PostgreSQL 16 + pgvector; single head `0005_message_model` |
| `alembic check` (model vs migration drift) | **fails**: see section E1 |
| `pytest`, no database | **5 failed, 5 passed**; all 5 failures are `ConnectionRefusedError` to the DB |
| `pytest`, migrated PostgreSQL | **3 failed, 7 passed** (below) |

The 3 failures with a database:

1. `test_chat.py::test_chat_returns_stubbed_response` asserts `conversation_id is None`. Stale: the
   service now persists the conversation and returns a real UUID.
2. `test_llm_providers.py::test_chat_and_stream_endpoints_use_resolved_provider` and
3. `test_llm_providers.py::test_chat_and_stream_endpoints_handle_provider_errors` both build
   `_FakeProvider`, which does not implement the abstract `close()` that `LLMProvider` now
   requires (`TypeError` at instantiation). Even after adding `close()`, they still fail because of
   A3: the override is bypassed and the stub provider answers.

These tests are labelled "unit" and the README says the chat tests need no database, but every request
through `get_chat_service` queries the model registry, so without PostgreSQL they fail early.
Treat all of this as pre-existing. Do not make it worse, and do not delete or weaken the tests.

Minor: pytest-asyncio warns that `asyncio_default_fixture_loop_scope` is unset; adding
`asyncio_default_fixture_loop_scope = "function"` to `[tool.pytest.ini_options]` silences it.

## C. Documentation drift

- `README.md` and `NODE_JS_DEVELOPER_GUIDE.md` say chat is stub-only, nothing is persisted, and no
  real provider exists. In reality the code has OpenAI, Grok, Gemini, OpenAI-compatible, and
  Anthropic providers, a factory, a DB-backed model registry, and message persistence. The guide
  also says `AnthropicProvider` returns stub text, which is wrong.
- The guide's Docker Compose section describes older defaults; `docker-compose.yml` and `.env.example`
  use different database names/ports. Check the files, not the prose.
- Architecture doc vs code (target vs reality):
  - SSE frames: doc says `{"type": "token" | "done", ...}`; code emits untyped `{"token": ...}`.
  - `conversations.user_id`: doc shows `uuid`; migration 0003 changed it to a string on purpose.
  - Request `intent` and response `citations`/`intent` fields are specified but not in `ChatRequest`/`ChatResponse`.
  - `EMBEDDING_*` settings and the embedding provider/factory do not exist yet.
  - Anonymous access to Feature 1 is specified, but every chat route currently requires a JWT.

## D. Data and security

- **`models.api_key` is stored in plain text** (`String(512)`), and `get_chat_service` reads it from
  the row to build a provider. Never log it, never return it in a schema, and do not extend this
  pattern (for example by adding more secrets to the table) without raising encryption or a secret
  manager with the user.
- `tests/conftest.py` and `NODE_JS_DEVELOPER_GUIDE.md` contain real-looking local DB credentials, and
  the uploaded archive included a `.env`. Never copy these. Use placeholders such as
  `postgresql+asyncpg://user:password@localhost:5432/dbname`.
- `EmbeddingModel` (the ORM class) maps to the `models` table and stores both `conversation` and
  `embedding` model rows. The name is a leftover from before the table was renamed. Keep using it as
  is; do not rename without a migration plan.

## E. Migrations and infrastructure

### E1. Autogenerate wants to rename three indexes (verified)
`alembic check` reports drift on `ix_conversations_user_id`, `ix_messages_conversation_id`, and
`ix_messages_model_id`. The ORM naming convention `"ix": "ix_%(column_0_label)s"` in `models/base.py`
yields schema-prefixed names (`ix_ai_chat_conversations_user_id`) while the migrations created
unprefixed names. Result: every `alembic revision --autogenerate` includes unrelated drop-and-recreate
index operations. Until fixed, **delete those unrelated index operations from any autogenerated
migration**. Verified fix: change the convention to `"ix": "ix_%(table_name)s_%(column_0_name)s"`;
`alembic check` then reports "No new upgrade operations detected" (offer this to the user; do not
apply it unasked).

### E2. Docker Compose database image probably lacks pgvector (not run here)
`docker-compose.yml` uses the stock `postgres:16.8` image, but migration `0002` runs
`CREATE EXTENSION IF NOT EXISTS vector`. The official Postgres image does not bundle pgvector, so
`alembic upgrade head` in the Compose stack will likely fail. A pgvector-enabled image such as
`pgvector/pgvector:pg16` is the usual fix. Flag it if the user reports Compose startup errors.

### E3. Doubled check-constraint name in migration 0001 (verified)
The database contains `ck_messages_ck_messages_message_role`; the ORM expects
`ck_messages_message_role`. Migration 0001 passed an already-prefixed name and the naming convention
prefixed it again. `alembic check` does not compare check constraints, so it is invisible. Never
repeat it: pass the bare name (see the migrations skill). Fixing it needs a new migration that
renames the constraint; offer, do not apply unasked.

## F. Naming inconsistency

Table names are mixed: plural `conversations`, `messages`, `models` versus singular
`manual_document`, `document_chunk`, `document_vector_status` (the singular ones follow the
architecture doc). Do not rename existing tables. For a *new, unplanned* table default to plural
`snake_case`, and tell the user which you chose. For tables the architecture doc names, use the
doc's name.

## G. Style slips (do not replicate)

- `ModelRepository.__init__` has no docstring (every other function and class in `src/` has one).
- `tests/conftest.py` sets environment defaults before importing `app`. That ordering is deliberate
  (see the testing skill), but the hard-coded credential defaults are not a pattern to repeat.
