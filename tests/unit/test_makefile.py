import re
from pathlib import Path

import pytest

_TARGET = re.compile(r"^([A-Za-z][\w-]*)\s*:(?!=)")


def _recipes(makefile: Path) -> dict[str, str]:
    """Map each Makefile target to its recipe lines joined by newlines."""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if line.startswith("\t") and current is not None:
            recipes[current].append(line.strip())
        elif match := _TARGET.match(line):
            current = match.group(1)
            recipes.setdefault(current, [])
    return {target: "\n".join(lines) for target, lines in recipes.items()}


@pytest.mark.ac("S0.1-AC1")
def test_makefile_defines_targets(repo_root: Path) -> None:
    makefile = repo_root / "Makefile"
    assert makefile.is_file(), "Makefile missing"
    recipes = _recipes(makefile)

    lint = recipes.get("lint", "")
    assert "uv run ruff check" in lint
    assert "uv run ruff format --check" in lint
    assert "uv run python scripts/lint_custom.py" in lint

    assert "uv run mypy" in recipes.get("typecheck", "")

    test = recipes.get("test", "")
    assert "uv run pytest" in test
    for suite in ("tests/unit", "tests/property", "tests/contract", "tests/e2e"):
        assert suite in test, f"`make test` must run {suite}"
    assert "tests/live" not in test, "`make test` is the offline suite"
