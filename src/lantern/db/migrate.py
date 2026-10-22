"""Apply packaged migrations without writing credentials to config files."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from asyncpg import PostgresError  # type: ignore[import-untyped]  # asyncpg has no type metadata.
from sqlalchemy.exc import SQLAlchemyError

from lantern.config import Settings


class MigrationError(RuntimeError):
    """A migration failed; its details must never expose credentials."""


def upgrade(settings: Settings) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["database_url"] = settings.database_url
    try:
        command.upgrade(config, "head")
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        raise MigrationError("Database unavailable. Run make db and check your settings.") from None
