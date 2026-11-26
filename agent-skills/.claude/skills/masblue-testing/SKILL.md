---
name: masblue-testing
description: How to write, run, and fix tests in the Masblue AI Chat Service - pytest with pytest-asyncio auto mode, FastAPI TestClient, dependency overrides, fake services/repositories/SDK clients, signed test JWTs, SSE assertions, and testing without a database. Use this skill whenever a task adds, changes, debugs, or runs tests, whenever a test fails with a connection error or a dependency override seems ignored, or when new behaviour needs test coverage, even if the user does not mention pytest.
---

# Testing

Read `masblue-project-standards` first. Layout: `tests/unit/`, `tests/integration/`,
`tests/conftest.py`. Run `uv run pytest` (one test: `uv run pytest tests/unit/test_x.py::test_y -q`).
`asyncio_mode = "auto"`, so write `async def test_...` with no decorator.

## Know the baseline before you start

- **No database:** any request that goes through `get_chat_service` or `get_db` fails with
  `ConnectionRefusedError` (5 existing tests do). That is the environment, not your change.
- **With a migrated PostgreSQL:** 7 pass, 3 fail for pre-existing reasons (stale `conversation_id is
  None` assertion; a fake missing `close()`; an override that is bypassed). Details in
  `masblue-project-standards/references/known-issues.md`.
- Your new tests must pass **without a database**, using the patterns below. Compare before/after so you
  can show you added no failures.

## Conventions

- Plain functions, no test classes. `-> None`, typed fixtures, docstring starting with "Verify ...".
- Fakes are small classes named `_Fake<Thing>` that record the calls they receive so the test can
  assert on what the code under test passed in.
- Assert the error envelope: `response.json()["error"]["code"] == "UNAUTHORIZED"`.
- SSE: assert on exact frames. `json.dumps` adds a space: `'data: {"token": "Hi "}'`, and the stream
  ends with `data: [DONE]`.
- Inject fakes where a strict type is expected with a specific ignore:
  `Service(repo)  # type: ignore[arg-type]`.
- Never put real keys, real DB credentials, or real customer data in tests. The default JWT secret in
  `conftest.py` is test-only; reuse the `auth_headers` fixture.

## Gotcha: environment before import

`models/base.py` reads settings **at import time** to set the schema. `conftest.py` therefore sets
environment variables *before* importing anything from `app`. Keep that ordering; do not add
`from app... import` lines above the `os.environ` setup, and do not move settings reads to import time
in new modules.

## Pattern 1: route test with a fake service (no DB)

Override the service dependency, then call the route with `auth_headers`. The engine is created lazily,
so nothing connects. Full tested code: `masblue-api-feature-workflow/references/worked-example.md`
(section 7). Always add the sibling test that proves an unauthenticated call returns 401 and that the
fake was **not** called.

```python
app = create_app()
app.dependency_overrides[get_conversation_service] = lambda: fake
with TestClient(app) as client:
    response = client.get("/api/v1/conversations", headers=auth_headers)
```

Override **the dependency the route actually uses**. For the chat endpoints that is
`get_chat_service`; overriding `get_chat_llm` does nothing because `get_chat_service` calls it as a plain
function (known-issues A3).

## Pattern 2: service test with a fake repository (no DB)

Construct the service with a hand-written fake repository and call it directly; assert on the recorded
arguments and the returned values (worked-example section 8).

## Pattern 3: provider tests with a fake SDK client

Providers accept `client=`. Build a fake exposing only the attributes the provider touches
(`chat.completions.create`, or `messages.create` / `messages.stream`), then assert on the kwargs sent,
the parsed result, streamed chunks, and that an SDK connection error becomes `LLMProviderError`. Copy
`_FakeAsyncOpenAI` and `_FakeAsyncAnthropic` from `tests/unit/test_llm_providers.py`. Any fake
`LLMProvider` must implement `generate`, `stream`, **and `close`**.

## Pattern 4: factory and settings tests

Instantiate `Settings(llm_provider="...", llm_api_key="...", llm_model="...")` directly (no env needed)
and assert the resulting provider type; use `pytest.raises(ServiceConfigurationError)` for bad configs.

## Pattern 5: real-database tests

Use the `test_db_session` fixture in `tests/conftest.py` and put such tests in `tests/integration/`.
They need a migrated PostgreSQL with pgvector (`uv run alembic upgrade head`). State this requirement
in the module docstring. Do not make unit tests depend on a database.

## What good coverage looks like here

For each endpoint: success; validation error (422 with `VALIDATION_ERROR`); 401; not-found or someone
else's record returns the same 404; paging arguments reach the service. For services: each branch and
each raised `AppError`. For anything touching user data: a test that user A cannot read user B's data.
Phase 3 of the roadmap requires automated cross-tenant isolation tests; write them whenever you add
retrieval or per-user queries.

## Debugging checklist

- `ConnectionRefusedError` -> a DB-backed dependency ran; override the service or start PostgreSQL.
- Override ignored -> wrong dependency, or the code calls it directly instead of via `Depends`.
- `TypeError: Can't instantiate abstract class` -> a fake misses an abstract method.
- Import-time settings errors -> environment set too late in `conftest.py`.
- 401 test fails with a DB error -> the auth dependency is not first in the route signature.
