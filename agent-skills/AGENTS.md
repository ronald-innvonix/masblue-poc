# Agent instructions: Masblue AI Chat Service

Async FastAPI + SQLAlchemy + PostgreSQL/pgvector service (Python 3.12, `uv`). Before changing code, read
`.claude/skills/masblue-project-standards/SKILL.md`; it links to the task-specific guides:

- Endpoints/services/repositories: `.claude/skills/masblue-api-feature-workflow/SKILL.md`
- Models/migrations: `.claude/skills/masblue-database-migrations/SKILL.md`
- LLM providers: `.claude/skills/masblue-llm-providers/SKILL.md`
- Tests: `.claude/skills/masblue-testing/SKILL.md`
- RAG/architecture/roadmap: `.claude/skills/masblue-ai-architecture/SKILL.md`

Always: keep the layering (route -> service -> repository), put the auth dependency first in routes, never log
message text or secrets, never open `.env`, and finish with
`uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
(the repo has documented pre-existing failures; add none).
