"""Approved ADR 0003 interfaces, pending implementation."""

import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.checks import StepRunner, run_step


def installed_requirements(root: Path) -> list[str]:
    raise NotImplementedError("S0.2: not implemented yet")


def audit(root: Path, *, runner: StepRunner = run_step) -> int:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
