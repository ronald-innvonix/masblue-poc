# Python/FastAPI Codebase Guide for Node.js Developers

## What this project is

This repository is an asynchronous FastAPI microservice for AI chat. Conceptually, it is comparable to a small Express/FastAPI service:

| FastAPI/Python concept | Node.js/Express equivalent |
|---|---|
| `FastAPI()` | Express app |
| `APIRouter` | Express router |
| Pydantic model | Zod/Joi or a request DTO |
| Dependency (`Depends`) | Middleware or an injected service |
| SQLAlchemy async session | Prisma/Sequelize/pg connection/session |
| Alembic | Prisma Migrate or Knex migrations |
| `uv` | npm/pnpm/bun |
| Uvicorn | Node HTTP server adapter |
| Gunicorn + Uvicorn workers | PM2/multiple Node worker processes |

The app currently returns stubbed chat responses. Database persistence exists in the models/repositories, but the chat service does not yet save messages.

## Repository structure

- `src/app/main.py` — application factory, middleware, lifespan, and router registration.
- `src/app/api/v1/` — HTTP routes.
- `src/app/api/deps.py` — dependency injection, JWT authentication, repositories, and services.
- `src/app/core/config.py` — environment configuration.
- `src/app/core/security.py` — Node-issued JWT validation.
- `src/app/services/` — use-case/application logic.
- `src/app/repositories/` — SQLAlchemy database operations.
- `src/app/models/` — SQLAlchemy ORM entities.
- `src/app/schemas/` — Pydantic request/response types.
- `src/app/llm/` — LLM abstraction and the current stub provider.
- `src/app/db/session.py` — async engine and session lifecycle.
- `migrations/versions/` — Alembic database migrations.
- `tests/` — pytest unit and integration tests.
- `.env` — local environment variables.
- `docker-compose.yml` — local container services.
- `pyproject.toml` — Python version, dependencies, and tool configuration.
- `Makefile` — convenient wrappers for common commands.

## Prerequisites

Use:

- Python 3.12
- `uv` for dependency management
- PostgreSQL 16, preferably already running
- Docker and Docker Compose if using containers

Do not install the project with plain `pip` unless it is necessary; this repository is configured around `uv` and includes a pinned `uv.lock`.

## Database connection

The active local `.env` configuration is:

```dotenv
DB_HOST=localhost
DB_PORT=5434
DB_NAME=force_development_db_07102026
DB_USERNAME=ronald
DB_PASSWORD=ronald
DATABASE_URL=
DB_SCHEMA=ai_chat
```

A secret should not be committed to Git in normal projects. This guide records the current local-development values supplied for this repository.

`[src/app/core/config.py](/home/ronald/Desktop/POC/insurance-chat-service/src/app/core/config.py)` loads `.env` automatically. If `DATABASE_URL` is empty, it builds:

```text
postgresql+asyncpg://ronald:ronald@localhost:5434/force_development_db_07102026
```

`asyncpg` is the async PostgreSQL driver. The URL is equivalent to a PostgreSQL connection string used by Node libraries, but with SQLAlchemy's `+asyncpg` dialect prefix.

An explicit `DATABASE_URL` takes precedence over `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, and `DB_PASSWORD`.

At application startup, `[src/app/db/session.py](/home/ronald/Desktop/POC/insurance-chat-service/src/app/db/session.py)`:

1. Creates one SQLAlchemy async engine.
2. Enables `pool_pre_ping` to discard invalid pooled connections.
3. Sets PostgreSQL `search_path` to `ai_chat`.
4. Creates an async-session factory.
5. Disposes the engine during graceful shutdown.

This means SQLAlchemy uses the `ai_chat` schema for service tables. It is intended to keep chat tables separate from the existing Node application's tables.

## Database schema and migrations

The first migration creates:

- `ai_chat.conversations`
- `ai_chat.messages`

It also creates indexes and an `ON DELETE CASCADE` relationship from messages to conversations.

Alembic reads the database URL and schema from application settings. Apply migrations with:

```bash
cd /home/ronald/Desktop/POC/insurance-chat-service
uv run alembic upgrade head
```

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Important: `user_id` is currently stored as a UUID. Verify that the existing Node application's user ID has the same type before production integration.

## Run the project locally

### 1. Install dependencies

```bash
cd /home/ronald/Desktop/POC/insurance-chat-service
uv sync --group dev
```

This creates a virtual environment and installs runtime plus development dependencies.

### 2. Ensure PostgreSQL is reachable

PostgreSQL must exist at:

```text
Host: localhost
Port: 5434
Database: force_development_db_07102026
User: ronald
Password: ronald
```

A PostgreSQL role and database can be created with the appropriate database administration permissions.

### 3. Apply migrations

```bash
uv run alembic upgrade head
```

### 4. Start the API

```bash
uv run uvicorn app.main:app --reload
```

The API starts at:

- Health: <http://localhost:8000/api/v1/health>
- Database readiness: <http://localhost:8000/api/v1/ready>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

You can also use the Makefile shorthand:

```bash
make install
make migrate
make dev
```

For Windows, run the underlying `uv run ...` commands directly because GNU `make` may not be installed.

## Docker Compose

The documented command is:

```bash
docker compose up --build
```

However, the current Compose PostgreSQL service is configured for the earlier local defaults: database `ai_chat`, user `ai_chat`, and host port `5432`. At present, the app container also receives `DB_HOST=localhost` and `DB_PORT=5434`, while this database is running inside the container. In this configuration, `localhost` means the app container itself, not the PostgreSQL container.

Therefore, for the supplied database on host port `5434`, prefer running PostgreSQL outside Docker and the Python app natively as described above.

To run the original `ai_chat` development stack reliably in Docker, Compose should use:

```yaml
DB_HOST: postgres
DB_PORT: 5432
DB_NAME: ai_chat
DB_USERNAME: ai_chat
DB_PASSWORD: local-dev-only
```

It is also possible to point the app container at the host's database, but that requires Docker host networking appropriate to the operating system and is not the safest default.

## API routes

All application routes are under `/api/v1`.

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/health` | No | Process liveness; does not query PostgreSQL |
| `GET` | `/api/v1/ready` | No | Runs `SELECT 1` against PostgreSQL |
| `POST` | `/api/v1/chat` | Bearer JWT | Returns a stub chat response |
| `POST` | `/api/v1/chat/stream` | Bearer JWT | Returns a stubbed server-sent event stream |

