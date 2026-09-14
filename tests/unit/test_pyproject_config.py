"""S0.1-AC2: pyproject.toml carries the agreed ruff/mypy/pytest/coverage/mutmut config."""

import tomllib
from pathlib import Path

import pytest

RUFF_SELECT = {
    "E", "F", "W", "I", "N", "UP", "B", "A", "C4", "DTZ", "T10", "EM", "ISC", "PIE", "PT",
    "RET", "SIM", "TID", "ARG", "PL", "RUF", "S", "BLE", "TRY", "ASYNC",
}  # fmt: skip
RUFF_IGNORE = {"PLR2004", "TRY003", "EM101", "EM102"}
RUFF_TESTS_IGNORE = {"S101", "PLR", "ARG"}
PYTEST_MARKERS = {"ac(id): acceptance criterion id", "live: hits real APIs", "slow"}


def _get(data: object, dotted: str) -> object:
    current = data
    for part in dotted.split("."):
        assert isinstance(current, dict), f"{dotted}: parent of {part!r} is not a table"
        assert part in current, f"pyproject.toml is missing {dotted}"
        current = current[part]
    return current


@pytest.fixture(scope="module")
def pyproject(repo_root: Path) -> dict[str, object]:
    with (repo_root / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


@pytest.mark.ac("S0.1-AC2")
def test_project_metadata(pyproject: dict[str, object]) -> None:
    assert _get(pyproject, "project.name") == "lantern"
    assert _get(pyproject, "project.requires-python") == ">=3.12"


@pytest.mark.ac("S0.1-AC2")
def test_ruff_config(pyproject: dict[str, object]) -> None:
    assert _get(pyproject, "tool.ruff.line-length") == 100
    assert _get(pyproject, "tool.ruff.target-version") == "py312"
    select = _get(pyproject, "tool.ruff.lint.select")
    assert isinstance(select, list)
    assert set(select) >= RUFF_SELECT, f"missing rule families: {RUFF_SELECT - set(select)}"


@pytest.mark.ac("S0.1-AC2")
def test_ruff_ignores_exact(pyproject: dict[str, object]) -> None:
    """Ignores are compared exactly: widening them is a deliberate, reviewed change."""
    ignore = _get(pyproject, "tool.ruff.lint.ignore")
    assert isinstance(ignore, list)
    assert set(ignore) == RUFF_IGNORE
    per_file = _get(pyproject, "tool.ruff.lint.per-file-ignores")
    assert isinstance(per_file, dict)
    assert set(per_file.get("tests/**", [])) == RUFF_TESTS_IGNORE


@pytest.mark.ac("S0.1-AC2")
def test_mypy_config(pyproject: dict[str, object]) -> None:
    assert _get(pyproject, "tool.mypy.strict") is True
    assert _get(pyproject, "tool.mypy.warn_unreachable") is True
    plugins = _get(pyproject, "tool.mypy.plugins")
    assert isinstance(plugins, list)
    assert "pydantic.mypy" in plugins


@pytest.mark.ac("S0.1-AC2")
def test_pytest_config(pyproject: dict[str, object]) -> None:
    addopts = _get(pyproject, "tool.pytest.ini_options.addopts")
    assert isinstance(addopts, str)
    for option in ("-q", "--strict-markers", "-p no:cacheprovider"):
        assert option in addopts
    markers = _get(pyproject, "tool.pytest.ini_options.markers")
    assert isinstance(markers, list)
    assert set(markers) >= PYTEST_MARKERS
    assert _get(pyproject, "tool.pytest.ini_options.testpaths") == ["tests"]
    assert _get(pyproject, "tool.pytest.ini_options.asyncio_mode") == "auto"


@pytest.mark.ac("S0.1-AC2")
def test_coverage_config(pyproject: dict[str, object]) -> None:
    assert _get(pyproject, "tool.coverage.run.branch") is True
    assert _get(pyproject, "tool.coverage.run.source") == ["src/lantern"]


@pytest.mark.ac("S0.1-AC2")
def test_mutmut_config(pyproject: dict[str, object]) -> None:
    assert _get(pyproject, "tool.mutmut.paths_to_mutate") == ["src/lantern/"]
    assert _get(pyproject, "tool.mutmut.tests_dir") == ["tests/"]
