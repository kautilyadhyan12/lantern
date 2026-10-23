# Lantern

Lantern will research questions using public information, preserve its evidence,
and produce reports with citations you can inspect. This first stage supplies
its development setup; investigation features will follow. Dependencies use
checked security fixes and a locked set of versions; there is no age-based wait.

Open the repository on GitHub, choose **Code → Codespaces → Create codespace**,
and work in your browser. The container provides Python 3.12, uv and Docker.
The owner's development rules are in AGENTS.md; API keys belong in Codespaces secrets.

Run these commands in the Codespace terminal:

```sh
uv sync --frozen
make db
export LANTERN_DATABASE_URL='postgresql+asyncpg://lantern:lantern-local-only@127.0.0.1:5434/lantern'
uv run lantern db upgrade
make hooks
make check
```

These public credentials are for local development only; never reuse them for deployment.
The database listens on localhost port 5434. Checks run offline and need it running.
Run `make db` to start it, or `make db-down` to stop it while keeping its data.
Real secrets come from environment variables; .env.example has placeholders.
Never commit captured evidence or personal data to this public repository.
