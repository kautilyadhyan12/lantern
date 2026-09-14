import os
import shutil
from pathlib import Path

import pytest

from tests.conftest import CLEAN_CLONE_ENV
from tests.helpers import output, run, tool

# Stripped so the clone's own `.venv` is used, not the one running this test.
_OUTER_ENV_VARS = {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}


def _copy_worktree(repo: Path, dest: Path, git: str) -> None:
    """Copy tracked + untracked-but-not-ignored files: what a clean clone of this tree holds."""
    listing = run(
        [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=repo, check=True
    ).stdout
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
    git, uv, make = tool("git"), tool("uv"), tool("make")
    clone = tmp_path / "clone"
    _copy_worktree(repo_root, clone, git)
    run([git, "init", "-q", "-b", "main"], cwd=clone, check=True)
    run([git, "add", "-A"], cwd=clone, check=True)

    env = {k: v for k, v in os.environ.items() if k not in _OUTER_ENV_VARS}
    env[CLEAN_CLONE_ENV] = "1"
    env["LANTERN_DATABASE_URL"] = database_url  # .env is gitignored, so the clone has none

    sync = run([uv, "sync", "--frozen"], cwd=clone, env=env, timeout=900)
    assert sync.returncode == 0, output(sync)

    checks = run([make, "lint", "typecheck", "test"], cwd=clone, env=env, timeout=1800)
    assert checks.returncode == 0, output(checks)
