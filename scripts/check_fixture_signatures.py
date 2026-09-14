"""Fixture signature policy check (stub)."""

from collections.abc import Sequence
from pathlib import Path


def find_fixtures(root: Path) -> list[Path]:
    raise NotImplementedError("S0.1: check_fixture_signatures not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.1: check_fixture_signatures not implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
