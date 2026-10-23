"""Approved S0.2 interfaces, pending implementation."""

from collections.abc import Sequence


def acceptance_ids(backlog_text: str, stories: Sequence[str]) -> list[str]:
    raise NotImplementedError("S0.2: not implemented yet")


def test_marks(source: str, path: str) -> dict[str, list[str]]:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
