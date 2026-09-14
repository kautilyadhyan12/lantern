import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import CLEAN_CLONE_ENV


def _tool(name: str) -> str:
    path = shutil.which(name)
    assert path is not None, f"`{name}` must be on PATH"
    return path


def _tail(text: str, lines: int = 80) -> str:
    return "\n".join(text.splitlines()[-lines:])


def _copy_worktree(repo: Path, dest: Path, git: str) -> None:
    """Copy tracked + untracked-but-not-ignored files: what a clean clone of this tree holds."""
    listing = subprocess.run(
        [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    for rel in filter(None, listing.split("\0")):
        src = repo / rel
        if src.is_file():  # skips tracked files deleted in the working tree
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


@pytest.mark.slow
@pytest.mark.ac("S0.1-AC1")
def test_clean_clone_uv_sync_and_make_green(
    repo_root: Path, tmp_path: Path, database_url: str
) -> None:
    git, uv, make = _tool("git"), _tool("uv"), _tool("make")
    clone = tmp_path / "clone"
    _copy_worktree(repo_root, clone, git)
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=clone, check=True)
    subprocess.run([git, "add", "-A"], cwd=clone, check=True)

    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
    env[CLEAN_CLONE_ENV] = "1"
    env["LANTERN_DATABASE_URL"] = database_url  # .env is gitignored, so the clone has none

    sync = subprocess.run(
        [uv, "sync", "--frozen"],
        cwd=clone,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    assert sync.returncode == 0, _tail(sync.stdout + sync.stderr)

    run = subprocess.run(
        [make, "lint", "typecheck", "test"],
        cwd=clone,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    assert run.returncode == 0, _tail(run.stdout + run.stderr)
