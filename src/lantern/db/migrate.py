"""S0.1 migration boundary, awaiting implementation."""
from lantern.config import Settings


class MigrationError(RuntimeError):
    """A migration failed; its details must never expose credentials."""


def upgrade(settings: Settings) -> None:
    raise NotImplementedError("S0.1: not implemented yet")
