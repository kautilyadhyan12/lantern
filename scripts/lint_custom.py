"""S0.1 custom linter boundary, awaiting implementation."""
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


def lint_source(source: str, path: str) -> list[Violation]:
    raise NotImplementedError("S0.1: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.1: not implemented yet")
