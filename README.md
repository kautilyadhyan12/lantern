# Lantern

Lantern will research questions using public information, preserve its evidence,
and produce reports with citations you can inspect. This first stage supplies
its development setup; investigation features will follow. Setup is in progress:
safe dependency fixes must finish the seven-day wait before a full install/check.

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

The credentials above are public, local development credentials only. The database
listens on localhost port 5434. Never reuse these credentials for deployment.
Real secrets come from environment variables; .env.example contains placeholders.
Checks run offline and need the local database. If it is stopped, run `make db`.
Use `make db-down` to stop it; its data volume is kept. Never commit local evidence
or personal data. The source, development tools and saved process documents are public.
