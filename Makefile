.PHONY: run test lint typecheck migrate ingest eval

run:
	uvicorn app.main:app --app-dir src --reload

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

migrate:
	alembic upgrade head

ingest:
	python scripts/ingest.py $(ARGS)

eval:
	python tests/eval/run.py
