---
name: masblue-database-migrations
description: How to change the database in the Masblue AI Chat Service - SQLAlchemy 2.0 ORM models, Alembic migrations, the ai_chat schema, pgvector columns, constraint and index naming, and safe upgrade/downgrade. Use this skill whenever a task adds or alters a table, column, index, constraint, enum, or extension, creates or edits anything in migrations/ or models/, runs alembic, or touches the model registry, conversations, messages, or RAG tables, even if the user only says "store X" or "add a field".
---

# Database models and migrations

Read `masblue-project-standards` first. Everything here was verified by running the migrations
against PostgreSQL 16 with pgvector (up, down to base, up again) and by building a new table
following these steps (`references/migration-patterns.md` is that tested example).

## Ground rules

- The service owns **only** the `ai_chat` schema (`DB_SCHEMA`). Never create a foreign key to, query,
  or migrate the Node application's tables. If read access to them is ever needed, that is a separate
  read-only role, not a migration (the README says so). `migrations/env.py` filters autogenerate to
  the service schema with `include_name`; do not remove that.
- Models subclass `Base` (schema + naming convention preset in `models/base.py`) and usually mix in
  `UUIDPrimaryKey` and `TimestampMixin`. Foreign keys use `schema_qualified("table")`, because the
  schema is configurable and is read at import time.
- ORM style: `Mapped[...]` + `mapped_column`, relationships with `TYPE_CHECKING` imports and string
  annotations, one entity per file, exported in `models/__init__.py` (Alembic only sees models
  imported there).
- `user_id` is a **string** (JWT `sub`), not a UUID.
- Tables: default new unplanned tables to plural `snake_case`; use the architecture doc's name for
  tables it defines (see known-issues F).

## Workflow

1. Edit or add the model; export it in `models/__init__.py`.
2. Generate a draft: `uv run alembic revision --autogenerate -m "short description"`.
3. **Rewrite the draft by hand** to the house style, then review it line by line:
   - File `migrations/versions/NNNN_slug.py` with the next number; `revision = "NNNN_slug"` (keep it
     **32 characters or fewer**, the width of Alembic's version column) and `down_revision` set to
     the previous revision string. Run `uv run alembic heads` and confirm exactly one head.
   - Header, typed revision variables and a docstring on `upgrade`/`downgrade`, copied from an
     existing migration.
   - Get the schema with `schema = op.get_context().config.attributes["db_schema"]` and pass
     `schema=schema` to every operation. Never hard-code `"ai_chat"`.
   - **Delete unrelated index drop/create operations** that autogenerate emits for
     `ix_conversations_user_id`, `ix_messages_conversation_id`, `ix_messages_model_id` (known-issues
     E1: a naming-convention mismatch, not a real change).
4. Write a real `downgrade()` that reverses the upgrade in reverse order.
5. Prove it: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`,
   then `uv run alembic check`. The only drift allowed is the three E1 index renames.
6. Add or adjust tests and any repository code (see `masblue-api-feature-workflow`).

## Naming (this is where mistakes hide)

`models/base.py` defines a naming convention. Alembic applies it to the names you pass in a migration
as well, so the two must be consistent:

| Kind | ORM declaration | Name the migration must produce |
|---|---|---|
| Primary key | automatic | `pk_<table>`; pass `name="pk_<table>"` |
| Foreign key | automatic | `fk_<table>_<col>_<referred_table>`; pass exactly that |
| Unique | `UniqueConstraint(cols)` | `uq_<table>_<first_col>`; pass exactly that |
| Check | `CheckConstraint(sql, name="rating_range")` | `ck_<table>_rating_range`; pass the **bare** name `"rating_range"` in the migration too |
| Index | prefer an explicit `Index("ix_<table>_<col>", "col")` | `ix_<table>_<col>` |

Check constraints are the trap: passing the already-prefixed name makes the convention prefix it
twice (`ck_messages_ck_messages_message_role` exists in the database today because migration 0001
did this). Always pass the bare name. Prefer explicit `Index(...)` over `index=True` for new
columns until known-issues E1 is fixed, so model and migration agree.

## Patterns to reuse

All with examples in `references/migration-patterns.md`: create table, add column, change a column
type (`postgresql_using`), rename table/constraints, enum types (`create_type=False` plus
`checkfirst`), the `vector` extension, HNSW and GIN indexes, partial unique indexes, data fixes.

## Cautions specific to this repo

- `document_chunk.embedding` is `Vector(1536)`. A different embedding dimension needs a new column or
  table and a migration; the registry's `dimensions` field alone does not change the column.
- `models.api_key` is plain text. Do not add more secrets to that table.
- `tenant_id` and `policy_id` are UUID columns but `user_id` is a string. Resolve how a JWT `sub`
  maps to `tenant_id` before writing tenant-filtered queries (see `masblue-ai-architecture`).
- Compose runs `alembic upgrade head` on startup for development; production runs migrations as a
  separate job with a role that can alter the schema, while the app runs with a restricted role.
- Avoid importing ORM models inside migrations; use `sa.text(...)` with schema-qualified names for
  data changes, so old migrations keep working after models change.
- Migration `0002` needs pgvector installed in the database image (known-issues E2).
