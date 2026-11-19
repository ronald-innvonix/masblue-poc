# Common local development commands.
.PHONY: install dev test lint format migrate

install:
	uv sync --group dev

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

