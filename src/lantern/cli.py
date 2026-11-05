"""Command line: run an investigation, serve the web app, manage the database."""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Literal

import uvicorn
from pydantic import ValidationError

from lantern.config import AppSettings, Settings
from lantern.db.migrate import MigrationError, upgrade
from lantern.models import Investigation, now
from lantern.report import to_markdown
from lantern.runtime import continue_investigation, run_investigation
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


def _run(brief: str | None, depth: Literal["quick", "deep"], resume: str | None = None) -> int:
    settings = AppSettings()
    store = Store(settings.data_dir)
    if resume is not None:
        found = store.load(resume)
        if found is None or not found.questions or found.status in {"queued", "running"}:
            sys.stderr.write("No finished investigation with that id. See var/investigations.\n")
            return 1
        investigation = found
        investigation.continued_at.append(now())
    else:
        investigation = Investigation(id=store.new_id(), brief=brief or "", depth=depth)
    store.save(investigation)
    seen = len(investigation.steps)

    def show(investigation: Investigation) -> None:
        nonlocal seen
        for step in investigation.steps[seen:]:
            sys.stdout.write(f"  · {step.message}\n")
        sys.stdout.flush()
        seen = len(investigation.steps)

    work = continue_investigation if resume else run_investigation
    result = asyncio.run(work(investigation, settings, store, show))
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
    run.add_argument(
        "--quick", action="store_true", help="One round of about 10 pages instead of a deep run"
    )
    again = commands.add_parser("continue", help="Continue a finished investigation")
    again.add_argument("id", help="The investigation id (from the web app or var/)")
    serve = commands.add_parser("serve", help="Start the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    database = commands.add_parser("db", help="Manage the local database")
    database.add_subparsers(dest="operation", required=True).add_parser("upgrade")
    arguments = parser.parse_args(argv)
    if arguments.command == "run":
        return _run(arguments.brief, "quick" if arguments.quick else "deep")
    if arguments.command == "continue":
        return _run(None, "deep", resume=arguments.id)
    if arguments.command == "serve":
        return _serve(arguments.host, arguments.port)
    return _database()
