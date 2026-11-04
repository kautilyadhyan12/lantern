"""Command line: run an investigation, serve the web app, manage the database."""

import argparse
import asyncio
import sys
from collections.abc import Sequence

import uvicorn
from pydantic import ValidationError

from lantern.config import AppSettings, Settings
from lantern.db.migrate import MigrationError, upgrade
from lantern.models import Investigation
from lantern.report import to_markdown
from lantern.runtime import run_investigation
from lantern.store import Store
from lantern.web.app import create_app


def _database() -> int:
    try:
        upgrade(Settings())
    except ValidationError:
        sys.stderr.write("Set LANTERN_DATABASE_URL to a postgresql+asyncpg database URL.\n")
        return 1
    except MigrationError:
        sys.stderr.write("Database upgrade failed. Run make db, check your settings, and retry.\n")
        return 1
    sys.stdout.write("Database is up to date.\n")
    return 0


def _run(brief: str) -> int:

    settings = AppSettings()
    store = Store(settings.data_dir)
    seen = 0

    def show(investigation: Investigation) -> None:
        nonlocal seen
        for step in investigation.steps[seen:]:
            sys.stdout.write(f"  · {step.message}\n")
        sys.stdout.flush()
        seen = len(investigation.steps)

    investigation = Investigation(id=store.new_id(), brief=brief)
    store.save(investigation)
    result = asyncio.run(run_investigation(investigation, settings, store, show))
    if result.status == "done":
        path = store.root / "investigations" / f"{result.id}.md"
        path.write_text(to_markdown(result), encoding="utf-8")
        sys.stdout.write(f"\nReport saved to {path}\n")
        return 0
    sys.stderr.write(f"\n{result.status}: {result.error or result.safety}\n")
    return 1


def _serve(host: str, port: int) -> int:
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lantern", description="Public-evidence investigations")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Investigate a question and save a cited report")
    run.add_argument("brief", help="The research question, in quotes")
    serve = commands.add_parser("serve", help="Start the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    database = commands.add_parser("db", help="Manage the local database")
    database.add_subparsers(dest="operation", required=True).add_parser("upgrade")
    arguments = parser.parse_args(argv)
    if arguments.command == "run":
        return _run(arguments.brief)
    if arguments.command == "serve":
        return _serve(arguments.host, arguments.port)
    return _database()
