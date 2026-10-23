"""The shared gate has a fixed order and cannot hide failed checks."""

import os
import shutil
import subprocess
import sys
import tomllib

import pytest
from pydantic import ValidationError

from scripts import checks

EXPECTED = (
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "ruff", "format", "--check", "src", "scripts", "tests"),
    ("uv", "run", "python", "scripts/lint_custom.py"),
    ("uv", "run", "lint-imports"),
    ("uv", "run", "mypy", "--strict"),
    (
        "uv",
        "run",
        "--offline",
        "pytest",
        "--cov",
        "--cov-report=term-missing",
        "--cov-report=json:coverage.json",
    ),
    ("uv", "run", "python", "scripts/coverage_gate.py"),
    ("uv", "run", "python", "scripts/check_dependencies.py"),
    ("uv", "run", "bandit", "-r", "src/lantern", "scripts"),
    ("uv", "run", "python", "scripts/audit_dependencies.py"),
)
CRITICAL_PATHS = [
    "src/lantern/core",
    "src/lantern/policy",
    "src/lantern/egress",
    "src/lantern/db/events.py",
    "src/lantern/tools/gateway.py",
    "src/lantern/llm/gateway.py",
    "src/lantern/report/render_html.py",
    "scripts/hooks",
]


@pytest.mark.ac("S0.2-AC1")
def test_required_order(tmp_path):
    assert checks.CHECKS == EXPECTED
    seen = []

    def runner(command, root):
        assert root == tmp_path
        seen.append(tuple(command))
        return checks.StepResult(
            command=tuple(command), exit_code=0, duration_seconds=0, output_tail=()
        )

    results = checks.run_checks(tmp_path, runner=runner)
    assert seen == list(EXPECTED)
    assert [result.command for result in results] == seen


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("failed_step", range(10))
@pytest.mark.parametrize("continue_on_error", [False, True])
def test_stops_at_each_failure(tmp_path, failed_step, continue_on_error):
    seen = []

    def runner(command, root):
        index = len(seen)
        seen.append(tuple(command))
        return checks.StepResult(
            command=tuple(command),
            exit_code=9 if index == failed_step else 0,
            duration_seconds=0.01,
            output_tail=(f"step {index}",),
        )

    results = checks.run_checks(tmp_path, runner=runner, continue_on_error=continue_on_error)
    expected_length = 10 if continue_on_error else failed_step + 1
    assert seen == list(EXPECTED[:expected_length])
    assert len(results) == expected_length
    assert results[failed_step].exit_code == 9


@pytest.mark.ac("S0.2-AC1")
def test_run_step_captures_exit_duration_and_last_30_lines(tmp_path):
    command = [sys.executable, "-c", "import sys; print(*range(45), sep='\\n'); sys.exit(7)"]
    result = checks.run_step(command, tmp_path)
    assert result.command == tuple(command)
    assert result.exit_code == 7
    assert result.duration_seconds >= 0
    assert result.output_tail == tuple(str(number) for number in range(15, 45))


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("failure", ["spawn", "timeout"])
def test_spawn_and_timeout_fail(tmp_path, monkeypatch, failure):
    def failed_process(*args, **kwargs):
        assert isinstance(args[0], (tuple, list))
        assert kwargs.get("shell", False) is False
        assert 0 < kwargs["timeout"] <= 1800
        if failure == "spawn":
            raise OSError("synthetic launch failure")
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=b"partial output")

    monkeypatch.setattr(subprocess, "run", failed_process)
    result = checks.run_step([sys.executable, "--version"], tmp_path)
    assert result.exit_code != 0
    assert result.output_tail
    assert any(failure in line.lower() or "fail" in line.lower() for line in result.output_tail)


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf")])
def test_invalid_step_result_rejected(duration):
    try:
        checks.StepResult(command=("test",), exit_code=0, duration_seconds=duration, output_tail=())
    except ValidationError:
        return
    raise AssertionError("Process-result durations must be finite and non-negative")


@pytest.mark.ac("S0.2-AC1")
def test_make_uses_shared_runner(repo):
    result = subprocess.run(
        ["make", "--dry-run", "check"],  # noqa: S607  # Only inspect the repository's Makefile.
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "uv run python -m scripts.checks"


@pytest.mark.ac("S0.2-AC1")
def test_import_contract_blocks_reverse_dependency(repo, tmp_path):
    configuration = tomllib.loads((repo / "pyproject.toml").read_text())
    contracts = configuration.get("tool", {}).get("importlinter", {}).get("contracts", [])
    assert any(
        item.get("type") == "layers" and item.get("layers") == ["lantern.cli", "lantern.db"]
        for item in contracts
    ), "Enforce existing CLI/database layers before introducing future packages"
    shutil.copytree(repo / "src", tmp_path / "src")
    shutil.copy(repo / "pyproject.toml", tmp_path / "pyproject.toml")
    command = [str(repo / ".venv/bin/lint-imports")]
    options = {
        "cwd": tmp_path,
        "capture_output": True,
        "text": True,
        "timeout": 30,
        "env": {**os.environ, "PYTHONPATH": str(tmp_path / "src")},
    }
    clean = subprocess.run(command, check=False, **options)  # noqa: S603  # Fixed installed linter, copied source.
    assert clean.returncode == 0, clean.stdout + clean.stderr
    database_init = tmp_path / "src/lantern/db/__init__.py"
    database_init.write_text(database_init.read_text() + "\nimport lantern.cli\n")
    broken = subprocess.run(command, check=False, **options)  # noqa: S603  # Fixed installed linter, copied source.
    assert broken.returncode != 0
    assert "BROKEN" in broken.stdout


@pytest.mark.ac("S0.2-AC5")
def test_quality_configuration_and_sources(project_file):
    tool = tomllib.loads(project_file("pyproject.toml"))["tool"]
    assert "lantern" in tool, "Missing quality configuration"
    assert "quality" in tool["lantern"], "Missing quality configuration"
    quality = tool["lantern"]["quality"]
    assert quality["coverage_total"] == 85
    assert quality["coverage_critical"] == 95
    assert tool["coverage"]["run"]["branch"] is True
    assert tool["coverage"]["run"]["source"] == ["src/lantern", "scripts"]


@pytest.mark.ac("S0.2-AC5")
def test_critical_paths_exact(project_file):
    tool = tomllib.loads(project_file("pyproject.toml"))["tool"]
    quality = tool.get("lantern", {}).get("quality", {})
    assert quality.get("critical_paths") == CRITICAL_PATHS


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize(
    "script",
    [
        "checks.py",
        "coverage_gate.py",
        "check_acceptance_ids.py",
        "check_dependencies.py",
        "audit_dependencies.py",
        "code_tree.py",
        "prove.py",
    ],
)
def test_standalone_scripts_have_working_cli(repo, tmp_path, script):
    result = subprocess.run(  # noqa: S603  # Fixed interpreter and repository script paths.
        [sys.executable, str(repo / "scripts" / script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()
    assert "Traceback" not in result.stderr
