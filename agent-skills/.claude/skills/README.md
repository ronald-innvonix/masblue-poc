# Masblue AI Chat Service: agent skill set

Six skills that teach an AI coding agent how this project is built, so new code matches it.
They are plain Markdown; Claude Code loads them automatically from `.claude/skills/`.

| Skill | Use for |
|---|---|
| `masblue-project-standards` | **Always.** Stack, commands, layering, conventions, definition of done, known issues |
| `masblue-api-feature-workflow` | New or changed endpoints, services, repositories, schemas (includes a tested worked example) |
| `masblue-database-migrations` | Models, Alembic, naming rules, pgvector (includes a tested migration) |
| `masblue-llm-providers` | `llm/`, factory, model registry, streaming |
| `masblue-testing` | Writing and debugging tests, running without a database |
| `masblue-ai-architecture` | RAG, intent routing, citations, tenant isolation, built-vs-planned, open questions |

## Install

Unzip at the repository root so you get `.claude/skills/...` (and `AGENTS.md`), then commit them.
In Claude Code, the skills trigger from their descriptions; you can also say "use the
masblue-api-feature-workflow skill". For other agents (Cursor, Codex, Copilot), `AGENTS.md` points at these
files. In Claude.ai, upload a skill folder zipped on its own.

## Keep them current

Skills describe the code as of this snapshot. When conventions change, edit the matching `SKILL.md` in the
same pull request. When a "known issue" is fixed, delete it from
`masblue-project-standards/references/known-issues.md`. The `masblue-ai-architecture` status table
should be updated as roadmap items land.

## What was verified

Run against your code: `ruff`, `mypy`, `pytest` (with and without PostgreSQL), and Alembic
(upgrade, downgrade, upgrade, `check`) on PostgreSQL 16 + pgvector. The worked example feature and the example
migration were built following these skills and passed. Not run: Docker Compose, real LLM calls, the Node backend.
