"""Project entry point and developer commands work as advertised."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from lantern import cli

CHECKS = [
    "ruff check",
    "ruff format --check",
    "lint_custom.py",
    "lint-imports",
    "mypy",
    "pytest",
    "coverage_gate.py",
    "check_dependencies.py",
    "bandit",
    "pip-audit",
]


@pytest.mark.ac("S0.1-AC1")
def test_placeholder():
    assert Path(cli.__file__).parts[-3:] == ("src", "lantern", "cli.py")


@pytest.mark.ac("S0.1-AC1")
def test_console_help(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["--help"])
    assert caught.value.code == 0
    output = capsys.readouterr().out.lower()
    assert "lantern" in output
    assert "db" in output


@pytest.mark.ac("S0.1-AC1")
def test_python_pin_and_lockfile(project_file):
    assert project_file(".python-version").strip().split(".")[:2] == ["3", "12"]
    lock = tomllib.loads(project_file("uv.lock"))
    assert any(package["name"] == "lantern" for package in lock["package"])
    assert not any(package["name"] == "litellm" for package in lock["package"])


@pytest.mark.ac("S0.1-AC1")
@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("failed_step", [None, *range(10)])
def test_make_check_commands_and_failure_propagation(project_file, repo, tmp_path, failed_step):
    project_file("Makefile")
    project_file("scripts/lint_custom.py")
    log = tmp_path / "checks.log"
    executable = tmp_path / "uv"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1:] == ['run', 'python', '-m', 'scripts.checks']:\n"
        f"    os.execv({sys.executable!r}, [{sys.executable!r}, '-m', 'scripts.checks'])\n"
        "args = ' '.join(sys.argv[1:])\n"
        f"checks = {CHECKS!r}\n"
        "index = next((i for i, item in enumerate(checks) if item in args), None)\n"
        "if index is None: sys.exit(73)\n"
        "with open(os.environ['CHECK_LOG'], 'a') as stream: stream.write(str(index) + '\\n')\n"
        "sys.exit(9 if str(index) == os.environ['FAIL_STEP'] else 0)\n"
    )
    executable.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "CHECK_LOG": str(log),
        "FAIL_STEP": str(failed_step),
    }
    result = subprocess.run(
        ["make", "check"],  # noqa: S607  # Only repository tools and temporary test paths.
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert log.is_file(), "make check must invoke the checks through uv run"
    seen = [int(line) for line in log.read_text().splitlines()]
    assert seen == list(range(10 if failed_step is None else failed_step + 1))
    assert (result.returncode == 0) is (failed_step is None)


@pytest.mark.ac("S0.1-AC1")
@pytest.mark.parametrize(("target", "expected"), [("db", "up"), ("db-down", "down")])
def test_db_targets(project_file, repo, target, expected):
    project_file("Makefile")
    result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        ["make", "--dry-run", target],  # noqa: S607  # Only repository tools and temporary test paths.
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert "docker compose" in result.stdout
    assert expected in result.stdout
    if target == "db":
        assert "--wait" in result.stdout, "Wait for database health before reporting success"
    else:
        assert "--volumes" not in result.stdout
        assert " -v" not in result.stdout
