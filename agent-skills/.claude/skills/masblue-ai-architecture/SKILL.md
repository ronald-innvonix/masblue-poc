---
name: masblue-ai-architecture
description: Product and architecture context for the Masblue insurance-portal AI POC - what is built versus planned, the two features (onboarding/help agent and personal policy assistant), RAG with pgvector and hybrid search, intent routing, grounded answers with citations, tenant isolation, PII and prompt-injection controls, lazy vectorization, and the phased roadmap. Use this skill whenever a task involves retrieval, embeddings, chunking, intent classification, citations, policy documents, manuals, anonymous vs authenticated access, the Node backend integration, audit logging, rate limiting, or implementing any item from docs/MASBLUE_AI_POC_ARCHITECTURE.md, and when deciding whether a requested change fits the design.
---

# Masblue AI architecture: built vs planned

The authoritative design is `docs/MASBLUE_AI_POC_ARCHITECTURE.md` (v2.0, Nov 2026). It describes a
target, and much of it is not in the code. Before implementing anything from it, check this table, and
build in the style of `masblue-project-standards`. Where the design and the code disagree, say so.

## Two features

1. **Help agent**: guides users through questionnaires and system manuals. Anonymous *and*
   authenticated users.
2. **Personal policy assistant**: answers questions about a signed-in policyholder's own policies with
   exact clause citations.

Principle: the AI service is an *intelligence companion*. It reads validated context and **never
modifies policy records or payment data**. The client sends only `message`, optional
`conversation_id`, optional `intent`; never client-assembled context.

## Status

| Area | Status |
|---|---|
| `POST /chat`, `POST /chat/stream`, history endpoint, health/ready | **Built** (persisted messages, SSE) |
| JWT validation (HS/RS, strict algorithm, requires `sub`) | **Built** |
| LLM provider abstraction + factory + DB model registry | **Built** |
| Tables: `conversations`, `messages`, `models`, `manual_document`, `document_vector_status`, `document_chunk` (pgvector, HNSW, GIN) | **Built** (schema only; the RAG tables are empty and unused) |
| Intent classifier (`get_intent_llm` wiring exists) | Wiring only; **no classifier** |
| Help / policy orchestrators, hybrid retrieval, prompt assembly, PII masking | **Not built** |
| Embedding provider/factory, `EMBEDDING_*` settings | **Not built** |
| Lazy vectorization, Node backend client, citation validator | **Not built** |
| Request `intent`; response `citations`/`intent`; typed SSE frames | **Not built** |
| Anonymous access (every chat route requires a JWT today) | **Not built** |
| Redis rate limiting | Placeholder (`TODO(phase-2)`) |

Roadmap: Phase 0 foundations (done), Phase 1 help-agent RAG (manual ingestion, indexing, classifier,
streaming), Phase 2 policy assistant (backend client, clause parser, lazy vectorization, grounded
prompts, citation checks), Phase 3 hardening (cross-tenant tests, 100-question golden set, p95 < 2 s).

## Non-negotiable rules (security and trust)

These come from the design's security section. Treat them as acceptance criteria:

1. **Tenant isolation in SQL.** Every query over policy chunks filters `tenant_id` (and the active
   `embedding_model_id`) in the `WHERE` clause. Make `tenant_id` a *required* parameter of the
   repository method (no default, no optional filter) so omission is a type error. Manuals are the only
   rows with `tenant_id IS NULL`.
2. **Identity only from the verified JWT** (`CurrentUser.user_id`). Never from the request body,
   query string, or the model's output.
3. **Retrieved text is untrusted data.** Wrap it in clear delimiters in the prompt and instruct the model
   to treat it as reference material only. The model has no database write access and no tools that
   mutate anything.
4. **Grounding.** Answer only from retrieved chunks; every coverage statement carries a section
   reference; if the answer is not in the context, return the designed fallback (point to customer
   support) instead of guessing.
5. **Citation verification.** After generation, cross-check each cited clause against the retrieved chunk
   IDs; drop or replace anything not found, and never return a citation that was not retrieved.
6. **PII.** Scrub sensitive identifiers before prompt assembly; never ingest payment-card credentials.
7. **Auditability.** Log request ID, user ID, intent, and retrieved chunk IDs. See open question 3.
8. **Server-side context.** Policy data comes from server-to-server calls to the Node backend using the
   verified JWT, never from the client.

## Intent routing (design)

`intent` given as `help` -> help flow (any user). `personal` -> requires valid auth, else a login
challenge. Missing -> a small fast model classifies using the query plus the last two turns into
help / personal / out-of-scope (friendly refusal with support contact). Needs the
`intent_llm_*` settings that already exist.

## Where new code should go (suggested; confirm with the user)

Mirror existing layering: `services/intent_service.py`, `services/retrieval_service.py`,
`services/vectorization_service.py`, `services/prompt_service.py`; `repositories/chunk_repo.py`,
`repositories/manual_document_repo.py`, `repositories/vector_status_repo.py`; an `embeddings/` package
like `llm/`; a `clients/masblue_backend.py` using `httpx.AsyncClient`, cached and closed in the
lifespan like the LLM clients. Retrieval SQL uses the cosine operator `<=>` to match the HNSW index and
`to_tsvector('english', chunk_text)` to match the GIN index. Long ingestion work must not block a
request: use a background task with a status row (`pending/processing/ready/failed`) in
`document_vector_status`, keyed by `(source_type, source_id, embedding_model_id)` with a
`content_hash` to detect change.

## Open questions to raise (do not decide silently)

1. **ID type.** `user_id` is a string (JWT `sub`, migration 0003) but `document_chunk.tenant_id` and
   `policy_id` are UUIDs. How does `sub` map to `tenant_id`? If the Node IDs are not UUIDs, tenant
   isolation breaks. The README already asks to confirm the Node user ID type.
2. **Anonymous access.** Feature 1 must work without login, but all routes require a JWT and
   `conversations.user_id` is non-null. Needs an optional-auth dependency and a rule for how (or
   whether) anonymous conversations are stored.
3. **Audit logging vs privacy.** The design logs the model response for auditability; the current
   middleware logs metadata only, by design. Decide what is logged and where, and for how long.
4. **Embedding dimensions.** The column is `Vector(1536)`; "zero-downtime model migration" with a model of a
   different size needs a new column/table or a separate index per dimension.
5. **API contract drift.** Typed SSE frames and `intent`/`citations` fields would change what the React
   client receives. Confirm the client is updated before changing shapes.
6. **Registry secrets.** `models.api_key` is plain text. Decide on encryption or a secret manager
   before more providers (including embeddings) are registered there.
7. **Fallback text.** The design quotes a support phone number and wording for the "not found" reply.
   Confirm the final text and number with the business before hard-coding; keep it in config.

## Evaluation and hardening (Phase 3 expectations)

Automated cross-tenant isolation tests (user A can never retrieve user B's chunks, including through
the vector, keyword, and citation paths); a golden question set measuring faithfulness and citation
correctness; latency benchmarks. When you build a retrieval feature, add the isolation test in the
same change.
