"""S0.2-AC2 / S0.2-AC3: the guards behave as hooks — hook JSON on stdin, exit 2 blocks.

These run the modules exactly the way the harness runs them (`python -m scripts.hooks.<name>`
from the project directory), so a broken module path, or a crash where a refusal was required,
fails here.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import output, run

pytestmark = pytest.mark.slow


def _bash_payload(command: str, **extra: Any) -> str:  # arbitrary hook JSON
    payload: dict[str, Any] = {
        "session_id": "s1",
        "cwd": "",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "tu1",
    }
    payload.update(extra)
    return json.dumps(payload)


def _edit_payload(file_path: str, cwd: Path) -> str:
    return json.dumps(
        {
            "session_id": "s1",
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "x"},
            "tool_use_id": "tu1",
        }
    )


def _hook(module: str, payload: str, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, "-m", module], cwd=repo_root, stdin_text=payload, timeout=60)


@pytest.mark.ac("S0.2-AC2")
def test_guard_bash_cli_blocks_and_explains(repo_root: Path) -> None:
    result = _hook("scripts.hooks.guard_bash", _bash_payload("git push --force"), repo_root)
    assert result.returncode == 2, output(result)
    assert "GB001" in result.stderr


@pytest.mark.ac("S0.2-AC2")
def test_guard_bash_cli_allows_uv_run_pytest(repo_root: Path) -> None:
    result = _hook("scripts.hooks.guard_bash", _bash_payload("uv run pytest"), repo_root)
    assert result.returncode == 0, output(result)


@pytest.mark.ac("S0.2-AC2")
def test_guard_bash_cli_blocks_for_the_reviewer_subagent(repo_root: Path) -> None:
    payload = _bash_payload("uv add httpx", agent_type="t3-reviewer", agent_id="a1")
    result = _hook("scripts.hooks.guard_bash", payload, repo_root)
    assert result.returncode == 2, output(result)
    assert "GB007" in result.stderr


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize("payload", ["", "{not json}"])
def test_guard_bash_cli_fails_closed_on_unreadable_input(payload: str, repo_root: Path) -> None:
    result = _hook("scripts.hooks.guard_bash", payload, repo_root)
    assert result.returncode == 2, output(result)
    assert result.stderr.strip()


@pytest.mark.ac("S0.2-AC3")
def test_guard_paths_cli_blocks_a_fixture_write(repo_root: Path) -> None:
    payload = _edit_payload("tests/fixtures/search/basic.json", repo_root)
    result = _hook("scripts.hooks.guard_paths", payload, repo_root)
    assert result.returncode == 2, output(result)
    assert "GP001" in result.stderr


@pytest.mark.ac("S0.2-AC3")
def test_guard_paths_cli_allows_a_src_write(repo_root: Path) -> None:
    payload = _edit_payload(str(repo_root / "src" / "lantern" / "cli.py"), repo_root)
    result = _hook("scripts.hooks.guard_paths", payload, repo_root)
    assert result.returncode == 0, output(result)


@pytest.mark.ac("S0.2-AC3")
def test_guard_paths_cli_fails_closed_on_unreadable_input(repo_root: Path) -> None:
    result = _hook("scripts.hooks.guard_paths", "", repo_root)
    assert result.returncode == 2, output(result)
    assert result.stderr.strip()
