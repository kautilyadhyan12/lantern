"""The stdin/exit-code protocol shared by every guard hook in this package.

A hook receives one JSON object on stdin describing the action the development harness is about to
take, and answers with an exit code: 0 lets it proceed, 2 refuses it and hands the text on stderr
back to the caller. The payload fields used here — `hook_event_name`, `tool_name`, `tool_input`,
`agent_type`, `stop_hook_active`, `cwd` — were verified against the harness's protocol on
2026-09-20.

The payload is produced by the harness itself, so anything unreadable here means the protocol
changed or a hook was wired up wrongly. Guards turn that into a refusal, never a silent allow.
"""

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

BLOCK: Final = 2
ALLOW: Final = 0

FILE_PATH_KEYS: Final = ("file_path", "notebook_path")


class HookInputError(ValueError):
    """The hook payload was missing, unparseable, or not the documented JSON object."""


@dataclass(frozen=True)
class Violation:
    """A refused action: the rule that fired and what to tell the caller."""

    rule: str
    detail: str


@dataclass(frozen=True)
class HookInput:
    """The subset of the hook payload these guards act on."""

    event: str
    tool_name: str
    tool_input: Mapping[str, object]
    agent_type: str | None
    stop_hook_active: bool
    cwd: Path
    raw: Mapping[str, object]

    @property
    def command(self) -> str:
        """The Bash command, or "" when this payload carries none."""
        return _text(self.tool_input.get("command"))

    @property
    def file_path(self) -> str:
        """The edited path, or "" when this payload carries none."""
        for key in FILE_PATH_KEYS:
            path = _text(self.tool_input.get(key))
            if path:
                return path
        return ""


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def parse_hook_input(payload: str) -> HookInput:
    """Parse a hook payload, raising HookInputError on anything unexpected."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HookInputError(f"payload is not JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise HookInputError(f"payload is {type(data).__name__}, expected a JSON object")

    tool_input = data.get("tool_input")
    agent_type = _text(data.get("agent_type")).strip()
    cwd = _text(data.get("cwd")).strip()
    return HookInput(
        event=_text(data.get("hook_event_name")),
        tool_name=_text(data.get("tool_name")),
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        agent_type=agent_type or None,
        stop_hook_active=data.get("stop_hook_active") is True,
        cwd=Path(cwd) if cwd else Path.cwd(),
        raw=data,
    )


def read_hook_input(stream: IO[str] | None = None) -> HookInput:
    """Read and parse the hook payload from `stream` (stdin by default)."""
    return parse_hook_input((stream if stream is not None else sys.stdin).read())


def block(reason: str, *, stream: IO[str] | None = None) -> int:
    """Refuse the action: the reason goes to stderr, which the harness shows to the caller."""
    print(reason, file=stream if stream is not None else sys.stderr)
    return BLOCK


def allow(note: str = "", *, stream: IO[str] | None = None) -> int:
    """Let the action through, optionally leaving a note on stdout."""
    if note:
        print(note, file=stream if stream is not None else sys.stdout)
    return ALLOW
