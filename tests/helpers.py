"""Shared helpers for tests that drive external tools (git, uv, make, pre-commit)."""

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def tool(name: str) -> str:
    """Absolute path of an executable on PATH; fails the test loudly if it is missing."""
    path = shutil.which(name)
    assert path is not None, f"`{name}` must be on PATH"
    return path


def run(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = 300,
    check: bool = False,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with an argv list (never a shell), capturing UTF-8 output."""
    return subprocess.run(  # noqa: S603  # argv lists built by tests from fixed tool names
        list(args),
        cwd=cwd,
        env=env,
        input=stdin_text,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
    )


def output(result: subprocess.CompletedProcess[str], lines: int = 80) -> str:
    """Last `lines` lines of combined stdout/stderr, for assertion messages."""
    return "\n".join((result.stdout + result.stderr).splitlines()[-lines:])
