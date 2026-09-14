# Lantern

AI-orchestrated OSINT investigation platform.

## Development quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), GNU make, Docker (Compose v2), git.

```sh
uv sync                    # Python 3.12 venv + locked dependencies
cp .env.example .env       # then replace every change-me (keep the two passwords in sync)
make db                    # Postgres 16 + pgvector on 127.0.0.1:${LANTERN_DB_PORT:-5434}
uv run lantern db upgrade  # apply migrations
make hooks                 # install the pre-commit hooks
make lint typecheck test   # the local gates
```

`make test` runs the offline suite (`tests/unit`, `property`, `contract`, `e2e`); the e2e
tests need the database from `make db` and fail with a pointer to it when it is down.

## Notes

- Pre-commit hooks are all local (`uv run …`), so they use the tool versions in `uv.lock`.
  The detect-secrets hook refuses to run while `.secrets.baseline` has unstaged changes —
  `git add .secrets.baseline` after it updates. Prefer `# pragma: allowlist secret` on a
  false-positive line over growing the baseline.
- Windows: everything works natively (uv, GNU make, Docker Desktop); Makefile recipes are
  single commands so cmd.exe and sh behave the same.
