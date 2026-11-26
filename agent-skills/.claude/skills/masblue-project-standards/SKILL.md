---
name: masblue-project-standards
description: Coding standards, tooling, architecture layering, and definition-of-done for the Masblue AI Chat Service (Python 3.12, FastAPI, async SQLAlchemy, PostgreSQL + pgvector, uv, ruff, mypy strict, pytest). Use this skill whenever you write, modify, review, refactor, or explain ANY code, config, migration, or test in this repository, even for small changes, and before running lint, type-check, test, or migration commands. Also use it for questions like "how do we do X here", project structure, naming, docstrings, error handling, logging, settings, or which command to run.
---

# Masblue AI Chat Service: project standards

An async FastAPI microservice that adds AI chat to the existing Masblue insurance portal
(React + Node.js + PostgreSQL). It validates JWTs issued by the Node backend, never issues
tokens, and owns only the `ai_chat` PostgreSQL schema.

## Which source to trust

When sources disagree, trust them in this order, and tell the user about the conflict instead
of silently picking one:

1. **The code and tool config** (`pyproject.toml`, `.pre-commit-config.yaml`): what actually runs.
2. **`docs/MASBLUE_AI_POC_ARCHITECTURE.md`**: the *target* design. Much of it is not built yet
   (see the `masblue-ai-architecture` skill for what exists versus what is planned).
3. **`README.md` and `NODE_JS_DEVELOPER_GUIDE.md`**: partly stale. They still describe stub-only
   chat with no persistence, but the code now has real providers and saves messages.

## Stack and tooling

Python 3.12 only. FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 async + asyncpg,
Alembic, structlog, PyJWT, pgvector, httpx, `openai` and `anthropic` SDKs, Gunicorn with Uvicorn
workers. Dev tools: **uv**, **ruff 0.11.6**, **mypy 1.15 (strict + pydantic plugin)**,
pytest + pytest-asyncio (`asyncio_mode = "auto"`). Versions are pinned in `pyproject.toml` and
`uv.lock`.

| Action | Command |
|---|---|
| Install | `uv sync --group dev` |
| Run API | `uv run uvicorn app.main:app --reload` |
| Test | `uv run pytest` |
| Lint + types | `uv run ruff check .` then `uv run mypy` |
| Format | `uv run ruff format .` |
| Migrate | `uv run alembic upgrade head` |
| New migration | `uv run alembic revision --autogenerate -m "..."` (then rename, see migrations skill) |
| Add dependency | `uv add <pkg>` or `uv add --group dev <pkg>` |

Use `uv` for everything. Do not use `pip install`, and do not hand-edit `uv.lock`; the lock file
is what makes builds reproducible (the Dockerfile runs `uv sync`).

## Layering: the rule that matters most

```
Route  ->  Service  ->  Repository  ->  SQLAlchemy  ->  PostgreSQL
              \-> LLMProvider (via llm/ factory)
```

| Layer | Folder | Does | Never does |
|---|---|---|---|
| Route | `api/v1/` | Parse request, depend on auth, call **one** service, shape the response | Touch the DB, call SDKs, hold business rules |
| Service | `services/` | Implement the use case; **own the transaction** (`session.commit()`); raise `AppError` subclasses | Import FastAPI or know about HTTP |
| Repository | `repositories/` | All SQL; takes an `AsyncSession`; **`flush()` only, never `commit()`** | Contain business decisions |
| Model / Schema | `models/`, `schemas/` | ORM tables / Pydantic API shapes | Leak ORM objects out of routes (map with `model_validate`) |
| Wiring | `api/deps.py` | The only place that constructs services, repositories, and providers | |

Why it matters: thin routes are trivially testable with a fake service; transaction boundaries
stay at the use case; swapping a provider or query touches one file.

## Conventions at a glance

Full detail and examples are in `references/code-conventions.md`. Read it before writing new code.

- Every module, class, function, and method has a **one-line docstring** (imperative, ends with a
  period). Modules open with a docstring too. Tests start theirs with "Verify ...".
- Modern typing only: `X | None`, `list[str]`, `collections.abc`. Every function is fully annotated
  (mypy strict). No `Optional`, no `typing.List`.
- Absolute imports (`from app.x import y`), ruff-sorted; double quotes; 100-column lines.
- Names: `<entity>_repo.py` / `<Entity>Repository`, `<name>_service.py` / `<Name>Service`,
  `<name>_provider.py` / `<Name>Provider`. Private attributes use a leading underscore.
- Dependencies are `Annotated[T, Depends(fn)]` and live in `api/deps.py` as `get_*` functions.
- Errors: raise `AppError(code, message, status)` (or a subclass). Messages are safe for clients.
  The response envelope is `{"error": {"code", "message", "request_id"}}`.
- Logging: `structlog.get_logger(__name__)` with snake_case event names and key/value fields.
  **Never log message text, tokens, API keys, or request bodies**; log `error_type=type(exc).__name__`.
- Config comes only from `Settings` (`core/config.py`, validated, env-backed). No `os.getenv`.
- Scope every user-owned query by user (`get_for_user`) and return the same 404 whether a record is
  missing or owned by someone else, so existence is not leaked.

## Definition of done

Run all four and fix anything your change caused before saying the work is finished:

```
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Also check, as relevant:

- [ ] New or changed behaviour has tests (see `masblue-testing`).
- [ ] Model change has a migration (see `masblue-database-migrations`).
- [ ] New setting is added in **all** of: `Settings`, `.env.example`, `docker-compose.yml`
      (if the container needs it), and the README configuration section.
- [ ] No secrets, real credentials, or customer data in code, tests, logs, or commit messages.

Be honest about the baseline: this repo does not start clean. Two mypy errors, a failing
`alembic check`, and failing tests (5 without a database, 3 with one) already exist (details in
`references/known-issues.md`). Report them as pre-existing instead of hiding them or "fixing" them
unasked, and make sure your own change adds no new ones.

## Other skills in this set

| When the task is about... | Use |
|---|---|
| Adding or changing an endpoint, service, repository, or schema | `masblue-api-feature-workflow` |
| ORM models, Alembic migrations, schema changes | `masblue-database-migrations` |
| LLM providers, the factory, model registry, streaming | `masblue-llm-providers` |
| Writing or fixing tests | `masblue-testing` |
| RAG, intent routing, citations, tenant isolation, roadmap features | `masblue-ai-architecture` |

## Safety

- Do not open or print `.env`. Use `.env.example` for variable names.
- Do not copy credentials from `.env`, `NODE_JS_DEVELOPER_GUIDE.md`, or `tests/conftest.py` into new
  code, docs, or examples. Use obvious placeholders.
- Before adding anything that touches the `models` table's `api_key` column, read
  `references/known-issues.md` (it is stored unencrypted).
