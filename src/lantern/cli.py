"""Development commands for Lantern."""
import argparse
from collections.abc import Sequence
import sys

from pydantic import ValidationError

from lantern.config import Settings
from lantern.db.migrate import MigrationError, upgrade


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lantern", description="Public-evidence investigations")
    commands = parser.add_subparsers(dest="command", required=True)
    database = commands.add_parser("db", help="Manage the local database")
    database.add_subparsers(dest="operation", required=True).add_parser("upgrade")
    parser.parse_args(argv)
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
