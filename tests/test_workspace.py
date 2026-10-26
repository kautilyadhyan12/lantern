"""Preserve the agent pack and keep local data outside version control."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from lantern.config import Settings

BASE = "1491cfcba7d09d000ee09d6f35a22771a6bfdcd5"


@pytest.mark.ac("S0.1-AC6")
def test_pack_files_unchanged(repo):
    # ADR 0005 authorizes only the devcontainer setup correction.
    paths = ["scripts/review_schema.json", ".codex", ".agents"]
    tracked = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        ["git", "ls-tree", "-r", "--name-only", BASE, "--", *paths],  # noqa: S607  # Only repository tools and temporary test paths.
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert tracked.stdout.splitlines(), "The base pack must exist"
    for relative in tracked.stdout.splitlines():
        original = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
            ["git", "show", f"{BASE}:{relative}"],  # noqa: S607  # Only repository tools and temporary test paths.
            cwd=repo,
            capture_output=True,
            check=True,
            timeout=10,
        ).stdout
        assert (repo / relative).read_bytes() == original, f"Protected pack changed: {relative}"


@pytest.mark.ac("S0.1-AC6")
@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".venv/bin/python",
        "var/evidence.html",
        "src/lantern/__pycache__/config.pyc",
        ".pytest_cache/state",
        ".mypy_cache/cache",
        ".ruff_cache/cache",
        ".hypothesis/examples/example",
    ],
)
def test_gitignore_protects_local_material(project_file, repo, path):
    project_file(".gitignore")
    result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        ["git", "check-ignore", "--no-index", path],  # noqa: S607  # Only repository tools and temporary test paths.
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"Local material must be ignored: {path}"


@pytest.mark.ac("S0.1-AC6")
def test_no_tracked_env(repo):
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z"],  # noqa: S607  # Fixed tool from the Codespace PATH.
            cwd=repo,
            capture_output=True,
            check=True,
            timeout=10,
        )
        .stdout.decode()
        .split("\0")
    )
    prohibited = [
        path
        for path in tracked
        if Path(path).name.startswith(".env") and Path(path).name != ".env.example"
    ]
    assert prohibited == [], "Only placeholder .env.example may be tracked"


@pytest.mark.ac("S0.1-AC6")
def test_example_settings_complete(project_file, repo):
    example = project_file(".env.example")

    variables = {
        line.split("=", 1)[0]
        for line in example.splitlines()
        if "=" in line and not line.startswith("#")
    }
    expected = {"LANTERN_" + field.upper() for field in Settings.model_fields}
    assert expected | {"LANTERN_DB_PORT"} <= variables
    assert "<" in example or "placeholder" in example.lower(), (
        "Example secrets must be placeholders"
    )
    for relative in ["src/lantern/config.py", "compose.yaml"]:
        assert (repo / relative).is_file(), f"Setting inventory also requires {relative}"
    assert not (repo / ".env").is_file(), "Tests must not generate a real .env"


@pytest.mark.ac("S0.1-AC6")
def test_development_commands_available():
    assert sys.version_info[:2] == (3, 12)
    for name in ["uv", "docker", "node", "gh", "codex"]:
        assert shutil.which(name), f"Development container must provide {name}"
    node = subprocess.run(
        ["node", "--version"],  # noqa: S607  # Fixed tool from the Codespace PATH.
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert re.fullmatch(r"v(?:22|24)\.\d+\.\d+\s*", node.stdout), (
        "Expected an October 2026 Node LTS line"
    )
    compose = subprocess.run(
        ["docker", "compose", "version"],  # noqa: S607  # Fixed tool from the Codespace PATH.
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert compose.returncode == 0
