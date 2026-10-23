"""Approved S0.2 interfaces, pending implementation."""

from collections.abc import Sequence
from pathlib import Path


def hash_entries(
    entries: Sequence[tuple[str, bytes]], excluded_prefixes: Sequence[str] = ()
) -> str:
    raise NotImplementedError("S0.2: not implemented yet")


def code_tree(
    root: Path, *, commit: str | None = None, excluded_prefixes: Sequence[str] = ()
) -> str:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
