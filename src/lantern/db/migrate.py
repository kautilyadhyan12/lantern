"""Programmatic Alembic entry points used by ``lantern db ...``."""

from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR: Final[Path] = Path(__file__).resolve().parent / "migrations"
DATABASE_URL_ATTRIBUTE: Final = "lantern_database_url"
# Revision files must be valid module names (ruff N999, mypy), so prefix the revision id.
FILE_TEMPLATE: Final = "r%(rev)s_%(slug)s"


def _ini_escape(value: str) -> str:
    return value.replace("%", "%%")


def alembic_config(database_url: str) -> Config:
    """Alembic config for Lantern's migrations.

    The URL travels in ``Config.attributes`` rather than the ini options: ConfigParser
    would %-interpolate it and could echo the password in error messages.
    """
    config = Config()
    config.set_main_option("script_location", _ini_escape(str(MIGRATIONS_DIR)))
    config.set_main_option("file_template", _ini_escape(FILE_TEMPLATE))
    config.attributes[DATABASE_URL_ATTRIBUTE] = database_url
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)
