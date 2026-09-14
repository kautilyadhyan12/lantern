# Lantern developer tasks.
# Each recipe line is a single plain command so it behaves the same under GNU make on
# Windows (cmd.exe or sh) and on Linux CI. Anything more complex belongs in scripts/*.py.
# Targets for later stories (prove, mutate, evals, t3, smoke, run) are added by those stories.

.PHONY: lint typecheck test db db-down hooks

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run python scripts/lint_custom.py src tests scripts

typecheck:
	uv run mypy src tests scripts

# Offline suite. e2e tests need the dev database: run `make db` first.
test:
	uv run pytest tests/unit tests/property tests/contract tests/e2e

db:
	docker compose up -d --wait db

db-down:
	docker compose down

hooks:
	uv run pre-commit install
