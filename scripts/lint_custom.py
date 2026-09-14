"""Custom lint rules for the Lantern codebase (stub)."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


@dataclass(frozen=True)
class Suppression:
    kind: Literal["type-ignore", "noqa"]
    reason: str


RULES: Final[Mapping[str, str]] = {}


def parse_suppression(comment: str) -> Suppression | None:
    raise NotImplementedError("S0.1: lint_custom not implemented yet")


def has_issue_url(text: str) -> bool:
    raise NotImplementedError("S0.1: lint_custom not implemented yet")


def check_source(source: str, path: str, *, in_src: bool) -> list[Violation]:
    raise NotImplementedError("S0.1: lint_custom not implemented yet")


def iter_python_files(paths: Sequence[Path]) -> Iterator[Path]:
    raise NotImplementedError("S0.1: lint_custom not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.1: lint_custom not implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
