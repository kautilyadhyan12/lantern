"""Run Lantern's ordered checks, preserving failures and bounded output."""

import argparse
import os
import re
import shlex
import subprocess  # nosec B404 # Development checks require bounded child processes.
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


def sanitize(text: str) -> str:
    for key, value in os.environ.items():
        if value and re.search(r"SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|DATABASE_URL", key, re.I):
            text = text.replace(value, "[REDACTED]")
    return text


class StepResult(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, revalidate_instances="always")
    command: tuple[str, ...]
    exit_code: int
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    output_tail: tuple[str, ...] = Field(max_length=30)

    @field_validator("command", "output_tail")
    @classmethod
    def redact(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sanitize(value) for value in values)


CHECKS = tuple(
    tuple(shlex.split(command))
    for command in (
        "uv run ruff check .",
        "uv run ruff format --check src scripts tests",
        "uv run python scripts/lint_custom.py",
        "uv run lint-imports",
        "uv run mypy --strict",
        "uv run --offline pytest --cov --cov-report=term-missing --cov-report=json:coverage.json",
        "uv run python scripts/coverage_gate.py",
        "uv run python scripts/check_dependencies.py",
        "uv run bandit -r src/lantern scripts",
        "uv run pip-audit --local --skip-editable --strict --progress-spinner off --timeout 30",
    )
)
StepRunner = Callable[[Sequence[str], Path], StepResult]


def run_step(command: Sequence[str], root: Path) -> StepResult:
    started = time.monotonic()
    try:
        process = subprocess.run(  # noqa: S603  # nosec B603 # Fixed argument lists; no shell.
            list(command),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=1800,
            check=False,
        )
        status, output = process.returncode, process.stdout.decode(errors="replace")
    except (OSError, subprocess.TimeoutExpired) as error:
        partial = error.output if isinstance(error, subprocess.TimeoutExpired) else b""
        output = (partial or b"").decode(
            errors="replace"
        ) + f"\n{type(error).__name__}: check failed."
        status = 124 if isinstance(error, subprocess.TimeoutExpired) else 126
    return StepResult(
        command=tuple(command),
        exit_code=status,
        duration_seconds=time.monotonic() - started,
        output_tail=tuple(output.splitlines()[-30:]),
    )


def run_checks(
    root: Path, *, runner: StepRunner = run_step, continue_on_error: bool = False
) -> list[StepResult]:
    results = []
    for command in CHECKS:
        result = StepResult.model_validate(runner(command, root))
        results.append(result)
        if result.exit_code and not continue_on_error:
            break
    return results


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    results = run_checks(Path.cwd())
    for result in results:
        print(f"{shlex.join(result.command)}: exit {result.exit_code}")
        print("\n".join(result.output_tail))
    return int(any(result.exit_code for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