Example chat request:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H 'Authorization: Bearer YOUR_NODE_APP_JWT' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","conversation_id":null}'
```

Example response:

```json
{
  "conversation_id": null,
  "message": "This is a stubbed AI response."
}
```

The streaming endpoint accepts the same body and responds as `text/event-stream`:

```text
data: {"token":"This "}

data: {"token":"is "}

data: [DONE]

```

## JWT integration with Node.js

This service does not issue or exchange tokens. It validates the JWT issued by the Node application and returns `sub` as `CurrentUser.user_id`.

For an HMAC-signed token, configure:

```dotenv
JWT_ALGORITHM=HS256
JWT_SECRET=the-same-secret-used-by-the-node-app
JWT_PUBLIC_KEY=
```

For an RSA/ECDSA public-key token, configure:

```dotenv
JWT_ALGORITHM=RS256
JWT_SECRET=
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
```

The service has a strict algorithm allow-list derived from `JWT_ALGORITHM` and requires a `sub` claim. It does not choose a signing algorithm from the token.

Send the Node-issued token unchanged in the `Authorization: Bearer <token>` header.

## Request flow

A chat request follows this structure:

```text
HTTP route
  -> FastAPI/Pydantic validates JSON
  -> Bearer middleware/dependency validates JWT
  -> ChatService handles the use case
  -> AnthropicProvider currently returns stub text
  -> Pydantic serializes and returns the response
```

Repository classes are not used by the current chat endpoint. Database operations are included for future persistence and used by `/ready`.

The intended architecture is:

```text
Route -> Service -> Repository -> SQLAlchemy -> PostgreSQL
               -> LLM provider
```

## Configuration reference

- `APP_ENV` — `development`, `test`, or `production`; production hides Swagger/OpenAPI.
- `LOG_LEVEL` — logging verbosity.
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` — PostgreSQL connection components.
- `DATABASE_URL` — optional complete connection string; takes precedence.
- `DB_SCHEMA` — service-owned schema, default `ai_chat`.
- `JWT_SECRET` — HMAC signing secret.
- `JWT_PUBLIC_KEY` — public key for asymmetric JWT verification.
- `JWT_ALGORITHM` — JWT algorithm, such as `HS256` or `RS256`.
- `CORS_ORIGINS` — comma-separated browser origins.
- `LLM_PROVIDER` — reserved provider selection setting.
- `LLM_API_KEY` — future provider API key.
- `LLM_MODEL` — future provider model name.
- `LLM_TIMEOUT_SECONDS` — future provider timeout.
- `RATE_LIMIT_PER_MINUTE` — reserved value; enforcement is not implemented yet.

## Testing and code quality

Run targeted/all tests:

```bash
uv run pytest
```

Lint:

```bash
uv run ruff check .
```

Format:

```bash
uv run ruff format .
```

Check types:

```bash
uv run mypy
```

The Makefile equivalents are:

```bash
make test
make lint
make format
```

The chat tests use FastAPI's test client and a signed test JWT. They do not require a real LLM or live database. The readiness test requires database availability.

## Current limitations

- Chat responses are deterministic stub text.
- Conversation and message repositories exist, but the chat service does not persist chat history.
- No real Anthropic integration is implemented despite the provider name.
- Rate limiting is a placeholder.
- RAG, tool calling, summarization, usage/cost tracking, and Redis caching are future work.
- Docker Compose's database defaults conflict with the supplied external database settings; native local execution is recommended for the current setup.

## Production deployment notes

- Provide secrets through a secret manager or deployment environment variables.
- Do not include `.env` in a container image or commit it to Git.
- Use a restricted PostgreSQL role, preferably scoped to `ai_chat`.
- Run migrations as a separate deployment job with migration permissions.
- Run the app with Gunicorn/Uvicorn workers in the production image.
- Terminate TLS at the platform/load balancer and forward the original Node JWT unchanged.
- Disable Swagger UI in production (`APP_ENV=production`).
