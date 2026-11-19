# AI Chat Service

An async FastAPI microservice scaffold intended to sit alongside an existing
React/Node.js/PostgreSQL application. It validates the Node backend's JWTs and
owns only its tables in the PostgreSQL `ai_chat` schema. Chat responses and
streamed tokens are stubs; no vendor LLM or chat persistence is implemented yet.

## Architecture

```text
React frontend ───────┐
                      ├──> /api/v1 (FastAPI routes)
Existing Node API ────┘             │
        issues JWTs                 ├── Depends: JWT validation
                                    v
                               Chat service ───> LLMProvider (stub)
                                    │
                                    v
                         Repositories (async SQLAlchemy)
                                    │
                                    v
                         PostgreSQL schema: ai_chat
```

Routes do not access the database. Services contain the use-case boundary,
repositories own database access, and the `LLMProvider` abstraction isolates
provider integrations from chat behavior.

## Local setup

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and PostgreSQL (or
Docker Compose).

```sh
cp .env.example .env
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The local database URL in `.env.example` targets PostgreSQL on `localhost`.
Alternatively, run the full local stack with Docker Compose as described below.
The development JWT secret is a placeholder; replace it with a secret/key that
matches the existing Node issuer before testing authenticated routes.

## Run with Docker Compose

```sh
docker compose up --build
```

Compose starts PostgreSQL, waits for its health check, applies this service's
migrations, and starts the API. The liveness endpoint is
<http://localhost:8000/api/v1/health>. Set `POSTGRES_PASSWORD` and `JWT_SECRET`
in a local `.env` file to override the local-only defaults. This compose file is
for development only; production deployments should provide secrets via their
secret manager and run the image with an appropriately restricted database role.

The production image uses Gunicorn with Uvicorn workers. The compose service
overrides that command with Uvicorn reload for local development.

## Migrations

```sh
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

Alembic creates and manages only the configured `DB_SCHEMA` (default `ai_chat`).
The migration environment sets that schema for the metadata and Alembic version
table; it does not inspect or alter the Node application's tables. If this
service later needs read access to existing application tables, give it a
separate read-only PostgreSQL role and keep those tables out of its migrations.

`user_id` is currently a UUID to match a common existing-app ID type. Confirm
the Node application's actual user ID type before connecting real data; update
the model/migration together if it differs.

## Tests and quality checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The health and chat tests use FastAPI's test client. Chat tests inject a signed
test JWT; they do not require a live database or LLM.

## Calling from React or Node

Either call the service directly from React (configure `CORS_ORIGINS`) or have
the Node backend proxy requests. Forward the Node-issued JWT unchanged as a
Bearer token. Configure `JWT_SECRET` for a shared HMAC key, or `JWT_PUBLIC_KEY`
and `JWT_ALGORITHM` for public-key verification. This service validates tokens
only; it does not issue them.

```http
POST /api/v1/chat
Authorization: Bearer <node-issued-jwt>
Content-Type: application/json

{"message":"Hello","conversation_id":null}
```

The stub response is JSON containing `conversation_id` and `message`. Streaming
uses the same request shape at `POST /api/v1/chat/stream` and returns
`text/event-stream` SSE frames with a `token` field, followed by `[DONE]`.
Clients should treat the streamed content as temporary placeholder output.

`GET /api/v1/health` is a liveness probe and does not contact PostgreSQL.
`GET /api/v1/ready` performs a database readiness check. Interactive docs are
available at `/docs` outside production and disabled when `APP_ENV=production`.

## Configuration

All runtime configuration is environment-based; see `.env.example` for the
complete variable list. `RATE_LIMIT_PER_MINUTE` is included as the future limit
configuration, but enforcement is intentionally a placeholder. Use a shared
Redis-backed limiter before scaling beyond one process.

Future work is marked in code with `TODO(phase-2)` (persistence, Redis rate
limiting, RAG/tool calling, summarization, and usage/cost tracking).
