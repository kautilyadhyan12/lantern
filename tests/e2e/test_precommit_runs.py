"""S0.1-AC4: the pre-commit config installs into a git repo and its hooks really run."""

import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.helpers import output, run, tool

# Built at runtime so this file never contains a literal key for detect-secrets to flag.
FAKE_AWS_KEY = "AKIA" + "Z7Q3" + "EXAMPLEKEY12"
PRE_COMMIT = [sys.executable, "-m", "pre_commit"]


@pytest.fixture
def scratch(repo_root: Path) -> Iterator[Path]:
    """A throwaway directory *inside* the repo (gitignored `.test-tmp/`).

    pre-commit relativises `--files` against the repo root, which fails across Windows
    drives, so sample files cannot live in pytest's tmp_path.
    """
    path = repo_root / ".test-tmp" / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _hook(repo_root: Path, hook_id: str, *files: Path) -> subprocess.CompletedProcess[str]:
    return run([*PRE_COMMIT, "run", hook_id, "--files", *map(str, files)], cwd=repo_root)


@pytest.mark.ac("S0.1-AC4")
def test_config_validates(repo_root: Path) -> None:
    result = run([*PRE_COMMIT, "validate-config", ".pre-commit-config.yaml"], cwd=repo_root)
    assert result.returncode == 0, output(result)


@pytest.mark.ac("S0.1-AC4")
def test_installs_into_git_repo(repo_root: Path, tmp_path: Path) -> None:
    config = repo_root / ".pre-commit-config.yaml"
    assert config.is_file(), ".pre-commit-config.yaml missing"
    run([tool("git"), "init", "-q", str(tmp_path)], cwd=tmp_path, check=True)
    shutil.copy(config, tmp_path / ".pre-commit-config.yaml")
    result = run([*PRE_COMMIT, "install"], cwd=tmp_path)
    assert result.returncode == 0, output(result)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    assert "pre-commit" in hook.read_text(encoding="utf-8")


@pytest.mark.ac("S0.1-AC4")
def test_ruff_hook_fails_on_lint_error_and_passes_clean(repo_root: Path, scratch: Path) -> None:
    bad = scratch / "bad_module.py"
    bad.write_text('"""Module."""\n\nVALUE = undefined_name\n', encoding="utf-8")
    good = scratch / "good_module.py"
    good.write_text('"""Module."""\n\nVALUE = 1\n', encoding="utf-8")

    failed = _hook(repo_root, "ruff-check", bad)
    assert failed.returncode != 0
    assert "F821" in output(failed)

    passed = _hook(repo_root, "ruff-check", good)
    assert passed.returncode == 0, output(passed)


@pytest.mark.ac("S0.1-AC4")
def test_mypy_hook_runs(repo_root: Path, scratch: Path) -> None:
    bad = scratch / "bad_types.py"
    bad.write_text('"""Module."""\n\nVALUE: int = "text"\n', encoding="utf-8")
    good = scratch / "good_types.py"
    good.write_text('"""Module."""\n\nVALUE: int = 1\n', encoding="utf-8")

    failed = _hook(repo_root, "mypy", bad)
    assert failed.returncode != 0
    assert "Incompatible types in assignment" in output(failed)

    passed = _hook(repo_root, "mypy", good)
    assert passed.returncode == 0, output(passed)


@pytest.mark.ac("S0.1-AC4")
def test_detect_secrets_hook_flags_secret(repo_root: Path, scratch: Path) -> None:
    leaky = scratch / "leaky.py"
    leaky.write_text(f'"""Module."""\n\nKEY_ID = "{FAKE_AWS_KEY}"\n', encoding="utf-8")
    clean = scratch / "clean.py"
    clean.write_text('"""Module."""\n\nVALUE = 1\n', encoding="utf-8")

    flagged = _hook(repo_root, "detect-secrets", leaky)
    assert flagged.returncode != 0
    assert "AWS Access Key" in output(flagged)

    passed = _hook(repo_root, "detect-secrets", clean)
    assert passed.returncode == 0, output(passed)


@pytest.mark.ac("S0.1-AC4")
def test_fixture_signature_hook_runs(repo_root: Path, scratch: Path) -> None:
    anything = scratch / "anything.txt"
    anything.write_text("x\n", encoding="utf-8")
    result = _hook(repo_root, "fixture-signatures", anything)
    assert result.returncode == 0, output(result)
    assert "Passed" in output(result), "hook must execute, not be skipped"
