"""Preserve the agent pack and keep local data outside version control."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.ac("S0.1-AC6")
BASE = "1491cfcba7d09d000ee09d6f35a22771a6bfdcd5"


def test_pack_files_unchanged(repo):
    paths = [".devcontainer/devcontainer.json", "scripts/review_schema.json", ".codex", ".agents"]
    tracked = subprocess.run(["git", "ls-tree", "-r", "--name-only", BASE, "--", *paths],
                             cwd=repo, text=True, capture_output=True, check=True, timeout=10)
    assert tracked.stdout.splitlines(), "The base pack must exist"
    for relative in tracked.stdout.splitlines():
        original = subprocess.run(["git", "show", f"{BASE}:{relative}"], cwd=repo,
                                  capture_output=True, check=True, timeout=10).stdout
        assert (repo / relative).read_bytes() == original, f"Protected pack changed: {relative}"


@pytest.mark.parametrize("path", [".env", ".env.local", ".venv/bin/python", "var/evidence.html",
                                  "src/lantern/__pycache__/config.pyc", ".pytest_cache/state",
                                  ".mypy_cache/cache", ".ruff_cache/cache", ".hypothesis/examples/example"])
def test_gitignore_protects_local_material(project_file, repo, path):
    project_file(".gitignore")
    result = subprocess.run(["git", "check-ignore", "--no-index", path], cwd=repo,
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, f"Local material must be ignored: {path}"


def test_no_tracked_env(repo):
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True,
                             check=True, timeout=10).stdout.decode().split("\0")
    prohibited = [path for path in tracked if Path(path).name.startswith(".env") and Path(path).name != ".env.example"]
    assert prohibited == [], "Only placeholder .env.example may be tracked"


def test_example_settings_complete(project_file, repo):
    example = project_file(".env.example")
    from lantern.config import Settings
    variables = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.startswith("#")}
    expected = {"LANTERN_" + field.upper() for field in Settings.model_fields}
    assert expected | {"LANTERN_DB_PORT"} <= variables
    assert "<" in example or "placeholder" in example.lower(), "Example secrets must be placeholders"
    for relative in ["src/lantern/config.py", "compose.yaml"]:
        assert (repo / relative).is_file(), f"Setting inventory also requires {relative}"
    assert not (repo / ".env").is_file(), "Tests must not generate a real .env"


def test_development_commands_available():
    assert sys.version_info[:2] == (3, 12)
    for name in ["uv", "docker", "node", "gh", "codex"]:
        assert shutil.which(name), f"Development container must provide {name}"
    node = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True, timeout=10)
    assert re.fullmatch(r"v(?:22|24)\.\d+\.\d+\s*", node.stdout), "Expected an October 2026 Node LTS line"
    compose = subprocess.run(["docker", "compose", "version"], capture_output=True, check=False, timeout=10)
    assert compose.returncode == 0
