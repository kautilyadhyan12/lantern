"""Approved S0.2 interfaces, pending implementation."""

import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import AwareDatetime, BaseModel

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.checks import (  # Standalone-script signature imports need the repository root.
    StepResult,
    StepRunner,
    run_step,
)


class ProofContext(BaseModel):
    story: str
    commit_sha: str
    code_tree: str
    recorded_at: AwareDatetime
    platform: str


def render_proof(context: ProofContext, results: Sequence[StepResult]) -> str:
    raise NotImplementedError("S0.2: not implemented yet")


def prove(
    story: str, ac_stories: Sequence[str], root: Path, *, runner: StepRunner = run_step
) -> int:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
