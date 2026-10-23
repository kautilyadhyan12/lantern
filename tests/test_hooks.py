"""Developer hooks use the locked local environment and actually check files."""

import json
import os
import shlex
import subprocess

import pytest
import yaml

EXPECTED = {
    "end-of-file-fixer",
    "trailing-whitespace-fixer",
    "ruff",
    "ruff-format",
    "mypy",
    "detect-secrets",
}


def hook_config(project_file):
    content = project_file(".pre-commit-config.yaml")

    return yaml.safe_load(content)


@pytest.mark.ac("S0.1-AC4")
def test_all_hooks_are_local_uv_commands(project_file):
    config = hook_config(project_file)
    assert config["repos"], "Install the required development hooks"
    for repository in config["repos"]:
        assert repository["repo"] == "local"
        for hook in repository["hooks"]:
            assert hook["language"] == "system"
            assert shlex.split(hook["entry"])[:2] == ["uv", "run"]


@pytest.mark.ac("S0.1-AC4")
def test_expected_hooks_present(project_file):
    config = hook_config(project_file)
    hooks = {hook["id"]: hook for repository in config["repos"] for hook in repository["hooks"]}
    assert hooks.keys() >= EXPECTED
    assert hooks["mypy"].get("pass_filenames") is False
    assert ".secrets.baseline" in hooks["detect-secrets"]["entry"]
    baseline = json.loads(project_file(".secrets.baseline"))
    assert "version" in baseline
    assert "results" in baseline


@pytest.mark.ac("S0.1-AC4")
def test_make_hooks_installs(project_file, repo, tmp_path):
    makefile = project_file("Makefile")
    config = project_file(".pre-commit-config.yaml")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)  # noqa: S603, S607  # Only repository tools and temporary test paths.
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / ".pre-commit-config.yaml").write_text(config)
    env = {**os.environ, "UV_PROJECT": str(repo), "PRE_COMMIT_HOME": str(tmp_path / "hook-cache")}
    result = subprocess.run(
        ["make", "hooks"],  # noqa: S607  # Only repository tools and temporary test paths.
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, "make hooks must install without remote hook repositories"
    installed = tmp_path / ".git/hooks/pre-commit"
    assert installed.is_file()
    assert "pre_commit" in installed.read_text()


@pytest.mark.ac("S0.1-AC4")
def test_whitespace_fixers_change_temp_file(project_file, repo, tmp_path):
    config = hook_config(project_file)
    hooks = {hook["id"]: hook for repository in config["repos"] for hook in repository["hooks"]}
    assert {"end-of-file-fixer", "trailing-whitespace-fixer"} <= hooks.keys()
    sample = tmp_path / "example.txt"
    sample.write_bytes(b"example  \n\n")
    for name in ["trailing-whitespace-fixer", "end-of-file-fixer"]:
        result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
            [*shlex.split(hooks[name]["entry"]), str(sample)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode in {0, 1}
    assert sample.read_bytes() == b"example\n"


@pytest.mark.ac("S0.1-AC4")
def test_secret_scanner_detects_synthetic_token(project_file, repo, tmp_path):
    config = hook_config(project_file)
    hooks = [
        hook for item in config["repos"] for hook in item["hooks"] if hook["id"] == "detect-secrets"
    ]
    assert len(hooks) == 1
    baseline = project_file(".secrets.baseline")
    fake = tmp_path / "example.py"
    # Deliberately generated fake token; never a real credential.
    fake.write_text("api_key = '" + "AKIA" + "A" * 16 + "'\n")
    baseline_path = tmp_path / ".secrets.baseline"
    baseline_path.write_text(baseline)
    command = shlex.split(hooks[0]["entry"])
    command[command.index(".secrets.baseline")] = str(baseline_path)
    clean = tmp_path / "clean.py"
    clean.write_text("value = 42\n")
    clean_result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        [*command, str(clean)], cwd=repo, capture_output=True, text=True, timeout=30, check=False
    )
    assert clean_result.returncode == 0, "Prove the installed scanner runs on a clean file"
    result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        [*command, str(fake)], cwd=repo, capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode == 1, "The installed hook must report the synthetic secret"
    assert str(fake) in result.stdout + result.stderr
