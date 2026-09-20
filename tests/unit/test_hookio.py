"""S0.2-AC2: the shared hook stdin protocol reader parses payloads and fails closed."""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.hooks import hookio


def _payload(**overrides: Any) -> str:  # hook payloads are arbitrary JSON
    data: dict[str, Any] = {
        "session_id": "s1",
        "transcript_path": "transcript.jsonl",
        "cwd": "D:/osint",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "uv run pytest"},
        "tool_use_id": "tu1",
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.mark.ac("S0.2-AC2")
def test_parse_minimal_payload() -> None:
    hook = hookio.parse_hook_input(_payload())
    assert hook.event == "PreToolUse"
    assert hook.tool_name == "Bash"
    assert hook.command == "uv run pytest"
    assert hook.agent_type is None
    assert hook.stop_hook_active is False
    assert hook.cwd == Path("D:/osint")


@pytest.mark.ac("S0.2-AC2")
def test_parse_subagent_fields() -> None:
    hook = hookio.parse_hook_input(_payload(agent_id="a1", agent_type="t3-reviewer"))
    assert hook.agent_type == "t3-reviewer"


@pytest.mark.ac("S0.2-AC2")
def test_parse_stop_payload() -> None:
    hook = hookio.parse_hook_input(
        json.dumps({"hook_event_name": "Stop", "stop_hook_active": True, "cwd": "D:/osint"})
    )
    assert hook.event == "Stop"
    assert hook.tool_name == ""
    assert hook.command == ""
    assert hook.stop_hook_active is True


@pytest.mark.ac("S0.2-AC2")
def test_file_path_accessor_reads_both_documented_keys() -> None:
    edit = hookio.parse_hook_input(
        _payload(tool_name="Write", tool_input={"file_path": "src/lantern/cli.py"})
    )
    notebook = hookio.parse_hook_input(
        _payload(tool_name="NotebookEdit", tool_input={"notebook_path": "notes.ipynb"})
    )
    assert edit.file_path == "src/lantern/cli.py"
    assert notebook.file_path == "notes.ipynb"


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "tool_input",
    [{}, {"command": None}, {"command": 7}, {"command": ["uv", "run"]}, "not-a-mapping"],
)
def test_accessors_tolerate_wrong_types(tool_input: object) -> None:
    hook = hookio.parse_hook_input(_payload(tool_input=tool_input))
    assert hook.command == ""
    assert hook.file_path == ""


@pytest.mark.ac("S0.2-AC2")
def test_missing_cwd_falls_back_to_the_process_directory() -> None:
    hook = hookio.parse_hook_input(json.dumps({"hook_event_name": "PreToolUse"}))
    assert hook.cwd == Path.cwd()


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize("payload", ["", "   ", "{not json}", "[]", '"a string"', "null"])
def test_malformed_payload_raises(payload: str) -> None:
    with pytest.raises(hookio.HookInputError):
        hookio.parse_hook_input(payload)


@pytest.mark.ac("S0.2-AC2")
def test_read_hook_input_reads_the_given_stream() -> None:
    hook = hookio.read_hook_input(io.StringIO(_payload()))
    assert hook.command == "uv run pytest"


@pytest.mark.ac("S0.2-AC2")
def test_block_writes_reason_to_stderr_and_returns_2() -> None:
    stream = io.StringIO()
    assert hookio.block("guard_bash: GB001 no force pushing", stream=stream) == 2
    assert hookio.BLOCK == 2
    assert "GB001" in stream.getvalue()


@pytest.mark.ac("S0.2-AC2")
def test_allow_returns_0_and_stays_quiet_without_a_note() -> None:
    stream = io.StringIO()
    assert hookio.allow(stream=stream) == 0
    assert hookio.ALLOW == 0
    assert stream.getvalue() == ""
    assert hookio.allow("checked 3 segments", stream=stream) == 0
    assert "checked 3 segments" in stream.getvalue()
