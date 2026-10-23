"""Approved S0.2 interfaces, pending implementation."""

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel


class StepResult(BaseModel):
    command: tuple[str, ...]
    exit_code: int
    duration_seconds: float
    output_tail: tuple[str, ...]


CHECKS: tuple[tuple[str, ...], ...] = ()
StepRunner = Callable[[Sequence[str], Path], StepResult]


def run_step(command: Sequence[str], root: Path) -> StepResult:
    raise NotImplementedError("S0.2: not implemented yet")


def run_checks(
    root: Path, *, runner: StepRunner = run_step, continue_on_error: bool = False
) -> list[StepResult]:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
