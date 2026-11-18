# Insurance Chat Service

Async FastAPI service for internal policy Q&A, form-field help, and document ingestion. Policy
content is retrieved only within the supplied `user_id`; provider prompts receive only those
authorized excerpts and structured facts.

## Setup

Requirements: Python 3.12, Docker Compose, and a PostgreSQL database with the pgvector extension.

```bash
cp .env.example .env
# Set INTERNAL_API_KEY, LLM_MODEL, and any provider credentials in .env.
docker compose up --build
```

Compose starts PostgreSQL, applies Alembic migrations, and starts the API on port 8000. For local
development, start only PostgreSQL with `docker compose up postgres`, install the dev dependencies
with `pip install -e ".[dev]"`, apply migrations with `alembic upgrade head`, then run
`uvicorn app.main:app --app-dir src --reload`.

The internal API key must be shared only with trusted backend callers. Set `user_id` from the
authenticated caller; do not accept it directly from an untrusted client.

## Configuration

All configuration is read from environment variables (or `.env` for local development). See
[.env.example](./.env.example) for a complete example.

| Variable | Required | Purpose |
|---|---:|---|
| `APP_ENV` | No | Environment label; defaults to `development`. |
| `LOG_LEVEL` | No | JSON log threshold; defaults to `INFO`. |
| `DATABASE_URL` | Yes | Async SQLAlchemy PostgreSQL URL, normally using `postgresql+asyncpg`. |
| `INTERNAL_API_KEY` | Yes | Constant-time checked key required on every `/v1` request. |
| `CORS_ORIGINS` | No | Comma-separated exact browser origins; empty denies browser origins. |
| `RATE_LIMIT_REQUESTS` | No | Requests per client address in the configured window; defaults to 120. |
| `RATE_LIMIT_WINDOW_SECONDS` | No | Rate-limit window; defaults to 60 seconds. |
| `LLM_PROVIDER` | Yes | `openai`, `anthropic`, or `openai_compatible`. |
| `LLM_MODEL` | Yes | Model name for the selected LLM provider. |
| `LLM_API_KEY` | Provider-dependent | Secret key for OpenAI/Anthropic or an authenticated compatible endpoint. |
| `LLM_BASE_URL` | Compatible provider | Base URL for `openai_compatible`; include `/v1` when required by the server. |
| `LLM_TIMEOUT_SECONDS` | No | Provider request timeout; defaults to 30. |
| `LLM_MAX_RETRIES` | No | Transient provider retry count; defaults to 3. |
| `LLM_FALLBACK_PROVIDER` | No | Optional fallback provider, enabled with the fallback model. |
| `LLM_FALLBACK_MODEL` | Fallback-dependent | Model name for the fallback provider. |
| `LLM_FALLBACK_API_KEY` | Fallback-dependent | Optional compatible-provider key, otherwise required. |
| `LLM_FALLBACK_BASE_URL` | Compatible fallback | Base URL for a compatible fallback provider. |
| `LLM_MAX_TOKENS` | No | Maximum response tokens; defaults to 700. |
| `LLM_TEMPERATURE` | No | Sampling temperature; defaults to 0.2. |
| `EMBED_PROVIDER` | No | `local` (default) or `openai`. |
| `EMBED_MODEL` | Yes | Local sentence-transformer model or remote embedding model name. |
| `EMBED_API_KEY` | OpenAI embeddings | Secret key for the OpenAI embedding provider. |
| `EMBED_BASE_URL` | No | Embedding API base URL; defaults to OpenAI for the remote provider. |
| `EMBED_DIM` | No | Must match the pgvector column dimension (384 in the initial migration). |
| `RETRIEVAL_TOP_K` | No | Maximum retrieved chunks; defaults to 6. |
| `RETRIEVAL_MIN_SCORE` | No | Minimum cosine similarity for policy excerpts; defaults to 0.25. |
| `MAX_UPLOAD_BYTES` | No | Maximum PDF upload size; defaults to 20,000,000 bytes. |

## LLM providers

Switch provider by setting `LLM_PROVIDER`, `LLM_MODEL`, and the matching key/base URL, then
restarting the service. `openai_compatible` supports endpoints implementing the OpenAI chat
completions API.

To add a provider, implement `LLMProvider` in `src/app/llm/providers/`, register its constructor in
`src/app/llm/factory.py`, add its provider name and required settings validation in
`src/app/core/config.py`, and cover completion/streaming behavior with an offline fake-provider
test. The embedding-provider extension points are `EmbeddingProvider` and
`src/app/embeddings/factory.py`.

## Data boundary

The service-owned schema contains `policy_documents`, `policy_chunks`, `policy_facts`,
`field_glossary`, and `chat_audit`. Chunk and fact reads always filter by `user_id` in SQL. With no
`policy_id`, the search spans only that user's service-ingested policies; a supplied ID narrows the
same query. `policy_facts` is the structured-fact source and should be populated from the trusted
policy/coverage system by an authorized upstream integration. No assumptions about the legacy
policies/coverage tables or their ownership joins are embedded here.

The included rate limiter is process-local as a replaceable hook. Multi-worker or multi-replica
deployments should provide a shared limiter implementation (for example, backed by Redis) before
relying on a global quota.

## Ingestion

Upload a PDF with the internal key and trusted owner ID:

```bash
curl -X POST http://localhost:8000/v1/policies/POLICY-123/documents \
  -H "X-Internal-Key: $INTERNAL_API_KEY" \
  -F "user_id=USER-123" \
  -F "file=@policy.pdf"
```

The response contains a document ID and `queued` status. Poll
`GET /v1/policies/{policy_id}/documents/{document_id}?user_id=...` for `queued`, `processing`,
`ready`, or `failed`. The pipeline extracts text per page using PyMuPDF, rejects image-only/scanned
PDFs, chunks by headings (or roughly 1,000 characters with overlap), stores section/page metadata,
embeds chunks, and atomically replaces a document's old chunks when a re-ingestion succeeds.

The CLI can also ingest synchronously:

```bash
python scripts/ingest.py --user-id USER-123 --policy-id POLICY-123 policy.pdf
```

## Tests and evaluation

Unit tests use `FakeLLMProvider` and `FakeEmbeddingProvider` and make no provider network calls.
Run `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, and `mypy src`.

For tenant-isolation integration coverage, start the pgvector service and set a dedicated
`TEST_DATABASE_URL`:

```bash
docker compose up -d postgres
TEST_DATABASE_URL='postgresql+asyncpg://insurance:insurance@localhost:5432/insurance_chat' pytest -q tests/integration
```

With the API running and evaluation policies/facts loaded, run:

```bash
EVAL_USER_ID=USER-123 EVAL_POLICY_ID=POLICY-123 python tests/eval/run.py
```

The runner reads `tests/eval/questions.yaml` and prints answer accuracy, citation rate, and refusal
correctness. `EVAL_POLICY_ID` is optional when cases should search all of the user's policies.
