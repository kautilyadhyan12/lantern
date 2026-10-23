"""Approved S0.2 interfaces, pending implementation."""

from collections.abc import Sequence

DENIED: frozenset[str] = frozenset()


def denied_packages(names: Sequence[str]) -> list[str]:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
