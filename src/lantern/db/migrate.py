"""Programmatic Alembic entry points (stub)."""

from pathlib import Path
from typing import Final

from alembic.config import Config

MIGRATIONS_DIR: Final[Path] = Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str) -> Config:
    raise NotImplementedError("S0.1: migrations not implemented yet")


def upgrade(database_url: str, revision: str = "head") -> None:
    raise NotImplementedError("S0.1: migrations not implemented yet")
