.PHONY: check prove db db-down hooks
export STORY AC_STORIES

check:
	uv run python -m scripts.checks

prove:
	uv run python -m scripts.prove

db:
	docker compose up -d --wait db

db-down:
	docker compose down

hooks:
	uv run pre-commit install
