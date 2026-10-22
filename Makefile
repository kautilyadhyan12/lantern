.PHONY: check db db-down hooks
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run python scripts/lint_custom.py
	uv run mypy --strict
	uv run --offline pytest

db:
	docker compose up -d --wait db

db-down:
	docker compose down

hooks:
	uv run pre-commit install
