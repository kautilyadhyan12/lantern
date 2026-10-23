"""The tool configuration is a contract defined by the design document."""

import tomllib

import pytest

EXPECTED = {
    "project.name": "lantern",
    "project.requires-python": ">=3.12",
    "project.scripts.lantern": "lantern.cli:main",
    "tool.ruff.line-length": 100,
    "tool.ruff.target-version": "py312",
    "tool.ruff.lint.select": [
        "E",
        "F",
        "W",
        "I",
        "N",
        "UP",
        "B",
        "A",
        "C4",
        "DTZ",
        "T10",
        "EM",
        "ISC",
        "PIE",
        "PT",
        "RET",
        "SIM",
        "TID",
        "ARG",
        "PL",
        "RUF",
        "S",
        "BLE",
        "TRY",
        "ASYNC",
    ],
    "tool.ruff.lint.ignore": ["PLR2004", "TRY003", "EM101", "EM102"],
    "tool.mypy.strict": True,
    "tool.mypy.warn_unreachable": True,
    "tool.mypy.plugins": ["pydantic.mypy"],
    "tool.pytest.ini_options.addopts": (
        "-q --strict-markers -p no:cacheprovider --import-mode=importlib"
    ),
    "tool.pytest.ini_options.pythonpath": ["."],
    "tool.pytest.ini_options.testpaths": ["tests"],
    "tool.pytest.ini_options.asyncio_mode": "auto",
    "tool.pytest.ini_options.markers": [
        "ac(id): acceptance criterion id",
        "review: adversarial test written by the independent reviewer",
        "live: calls real external APIs",
        "slow: slow test",
    ],
    "tool.coverage.run.branch": True,
    "tool.coverage.run.source": ["src/lantern", "scripts"],
}


@pytest.mark.ac("S0.1-AC2")
@pytest.mark.parametrize(("key", "expected"), EXPECTED.items())
def test_required_tooling_keys(project_file, key, expected):
    value = tomllib.loads(project_file("pyproject.toml"))
    for part in key.split("."):
        assert part in value, f"Missing configuration: {key}"
        value = value[part]
    assert value == expected, f"Configuration differs from docs/05 §2.1: {key}"


@pytest.mark.ac("S0.1-AC2")
def test_per_file_lint_ignores(project_file):
    config = tomllib.loads(project_file("pyproject.toml"))
    assert "ruff" in config.get("tool", {}), "S0.1 must configure ruff"
    ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
    assert ignores == {
        "tests/**": ["S101", "PLR", "ARG"],
        "tests/review/**": ["S101", "PLR", "ARG", "N999"],
    }


@pytest.mark.ac("S0.1-AC2")
def test_src_package_and_console_entry(project_file, repo):
    config = tomllib.loads(project_file("pyproject.toml"))
    assert config.get("project", {}).get("scripts", {}).get("lantern") == "lantern.cli:main"
    assert (repo / "src/lantern/__init__.py").is_file()
    assert "build-system" in config, "A fresh clone must install the src-layout package"
    assert config["build-system"]["requires"], "Build dependencies must be pinned and audited"


@pytest.mark.ac("S0.1-AC2")
def test_dependency_cooldown(project_file):
    config = tomllib.loads(project_file("pyproject.toml"))
    assert config["tool"]["uv"]["exclude-newer"] == "7 days"
    assert not config["tool"]["uv"].get("exclude-newer-package"), "No cooldown exceptions"
