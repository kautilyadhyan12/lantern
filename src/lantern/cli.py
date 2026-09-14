"""Lantern command-line entry point: ``lantern <command> ...``."""

import argparse
from collections.abc import Callable, Sequence

import structlog

from lantern.config import Settings
from lantern.db import migrate

log = structlog.get_logger(__name__)

Handler = Callable[[argparse.Namespace], int]


def _db_upgrade(_args: argparse.Namespace) -> int:
    migrate.upgrade(Settings().database_url.get_secret_value())
    log.info("db.upgrade.done", revision="head")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lantern", description="Lantern OSINT platform")
    commands = parser.add_subparsers(dest="command", required=True)

    db = commands.add_parser("db", help="database schema management")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    upgrade = db_commands.add_parser("upgrade", help="apply all migrations (alembic upgrade head)")
    upgrade.set_defaults(handler=_db_upgrade)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    return handler(args)
